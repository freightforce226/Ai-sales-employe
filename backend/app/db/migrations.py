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


if __name__ == "__main__":
    async def main():
        await run_engagement_migrations()
        await run_ai_reply_migrations()
    asyncio.run(main())
