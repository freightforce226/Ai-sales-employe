import asyncio
from sqlalchemy import text
from app.db.session import AsyncSessionLocal
from app.core.logging import get_logger

logger = get_logger(__name__)

async def run_engagement_migrations():
    """
    Executes production-grade SQL migration scripts to create tables for:
    - organization_engagement_settings
    - engagement_executions
    - engagement_execution_logs
    Keeps main.py free of CREATE TABLE logic.
    """
    logger.info("Starting database schema migrations for SaaS Engagement Orchestrator...")
    async with AsyncSessionLocal() as session:
        try:
            # 1. organization_engagement_settings
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS organization_engagement_settings (
                    organization_id UUID PRIMARY KEY,
                    auto_engagement BOOLEAN NOT NULL DEFAULT FALSE,
                    schedule TEXT NOT NULL DEFAULT 'daily',
                    preferred_send_time TEXT NOT NULL DEFAULT '09:00',
                    timezone TEXT NOT NULL DEFAULT 'UTC',
                    emails_per_week INTEGER NOT NULL DEFAULT 3,
                    min_gap_days INTEGER NOT NULL DEFAULT 2,
                    allowed_weekdays JSONB NOT NULL DEFAULT '[1,2,3,4,5]',
                    batch_size INTEGER NOT NULL DEFAULT 50,
                    delay_seconds INTEGER NOT NULL DEFAULT 5,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """))
            await session.commit()
            logger.info("Verified table: organization_engagement_settings")
        except Exception as e:
            await session.rollback()
            logger.error("Failed migrating organization_engagement_settings", error=str(e))

        try:
            # 2. engagement_executions
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS engagement_executions (
                    id UUID PRIMARY KEY,
                    organization_id UUID NOT NULL,
                    workflow_execution_id TEXT,
                    started_by_user UUID,
                    trigger_type TEXT NOT NULL, -- manual | scheduled
                    status TEXT NOT NULL DEFAULT 'started', -- started | running | completed | failed
                    total_customers INTEGER NOT NULL DEFAULT 0,
                    processed INTEGER NOT NULL DEFAULT 0,
                    sent INTEGER NOT NULL DEFAULT 0,
                    failed INTEGER NOT NULL DEFAULT 0,
                    skipped INTEGER NOT NULL DEFAULT 0,
                    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    completed_at TIMESTAMP WITH TIME ZONE,
                    duration_seconds INTEGER,
                    error_message TEXT
                )
            """))
            await session.commit()
            logger.info("Verified table: engagement_executions")
        except Exception as e:
            await session.rollback()
            logger.error("Failed migrating engagement_executions", error=str(e))

        try:
            # 3. engagement_execution_logs
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS engagement_execution_logs (
                    id UUID PRIMARY KEY,
                    execution_id UUID NOT NULL REFERENCES engagement_executions(id) ON DELETE CASCADE,
                    organization_id UUID NOT NULL,
                    customer_id UUID,
                    status TEXT NOT NULL, -- sent | failed | skipped
                    message TEXT,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """))
            await session.commit()
            logger.info("Verified table: engagement_execution_logs")
        except Exception as e:
            await session.rollback()
            logger.error("Failed migrating engagement_execution_logs", error=str(e))

        # 4. Insert default settings rows for any organizations that don't have them
        try:
            await session.execute(text("""
                INSERT INTO organization_engagement_settings (organization_id)
                SELECT id FROM organizations
                ON CONFLICT (organization_id) DO NOTHING
            """))
            await session.commit()
            logger.info("Initialized default settings for organizations")
        except Exception as e:
            await session.rollback()
            logger.error("Failed to populate default engagement settings", error=str(e))

    logger.info("Database schema migrations completed successfully.")


async def run_ai_reply_migrations():
    """
    Executes database migrations to create and seed the organization_ai_settings table.
    """
    logger.info("Starting database schema migrations for AI Reply Engine...")
    async with AsyncSessionLocal() as session:
        try:
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS organization_ai_settings (
                    organization_id UUID PRIMARY KEY REFERENCES organizations(id) ON DELETE CASCADE,
                    ai_enabled BOOLEAN NOT NULL DEFAULT FALSE,
                    company_name CHARACTER VARYING,
                    reply_tone CHARACTER VARYING DEFAULT 'professional',
                    ai_writing_instructions TEXT,
                    email_signature TEXT,
                    default_cc_emails JSONB DEFAULT '[]'::jsonb,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """))
            await session.commit()
            logger.info("Verified table: organization_ai_settings")
        except Exception as e:
            await session.rollback()
            logger.error("Failed migrating organization_ai_settings", error=str(e))

        # Insert default settings rows for any organizations that don't have them
        try:
            await session.execute(text("""
                INSERT INTO organization_ai_settings (organization_id)
                SELECT id FROM organizations
                ON CONFLICT (organization_id) DO NOTHING
            """))
            await session.commit()
            logger.info("Initialized default AI reply settings for organizations")
        except Exception as e:
            await session.rollback()
            logger.error("Failed to populate default AI reply settings", error=str(e))

        # Migrations for Stale Lock Recovery
        try:
            # 1. Add queued_at column
            await session.execute(text("""
                ALTER TABLE email_log 
                ADD COLUMN IF NOT EXISTS queued_at TIMESTAMP WITH TIME ZONE NULL
            """))
            await session.commit()
            
            # 2. Create index for recovery performance
            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_email_log_queued_recovery 
                ON email_log (delivery_status, queued_at)
            """))
            await session.commit()
            
            # 3. Verification check
            res_col = await session.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'email_log' AND column_name = 'queued_at'
            """))
            col_verified = res_col.fetchone() is not None
            
            res_idx = await session.execute(text("""
                SELECT indexname 
                FROM pg_indexes 
                WHERE tablename = 'email_log' AND indexname = 'idx_email_log_queued_recovery'
            """))
            idx_verified = res_idx.fetchone() is not None
            
            if col_verified and idx_verified:
                logger.info("Running AI Reply database migrations...")
                logger.info("OK: queued_at column verified.")
                logger.info("OK: idx_email_log_queued_recovery index verified.")
                logger.info("OK: AI Reply schema up to date.")
            else:
                logger.error("Verification failed: queued_at or index missing from schema metadata.")
        except Exception as e:
            await session.rollback()
            logger.error("Failed executing or verifying AI Reply lock recovery migrations", error=str(e))


async def run_organization_settings_migrations():
    """
    Executes database migrations to create and seed organization_settings table and organization profile columns.
    """
    logger.info("Starting database schema migrations for Organization Settings...")
    async with AsyncSessionLocal() as session:
        # 1. Add profile columns to organizations if missing
        try:
            await session.execute(text("ALTER TABLE organizations ADD COLUMN IF NOT EXISTS phone_number VARCHAR NULL"))
            await session.execute(text("ALTER TABLE organizations ADD COLUMN IF NOT EXISTS website VARCHAR NULL"))
            await session.execute(text("ALTER TABLE organizations ADD COLUMN IF NOT EXISTS timezone VARCHAR NULL DEFAULT 'UTC'"))
            await session.execute(text("ALTER TABLE organizations ADD COLUMN IF NOT EXISTS country VARCHAR NULL"))
            await session.commit()
            logger.info("Verified profile columns on organizations table")
        except Exception as e:
            await session.rollback()
            logger.error("Failed adding profile columns to organizations table", error=str(e))

        # 2. Create organization_settings table
        try:
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS organization_settings (
                    organization_id UUID PRIMARY KEY REFERENCES organizations(id) ON DELETE CASCADE,
                    sender_display_name VARCHAR NULL,
                    reply_to_email VARCHAR NULL,
                    default_signature TEXT NULL,
                    cc_emails TEXT[] DEFAULT '{}',
                    bcc_emails TEXT[] DEFAULT '{}',
                    ai_enabled BOOLEAN NOT NULL DEFAULT FALSE,
                    reply_style VARCHAR NOT NULL DEFAULT 'Professional',
                    reply_length VARCHAR NOT NULL DEFAULT 'Medium',
                    scheduler_enabled BOOLEAN NOT NULL DEFAULT FALSE,
                    scheduler_interval_minutes INTEGER NOT NULL DEFAULT 15,
                    business_hours_enabled BOOLEAN NOT NULL DEFAULT TRUE,
                    working_days TEXT[] DEFAULT '{"Mon","Tue","Wed","Thu","Fri"}',
                    start_time VARCHAR NOT NULL DEFAULT '09:00',
                    end_time VARCHAR NOT NULL DEFAULT '18:00',
                    last_scheduler_run TIMESTAMP WITH TIME ZONE NULL,
                    notify_failed_replies BOOLEAN NOT NULL DEFAULT TRUE,
                    notify_outlook_disconnect BOOLEAN NOT NULL DEFAULT TRUE,
                    daily_summary_enabled BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """))
            await session.commit()
            logger.info("Verified table: organization_settings")
        except Exception as e:
            await session.rollback()
            logger.error("Failed migrating organization_settings", error=str(e))

        # 3. Seed default rows for any organizations that don't have them
        try:
            await session.execute(text("""
                INSERT INTO organization_settings (organization_id)
                SELECT id FROM organizations
                ON CONFLICT (organization_id) DO NOTHING
            """))
            await session.commit()
            logger.info("Initialized default settings for organizations")
        except Exception as e:
            await session.rollback()
            logger.error("Failed to seed default settings for organizations", error=str(e))

        # 4. Idempotently backfill legacy default_cc_emails into organization_settings.cc_emails if empty
        try:
            await session.execute(text("""
                UPDATE organization_settings os
                SET cc_emails = ARRAY(
                    SELECT jsonb_array_elements_text(oas.default_cc_emails)
                    FROM organization_ai_settings oas
                    WHERE oas.organization_id = os.organization_id
                )
                WHERE (os.cc_emails IS NULL OR os.cc_emails = '{}')
                  AND EXISTS (
                      SELECT 1 FROM organization_ai_settings oas
                      WHERE oas.organization_id = os.organization_id
                        AND oas.default_cc_emails IS NOT NULL
                        AND oas.default_cc_emails != '[]'::jsonb
                  )
            """))
            await session.commit()
            logger.info("Idempotently backfilled legacy default CC emails to organization_settings")
        except Exception as e:
            await session.rollback()
            logger.warning("Idempotent legacy default CC backfill warning/skipped", error=str(e))


async def run_smtp_migrations():
    """
    Executes migrations to add SMTP/IMAP configurations and auth_username,
    and make existing Microsoft oauth columns nullable on tenant_integrations.
    """
    logger.info("Starting database schema migrations for SMTP/IMAP integration...")
    async with AsyncSessionLocal() as session:
        # 1. Update IntegrationProvider enum values
        try:
            # PostgreSQL command to add enum value if not exists
            await session.execute(text("ALTER TYPE integration_provider ADD VALUE IF NOT EXISTS 'smtp'"))
            await session.commit()
            logger.info("Verified integration_provider enum contains 'smtp'")
        except Exception as enum_err:
            await session.rollback()
            logger.warning("Alter enum integration_provider returned", error=str(enum_err))

        # 2. Modify existing oauth columns to be nullable
        try:
            await session.execute(text("ALTER TABLE tenant_integrations ALTER COLUMN encrypted_access_token DROP NOT NULL"))
            await session.execute(text("ALTER TABLE tenant_integrations ALTER COLUMN encrypted_refresh_token DROP NOT NULL"))
            await session.execute(text("ALTER TABLE tenant_integrations ALTER COLUMN token_expires_at DROP NOT NULL"))
            await session.commit()
            logger.info("OAuth columns are now nullable in tenant_integrations table")
        except Exception as null_err:
            await session.rollback()
            logger.error("Failed to alter token columns to nullable", error=str(null_err))

        # 3. Add SMTP/IMAP settings columns
        columns_to_add = [
            ("auth_username", "VARCHAR"),
            ("encrypted_password", "VARCHAR"),
            ("smtp_host", "VARCHAR"),
            ("smtp_port", "INTEGER"),
            ("smtp_security", "VARCHAR"),
            ("imap_host", "VARCHAR"),
            ("imap_port", "INTEGER"),
            ("imap_security", "VARCHAR"),
            ("last_sync_cursor", "VARCHAR")
        ]
        for col_name, col_type in columns_to_add:
            try:
                await session.execute(text(f"ALTER TABLE tenant_integrations ADD COLUMN IF NOT EXISTS {col_name} {col_type} NULL"))
                await session.commit()
                logger.info(f"Verified column: {col_name} ({col_type}) exists in tenant_integrations")
            except Exception as col_err:
                await session.rollback()
                logger.error(f"Failed to add column {col_name} ({col_type})", error=str(col_err))

        # 4. Recreate active_organizations_for_engagement view to support both microsoft_graph and smtp
        try:
            await session.execute(text("""
                CREATE OR REPLACE VIEW public.active_organizations_for_engagement AS
                 SELECT o.id AS organization_id,
                    o.name,
                    ti.mailbox_email,
                    ti.token_expires_at
                   FROM organizations o
                   JOIN tenant_integrations ti ON ti.organization_id = o.id 
                     AND ti.provider IN ('microsoft_graph'::integration_provider, 'smtp'::integration_provider) 
                     AND ti.is_active = true
                  WHERE o.is_active = true;
            """))
            await session.commit()
            logger.info("Successfully updated active_organizations_for_engagement view to be provider-agnostic.")
        except Exception as view_err:
            await session.rollback()
            logger.error("Failed to update active_organizations_for_engagement view", error=str(view_err))


if __name__ == "__main__":
    async def main():
        await run_engagement_migrations()
        await run_ai_reply_migrations()
        await run_organization_settings_migrations()
        await run_smtp_migrations()
    asyncio.run(main())
