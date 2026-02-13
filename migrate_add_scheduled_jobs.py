"""
Migration: Add scheduled_jobs table and initialize default jobs
"""
from app.database import SessionLocal, engine, Base
from app.models.scheduled_job import ScheduledJob
from sqlalchemy import text


def migrate():
    """Run migration"""
    print("Starting migration: Add scheduled_jobs table")

    # Create tables
    print("Creating scheduled_jobs table...")
    Base.metadata.create_all(bind=engine, tables=[ScheduledJob.__table__])

    # Initialize default scheduled jobs
    db = SessionLocal()
    try:
        # Check if jobs already exist
        existing_count = db.query(ScheduledJob).count()
        if existing_count > 0:
            print(f"Scheduled jobs already exist ({existing_count} jobs). Skipping initialization.")
            return

        # Create default jobs
        jobs = [
            ScheduledJob(
                job_type='confluence_sync',
                name='Confluence 전체 동기화',
                description='Confluence에서 모든 지원서를 가져와 데이터베이스에 저장합니다. 신규 지원서는 추가되고 기존 지원서는 업데이트됩니다.',
                cron_expression='0 2 * * *',  # Daily at 2 AM
                is_active=False
            ),
            ScheduledJob(
                job_type='ai_evaluation',
                name='AI 평가 자동 실행',
                description='아직 AI 평가가 완료되지 않은 지원서들을 자동으로 평가합니다. 이미 평가된 지원서는 재평가하지 않습니다.',
                cron_expression='0 3 * * *',  # Daily at 3 AM (after sync)
                is_active=False
            )
        ]

        for job in jobs:
            db.add(job)
            print(f"  - Created job: {job.name}")

        db.commit()
        print(f"✅ Successfully initialized {len(jobs)} scheduled jobs")
        print("\n⚠️  Note: All jobs are disabled by default. Enable them in Admin > 스케줄 작업 관리")

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()

    print("Migration completed")


if __name__ == "__main__":
    migrate()
