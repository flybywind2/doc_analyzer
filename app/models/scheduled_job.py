"""
Scheduled Job model for cron jobs
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean
from sqlalchemy.sql import func
from app.database import Base


class ScheduledJob(Base):
    """Scheduled Job model for cron automation"""
    __tablename__ = "scheduled_jobs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # Job identification
    job_type = Column(String(50), unique=True, nullable=False, index=True)  # 'confluence_sync', 'ai_evaluation'
    name = Column(String(200), nullable=False)  # Display name
    description = Column(Text)

    # Schedule configuration
    cron_expression = Column(String(100))  # Cron expression (e.g., "0 2 * * *" for 2 AM daily)
    is_active = Column(Boolean, default=False, index=True)

    # Execution tracking
    last_run_at = Column(DateTime(timezone=True))
    last_run_status = Column(String(20))  # 'success', 'failed', 'running'
    last_run_message = Column(Text)
    next_run_at = Column(DateTime(timezone=True))

    # Execution count
    total_runs = Column(Integer, default=0)
    successful_runs = Column(Integer, default=0)
    failed_runs = Column(Integer, default=0)

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
