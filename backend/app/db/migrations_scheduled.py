import asyncio
from sqlalchemy import text
from app.db.session import AsyncSessionLocal, engine
from app.core.logging import get_logger

logger = get_logger(__name__)

async def run_scheduled_migrations():
    logger.info("Starting DDL migration for scheduled executions and idempotent functions...")
    
    # Alter type in AUTOCOMMIT mode to allow adding enum values without transaction errors
    async with engine.connect() as conn:
        await conn.execution_options(isolation_level="AUTOCOMMIT")
        await conn.execute(text("ALTER TYPE public.followup_status ADD VALUE IF NOT EXISTS 'completed';"))
    
    async with AsyncSessionLocal() as session:
        try:
            # Drop old eligible function signatures to prevent argument mismatch issues
            await session.execute(text("DROP FUNCTION IF EXISTS public.get_engagement_eligible_customers(uuid, date, integer, integer, integer);"))
            await session.execute(text("DROP FUNCTION IF EXISTS public.get_engagement_eligible_customers(uuid, date, integer, integer, integer, integer);"))
            await session.execute(text("DROP FUNCTION IF EXISTS public.enqueue_followup_step(uuid, uuid, uuid);"))
            await session.execute(text("DROP FUNCTION IF EXISTS public.enqueue_followup_step(uuid, uuid, uuid, integer);"))

            # Alter follow_up_schedule table to add completed_at, message_id, and reply tracking details
            await session.execute(text("ALTER TABLE public.follow_up_schedule ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP WITH TIME ZONE;"))
            await session.execute(text("ALTER TABLE public.follow_up_schedule ADD COLUMN IF NOT EXISTS message_id VARCHAR;"))
            await session.execute(text("ALTER TABLE public.follow_up_schedule ADD COLUMN IF NOT EXISTS reply_detected_at TIMESTAMP WITH TIME ZONE;"))
            await session.execute(text("ALTER TABLE public.follow_up_schedule ADD COLUMN IF NOT EXISTS reply_message_id VARCHAR;"))
            await session.execute(text("ALTER TABLE public.follow_up_schedule ADD COLUMN IF NOT EXISTS reply_thread_id VARCHAR;"))
            await session.execute(text("ALTER TABLE public.follow_up_schedule ADD COLUMN IF NOT EXISTS reply_subject VARCHAR;"))
            await session.execute(text("ALTER TABLE public.follow_up_schedule ADD COLUMN IF NOT EXISTS reply_from VARCHAR;"))
            await session.execute(text("ALTER TABLE public.follow_up_schedule ADD COLUMN IF NOT EXISTS reply_reason VARCHAR;"))
            
            # Alter email_log table to add threading metadata
            await session.execute(text("ALTER TABLE public.email_log ADD COLUMN IF NOT EXISTS thread_id VARCHAR;"))
            await session.execute(text("ALTER TABLE public.email_log ADD COLUMN IF NOT EXISTS internet_message_id VARCHAR;"))
            await session.execute(text("ALTER TABLE public.email_log ADD COLUMN IF NOT EXISTS \"references\" TEXT;"))
            await session.execute(text("ALTER TABLE public.email_log ADD COLUMN IF NOT EXISTS in_reply_to VARCHAR;"))
            logger.info("Successfully updated follow_up_schedule and email_log table columns.")

            # Recreate get_engagement_eligible_customers
            await session.execute(text("""
                CREATE OR REPLACE FUNCTION public.get_engagement_eligible_customers(
                    p_organization_id uuid,
                    p_week_start date,
                    p_weekly_cap integer DEFAULT 2,
                    p_min_gap_days integer DEFAULT 2,
                    p_batch_limit integer DEFAULT 200,
                    p_batch_offset integer DEFAULT 0
                )
                RETURNS TABLE(
                    customer_id uuid,
                    company_name text,
                    industry text,
                    country text,
                    contact_email text,
                    last_contact_date date,
                    segment_type text,
                    emails_sent_this_week integer
                )
                LANGUAGE sql
                STABLE
                AS $function$
                  select
                    c.id as customer_id,
                    c.company_name,
                    c.industry,
                    c.country,
                    c.contact_email,
                    c.last_contact_date,
                    latest_seg.segment_type::text,
                    coalesce(ec.emails_sent_this_week, 0) as emails_sent_this_week
                  from customers c
                  inner join lateral (
                    select cs.segment_type
                    from customer_segments cs
                    where cs.customer_id = c.id
                    order by cs.computed_at desc
                    limit 1
                  ) latest_seg on true
                  left join engagement_counters ec
                    on ec.customer_id = c.id
                    and ec.week_start = p_week_start
                  where c.organization_id = p_organization_id
                    and c.deleted_at is null
                    and latest_seg.segment_type in ('dormant', 'inactive')
                    and coalesce(ec.emails_sent_this_week, 0) < p_weekly_cap
                    and not exists (
                      select 1 from email_log el
                      where el.customer_id = c.id
                        and el.organization_id = p_organization_id
                        and el.direction = 'outbound'
                        and el.email_type = 'engagement'
                        and el.sent_at > now() - (p_min_gap_days * interval '1 day')
                    )
                  order by c.last_contact_date asc nulls first
                  limit p_batch_limit
                  offset p_batch_offset;
                $function$;
            """))
            logger.info("Successfully deployed public.get_engagement_eligible_customers function.")
            
            # Recreate record_engagement_send_and_increment
            await session.execute(text("""
                CREATE OR REPLACE FUNCTION public.record_engagement_send_and_increment(
                    p_organization_id uuid,
                    p_customer_id uuid,
                    p_subject text,
                    p_body text,
                    p_has_attachment boolean,
                    p_graph_message_id text,
                    p_sent_at timestamp with time zone
                )
                RETURNS uuid
                LANGUAGE plpgsql
                AS $function$
                DECLARE
                  v_email_log_id uuid;
                  v_week_start date;
                  v_sent_count integer;
                BEGIN
                  v_week_start := date_trunc('week', p_sent_at)::date;

                  -- 1. Insert/update email_log
                  v_email_log_id := record_engagement_send(
                    p_organization_id,
                    p_customer_id,
                    p_subject,
                    p_body,
                    p_has_attachment,
                    p_graph_message_id,
                    p_sent_at
                  );

                  -- 2. Count actual emails sent this week
                  SELECT COUNT(*) INTO v_sent_count
                  FROM email_log
                  WHERE customer_id = p_customer_id
                    AND organization_id = p_organization_id
                    AND email_type = 'engagement'
                    AND sent_at >= v_week_start::timestamp;

                  -- 3. Upsert counter with the exact database count
                  INSERT INTO engagement_counters (
                    organization_id,
                    customer_id,
                    week_start,
                    emails_sent_this_week
                  )
                  VALUES (
                    p_organization_id,
                    p_customer_id,
                    v_week_start,
                    v_sent_count
                  )
                  ON CONFLICT (customer_id, week_start)
                  DO UPDATE
                  SET emails_sent_this_week = v_sent_count;

                  -- 4. Update customer timestamps
                  UPDATE customers
                  SET last_contact_date = p_sent_at::date,
                      updated_at = NOW()
                  WHERE id = p_customer_id;

                  -- 5. Automatically enqueue customer's first follow-up
                  PERFORM public.enqueue_followup_step(p_organization_id, p_customer_id, v_email_log_id);
 
                  RETURN v_email_log_id;
                END;
                $function$;
            """))
            logger.info("Successfully deployed public.record_engagement_send_and_increment function.")

            # Deploy enqueue_followup_step DDL function
            await session.execute(text("""
                CREATE OR REPLACE FUNCTION public.enqueue_followup_step(
                    p_organization_id uuid,
                    p_customer_id uuid,
                    p_source_email_log_id uuid,
                    p_step_number integer DEFAULT 1
                )
                RETURNS uuid
                LANGUAGE plpgsql
                AS $function$
                DECLARE
                  v_max_follow_ups integer;
                  v_stop_on_reply boolean;
                  v_config jsonb;
                  v_step_config jsonb;
                  v_delay_days integer;
                  v_ai_rewrite boolean;
                  v_profile_id uuid;
                  v_scheduled_datetime timestamp with time zone;
                  v_scheduled_date date;
                  v_followup_id uuid;
                  v_has_replied boolean;
                  v_sent_at timestamp with time zone;
                  v_base_time timestamp with time zone;
                  v_timezone text;
                  v_pref_send_time text;
                BEGIN
                  -- 1. Fetch Follow-up & Timezone Settings
                  SELECT max_follow_ups, stop_on_reply, follow_up_sequence_config, timezone, preferred_send_time
                  INTO v_max_follow_ups, v_stop_on_reply, v_config, v_timezone, v_pref_send_time
                  FROM organization_engagement_settings
                  WHERE organization_id = p_organization_id;

                  -- If settings don't exist or max_follow_ups is 0, exit early
                  IF NOT FOUND OR v_max_follow_ups IS NULL OR v_max_follow_ups = 0 THEN
                    RETURN NULL;
                  END IF;

                  -- If requested step is greater than max configured followups, do not insert
                  IF p_step_number > v_max_follow_ups THEN
                    RETURN NULL;
                  END IF;

                  -- 2. Fetch step config
                  SELECT value INTO v_step_config
                  FROM jsonb_array_elements(v_config)
                  WHERE (value->>'step_number')::integer = p_step_number;

                  IF NOT FOUND OR v_step_config IS NULL THEN
                    -- Fallback default values
                    v_delay_days := 3;
                    v_ai_rewrite := true;
                    v_profile_id := NULL;
                  ELSE
                    -- Check if step is enabled. If not enabled, exit early
                    IF (v_step_config->>'is_enabled')::boolean = false THEN
                       RETURN NULL;
                    END IF;
                    v_delay_days := (v_step_config->>'delay_days')::integer;
                    v_ai_rewrite := (v_step_config->>'ai_rewrite_enabled')::boolean;
                    v_profile_id := (v_step_config->>'attachment_profile_id')::uuid;
                  END IF;

                  -- 3. Idempotency Check: check for an existing active schedule (status pending or paused)
                  SELECT id INTO v_followup_id
                  FROM follow_up_schedule
                  WHERE organization_id = p_organization_id
                    AND customer_id = p_customer_id
                    AND step_number = p_step_number
                    AND status::text IN ('pending', 'paused');

                  IF v_followup_id IS NOT NULL THEN
                    RETURN v_followup_id;
                  END IF;

                  -- 4. Check if customer has sent an inbound reply after the engagement email
                  SELECT sent_at INTO v_sent_at
                  FROM email_log
                  WHERE id = p_source_email_log_id;

                  IF v_sent_at IS NULL THEN
                    v_sent_at := NOW();
                  END IF;

                  SELECT EXISTS(
                    SELECT 1 FROM email_log
                    WHERE customer_id = p_customer_id
                      AND organization_id = p_organization_id
                      AND direction = 'inbound'
                      AND sent_at > v_sent_at
                  ) INTO v_has_replied;

                  IF v_has_replied THEN
                    RETURN NULL;
                  END IF;

                  -- 5. Calculate offset scheduled date/datetime using previous completion or parent sent time
                  v_base_time := NULL;
                  IF p_step_number > 1 THEN
                    SELECT completed_at INTO v_base_time
                    FROM follow_up_schedule
                    WHERE customer_id = p_customer_id
                      AND organization_id = p_organization_id
                      AND step_number = p_step_number - 1
                      AND status = 'completed'
                    ORDER BY completed_at DESC
                    LIMIT 1;
                  END IF;

                  IF v_base_time IS NULL THEN
                    v_base_time := v_sent_at;
                  END IF;

                  -- Bind base time by current time to avoid historical scheduling
                  IF v_base_time < NOW() THEN
                    v_base_time := NOW();
                  END IF;

                  v_scheduled_datetime := v_base_time + (v_delay_days * interval '1 day');
                  v_scheduled_date := v_scheduled_datetime::date;

                  -- Adjust to Organization's local preferred Send Time, converted to UTC
                  BEGIN
                      v_scheduled_datetime := (v_scheduled_date::text || ' ' || COALESCE(v_pref_send_time, '09:00'))::timestamp AT TIME ZONE COALESCE(v_timezone, 'UTC');
                  EXCEPTION WHEN OTHERS THEN
                      -- Fallback if conversion fails
                      v_scheduled_datetime := v_base_time + (v_delay_days * interval '1 day');
                  END;

                  v_followup_id := gen_random_uuid();

                  -- 6. Insert new follow-up step
                  INSERT INTO follow_up_schedule (
                    id, organization_id, customer_id, source_email_log_id, campaign_id,
                    scheduled_date, trigger_phrase, source, status, created_at, updated_at,
                    step_number, attachment_profile_id, scheduled_datetime, draft_status,
                    ai_rewrite_enabled, ai_draft_body
                  )
                  VALUES (
                    v_followup_id, p_organization_id, p_customer_id, p_source_email_log_id, NULL,
                    v_scheduled_date, NULL, 'auto_rule', 'pending', NOW(), NOW(),
                    p_step_number, v_profile_id, v_scheduled_datetime, 'pending_review',
                    v_ai_rewrite, NULL
                  );

                  RETURN v_followup_id;
                END;
                $function$;
            """))
            logger.info("Successfully deployed public.enqueue_followup_step function.")

            # Deduplicate existing pending schedules to allow unique index creation
            await session.execute(text("""
                DELETE FROM public.follow_up_schedule f1
                USING public.follow_up_schedule f2
                WHERE f1.status = 'pending'
                  AND f2.status = 'pending'
                  AND f1.organization_id = f2.organization_id
                  AND f1.customer_id = f2.customer_id
                  AND f1.step_number = f2.step_number
                  AND f1.id > f2.id;
            """))
            logger.info("Successfully deduplicated follow_up_schedule table.")

            # Create partial unique index
            await session.execute(text("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_follow_up_schedule_unique_active
                ON public.follow_up_schedule (organization_id, customer_id, step_number)
                WHERE status = 'pending';
            """))
            logger.info("Successfully created partial unique index on public.follow_up_schedule.")

            # Recreate get_due_followups
            await session.execute(text("""
                CREATE OR REPLACE FUNCTION public.get_due_followups(
                    p_organization_id uuid
                )
                RETURNS TABLE(
                    schedule_id uuid,
                    organization_id uuid,
                    customer_id uuid,
                    customer_name text,
                    company_name text,
                    customer_email text,
                    source_email_log_id uuid,
                    step_number integer,
                    attachment_profile_id uuid,
                    ai_rewrite_enabled boolean,
                    ai_draft_body text,
                    scheduled_datetime timestamp with time zone,
                    mailbox_email text
                )
                LANGUAGE sql
                STABLE
                AS $function$
                  select
                    f.id as schedule_id,
                    f.organization_id,
                    f.customer_id,
                    c.contact_name as customer_name,
                    c.company_name,
                    c.contact_email as customer_email,
                    f.source_email_log_id,
                    f.step_number,
                    f.attachment_profile_id,
                    f.ai_rewrite_enabled,
                    f.ai_draft_body,
                    f.scheduled_datetime,
                    aoe.mailbox_email
                  from follow_up_schedule f
                  join customers c on f.customer_id = c.id
                  left join follow_up_attachment_profiles ap on f.attachment_profile_id = ap.id
                  left join active_organizations_for_engagement aoe on aoe.organization_id = f.organization_id
                  left join organization_engagement_settings oes on oes.organization_id = f.organization_id
                  left join email_log el_source on el_source.id = f.source_email_log_id
                  where f.organization_id = p_organization_id
                    and f.status::text = 'pending'
                    and f.draft_status = 'pending_review'
                    and f.scheduled_datetime <= now()
                    and f.ai_rewrite_enabled = true
                    and c.deleted_at is null
                    and (
                      oes.stop_on_reply is not true
                      or not exists (
                        select 1 from email_log el_inbound
                        where el_inbound.customer_id = f.customer_id
                          and el_inbound.organization_id = f.organization_id
                          and el_inbound.direction = 'inbound'
                          and el_inbound.sent_at > el_source.sent_at
                      )
                    )
                  order by f.scheduled_datetime asc;
                $function$;
            """))
            logger.info("Successfully deployed public.get_due_followups function.")

            # Create follow_up_executions table
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS public.follow_up_executions (
                    id UUID PRIMARY KEY,
                    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
                    workflow_execution_id VARCHAR,
                    trigger_type VARCHAR NOT NULL,
                    status VARCHAR NOT NULL,
                    started_by_user UUID REFERENCES users(id) ON DELETE SET NULL,
                    total_customers INTEGER DEFAULT 0,
                    processed INTEGER DEFAULT 0,
                    sent INTEGER DEFAULT 0,
                    failed INTEGER DEFAULT 0,
                    skipped INTEGER DEFAULT 0,
                    stopped_by_reply_count INTEGER DEFAULT 0,
                    started_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                    completed_at TIMESTAMP WITH TIME ZONE,
                    duration_seconds INTEGER,
                    error_message TEXT,
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
                );
            """))
            await session.execute(text("ALTER TABLE public.follow_up_executions ADD COLUMN IF NOT EXISTS stopped_by_reply_count INTEGER DEFAULT 0;"))
            logger.info("Successfully created/updated follow_up_executions table.")

            # Add sync tracking columns to tenant_integrations
            await session.execute(text("""
                ALTER TABLE public.tenant_integrations 
                ADD COLUMN IF NOT EXISTS last_successful_sync TIMESTAMP WITH TIME ZONE,
                ADD COLUMN IF NOT EXISTS sync_started_at TIMESTAMP WITH TIME ZONE,
                ADD COLUMN IF NOT EXISTS sync_completed_at TIMESTAMP WITH TIME ZONE,
                ADD COLUMN IF NOT EXISTS last_graph_delta_link TEXT;
            """))
            logger.info("Successfully added tracking columns to tenant_integrations.")

            # Create partial unique indexes to guarantee single active execution per organization
            await session.execute(text("""
                CREATE UNIQUE INDEX IF NOT EXISTS uq_active_engagement_execution 
                ON public.engagement_executions (organization_id) 
                WHERE status IN ('pending', 'started', 'running');
            """))
            await session.execute(text("""
                CREATE UNIQUE INDEX IF NOT EXISTS uq_active_followup_execution 
                ON public.follow_up_executions (organization_id) 
                WHERE status IN ('pending', 'started', 'running');
            """))
            logger.info("Successfully deployed partial unique constraints.")

            # Create start_engagement_execution stored procedure
            await session.execute(text("""
                CREATE OR REPLACE FUNCTION public.start_engagement_execution(
                    p_organization_id UUID,
                    p_workflow_execution_id TEXT,
                    p_trigger_type TEXT,
                    p_started_by_user UUID,
                    p_timeout_hours INTEGER DEFAULT 2
                )
                RETURNS TABLE (
                    already_running BOOLEAN,
                    execution_id UUID,
                    workflow_execution_id TEXT,
                    status TEXT,
                    started_at TIMESTAMP WITH TIME ZONE,
                    total_customers INTEGER
                ) AS $func$
                #variable_conflict use_column
                DECLARE
                    v_existing_id UUID;
                    v_existing_workflow_id TEXT;
                    v_existing_status TEXT;
                    v_existing_started_at TIMESTAMP WITH TIME ZONE;
                    v_existing_total_customers INTEGER;
                    v_new_id UUID;
                    v_new_started_at TIMESTAMP WITH TIME ZONE;
                    v_total_eligible INTEGER;
                    v_weekly_cap INTEGER;
                    v_min_gap INTEGER;
                    v_batch_limit INTEGER;
                BEGIN
                    -- Acquire transactional advisory lock on organization to prevent race conditions
                    PERFORM pg_advisory_xact_lock(hashtext(p_organization_id::text));

                    -- Clean up stale executions
                    UPDATE public.engagement_executions
                    SET status = 'failed',
                        error_message = 'Execution timed out after ' || p_timeout_hours || ' hours in started/running/pending state.',
                        completed_at = NOW()
                    WHERE organization_id = p_organization_id
                       AND status IN ('pending', 'started', 'running')
                       AND started_at < (NOW() - (p_timeout_hours || ' hours')::INTERVAL);

                    -- Check for active execution
                    SELECT id, public.engagement_executions.workflow_execution_id, status, public.engagement_executions.started_at, total_customers
                    INTO v_existing_id, v_existing_workflow_id, v_existing_status, v_existing_started_at, v_existing_total_customers
                    FROM public.engagement_executions
                    WHERE organization_id = p_organization_id
                      AND status IN ('pending', 'started', 'running')
                    ORDER BY started_at DESC
                    LIMIT 1;

                    IF FOUND THEN
                         RETURN QUERY SELECT TRUE, v_existing_id, v_existing_workflow_id, v_existing_status, v_existing_started_at, v_existing_total_customers;
                         RETURN;
                    END IF;

                    -- Retrieve settings for total customers count
                    SELECT emails_per_week, min_gap_days, batch_size
                    INTO v_weekly_cap, v_min_gap, v_batch_limit
                    FROM public.organization_engagement_settings
                    WHERE organization_id = p_organization_id;

                    IF NOT FOUND THEN
                         v_weekly_cap := 3;
                         v_min_gap := 2;
                         v_batch_limit := 50;
                    END IF;

                    -- Calculate eligible customer count
                    SELECT COUNT(*)::INTEGER
                    INTO v_total_eligible
                    FROM public.get_engagement_eligible_customers(
                         p_organization_id := p_organization_id,
                         p_week_start := date_trunc('week', NOW())::date,
                         p_weekly_cap := v_weekly_cap,
                         p_min_gap_days := v_min_gap,
                         p_batch_limit := v_batch_limit,
                         p_batch_offset := 0
                    );

                    v_new_id := gen_random_uuid();
                    v_new_started_at := NOW();

                    INSERT INTO public.engagement_executions (
                        id, organization_id, workflow_execution_id, started_by_user, trigger_type, status,
                        total_customers, processed, sent, failed, skipped, started_at
                    ) VALUES (
                        v_new_id, p_organization_id, p_workflow_execution_id, p_started_by_user, p_trigger_type, 'started',
                        v_total_eligible, 0, 0, 0, 0, v_new_started_at
                    );

                    RETURN QUERY SELECT FALSE, v_new_id, p_workflow_execution_id, 'started'::TEXT, v_new_started_at, v_total_eligible;
                END;
                $func$ LANGUAGE plpgsql;
            """))

            # Create start_followup_execution stored procedure
            await session.execute(text("""
                CREATE OR REPLACE FUNCTION public.start_followup_execution(
                    p_organization_id UUID,
                    p_workflow_execution_id TEXT,
                    p_trigger_type TEXT,
                    p_started_by_user UUID,
                    p_timeout_hours INTEGER DEFAULT 2
                )
                RETURNS TABLE (
                    already_running BOOLEAN,
                    execution_id UUID,
                    workflow_execution_id TEXT,
                    status TEXT,
                    started_at TIMESTAMP WITH TIME ZONE,
                    total_customers INTEGER
                ) AS $func$
                #variable_conflict use_column
                DECLARE
                    v_existing_id UUID;
                    v_existing_workflow_id TEXT;
                    v_existing_status TEXT;
                    v_existing_started_at TIMESTAMP WITH TIME ZONE;
                    v_existing_total_customers INTEGER;
                    v_new_id UUID;
                    v_new_started_at TIMESTAMP WITH TIME ZONE;
                    v_total_eligible INTEGER;
                BEGIN
                    -- Acquire transactional advisory lock on organization to prevent race conditions
                    PERFORM pg_advisory_xact_lock(hashtext(p_organization_id::text));

                    -- Clean up stale executions
                    UPDATE public.follow_up_executions
                    SET status = 'failed',
                        error_message = 'Execution timed out after ' || p_timeout_hours || ' hours in started/running/pending state.',
                        completed_at = NOW()
                    WHERE organization_id = p_organization_id
                      AND status IN ('pending', 'started', 'running')
                      AND started_at < (NOW() - (p_timeout_hours || ' hours')::INTERVAL);

                    -- Check for active execution
                    SELECT id, public.follow_up_executions.workflow_execution_id, status, public.follow_up_executions.started_at, total_customers
                    INTO v_existing_id, v_existing_workflow_id, v_existing_status, v_existing_started_at, v_existing_total_customers
                    FROM public.follow_up_executions
                    WHERE organization_id = p_organization_id
                      AND status IN ('pending', 'started', 'running')
                    ORDER BY started_at DESC
                    LIMIT 1;

                    IF FOUND THEN
                         RETURN QUERY SELECT TRUE, v_existing_id, v_existing_workflow_id, v_existing_status, v_existing_started_at, v_existing_total_customers;
                         RETURN;
                    END IF;

                    -- Calculate due followups count
                    SELECT COUNT(*)::INTEGER
                    INTO v_total_eligible
                    FROM public.follow_up_schedule f
                    JOIN public.customers c ON f.customer_id = c.id
                    WHERE f.organization_id = p_organization_id 
                      AND f.draft_status = 'scheduled'
                      AND f.scheduled_datetime <= NOW()
                      AND c.deleted_at IS NULL;

                    v_new_id := gen_random_uuid();
                    v_new_started_at := NOW();

                    INSERT INTO public.follow_up_executions (
                        id, organization_id, workflow_execution_id, started_by_user, trigger_type, status,
                        total_customers, processed, sent, failed, skipped, started_at
                    ) VALUES (
                        v_new_id, p_organization_id, p_workflow_execution_id, p_started_by_user, p_trigger_type, 'started',
                        v_total_eligible, 0, 0, 0, 0, v_new_started_at
                    );

                    RETURN QUERY SELECT FALSE, v_new_id, p_workflow_execution_id, 'started'::TEXT, v_new_started_at, v_total_eligible;
                END;
                $func$ LANGUAGE plpgsql;
            """))
            logger.info("Successfully deployed start execution stored procedures.")

            await session.commit()
            
        except Exception as e:
            await session.rollback()
            logger.error("DDL Migration failed", error=str(e))
            raise e

    # Backfill historical engagement email logs
    async with AsyncSessionLocal() as session:
        try:
            logger.info("Starting historical engagement emails backfill...")
            res = await session.execute(text("""
                SELECT id, organization_id, customer_id, sent_at 
                FROM email_log 
                WHERE email_type = 'engagement' AND direction = 'outbound'
            """))
            logs = res.fetchall()
            backfilled_count = 0
            for email_log_id, org_id, cust_id, sent_at in logs:
                enqueue_res = await session.execute(
                    text("SELECT public.enqueue_followup_step(:org_id, :cust_id, :log_id)"),
                    {"org_id": org_id, "cust_id": cust_id, "log_id": email_log_id}
                )
                new_fid = enqueue_res.scalar()
                if new_fid:
                    backfilled_count += 1
            await session.commit()
            logger.info(f"Backfill successfully completed. Scheduled {backfilled_count} new follow-up records.")
        except Exception as e:
            await session.rollback()
            logger.error("Backfill failed", error=str(e))

if __name__ == "__main__":
    asyncio.run(run_scheduled_migrations())
