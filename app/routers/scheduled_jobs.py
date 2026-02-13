"""
Scheduled Jobs router
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime
from app.database import get_db
from app.models.scheduled_job import ScheduledJob
from app.models.user import User
from app.services.auth import get_current_active_admin
from app.services.scheduler import job_scheduler
from pydantic import BaseModel


class ScheduledJobResponse(BaseModel):
    id: int
    job_type: str
    name: str
    description: str | None
    cron_expression: str | None
    is_active: bool
    last_run_at: datetime | None
    last_run_status: str | None
    last_run_message: str | None
    next_run_at: datetime | None
    total_runs: int
    successful_runs: int
    failed_runs: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ScheduledJobUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    cron_expression: str | None = None
    is_active: bool | None = None


router = APIRouter(prefix="/scheduled-jobs", tags=["Scheduled Jobs"])


@router.get("", response_model=List[ScheduledJobResponse])
async def list_scheduled_jobs(
    current_user: User = Depends(get_current_active_admin),
    db: Session = Depends(get_db)
):
    """
    List all scheduled jobs (Admin only)
    """
    jobs = db.query(ScheduledJob).order_by(ScheduledJob.job_type).all()
    return jobs


@router.get("/{job_id}", response_model=ScheduledJobResponse)
async def get_scheduled_job(
    job_id: int,
    current_user: User = Depends(get_current_active_admin),
    db: Session = Depends(get_db)
):
    """
    Get scheduled job details (Admin only)
    """
    job = db.query(ScheduledJob).filter(ScheduledJob.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scheduled job not found"
        )
    return job


@router.put("/{job_id}", response_model=ScheduledJobResponse)
async def update_scheduled_job(
    job_id: int,
    job_data: ScheduledJobUpdate,
    current_user: User = Depends(get_current_active_admin),
    db: Session = Depends(get_db)
):
    """
    Update scheduled job (Admin only)
    """
    job = db.query(ScheduledJob).filter(ScheduledJob.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scheduled job not found"
        )

    # Store previous active state
    was_active = job.is_active

    # Update fields
    update_data = job_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(job, field, value)

    job.updated_at = datetime.utcnow()

    try:
        db.commit()
        db.refresh(job)

        # Update scheduler
        if job.is_active and (not was_active or 'cron_expression' in update_data):
            # Schedule or reschedule job
            job_scheduler.schedule_job(job)
        elif not job.is_active and was_active:
            # Unschedule job
            job_scheduler.unschedule_job(job.job_type)

        return job

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update scheduled job: {str(e)}"
        )


@router.post("/{job_id}/toggle", response_model=ScheduledJobResponse)
async def toggle_scheduled_job(
    job_id: int,
    current_user: User = Depends(get_current_active_admin),
    db: Session = Depends(get_db)
):
    """
    Toggle scheduled job active status (Admin only)
    """
    job = db.query(ScheduledJob).filter(ScheduledJob.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scheduled job not found"
        )

    # Toggle active state
    job.is_active = not job.is_active
    job.updated_at = datetime.utcnow()

    try:
        db.commit()
        db.refresh(job)

        # Update scheduler
        if job.is_active:
            job_scheduler.schedule_job(job)
        else:
            job_scheduler.unschedule_job(job.job_type)

        return job

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to toggle scheduled job: {str(e)}"
        )


@router.post("/{job_id}/run-now")
async def run_scheduled_job_now(
    job_id: int,
    current_user: User = Depends(get_current_active_admin),
    db: Session = Depends(get_db)
):
    """
    Manually trigger a scheduled job to run immediately (Admin only)
    """
    job = db.query(ScheduledJob).filter(ScheduledJob.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scheduled job not found"
        )

    try:
        # Get job function
        job_func = job_scheduler._get_job_function(job.job_type)
        if not job_func:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown job type: {job.job_type}"
            )

        # Update status to running
        job.last_run_status = 'running'
        job.last_run_at = datetime.utcnow()
        job.total_runs += 1
        db.commit()

        # Execute job function
        result_data = None
        try:
            result_data = job_func()
            job.last_run_status = 'success'

            # Format result message based on job type
            if job.job_type == 'confluence_sync' and result_data:
                job.last_run_message = f"동기화 완료: 총 {result_data.get('total_pages', 0)}개, 신규 {result_data.get('new_count', 0)}개, 업데이트 {result_data.get('updated_count', 0)}개, 오류 {result_data.get('error_count', 0)}개"
            elif job.job_type == 'ai_evaluation' and result_data:
                job.last_run_message = f"평가 완료: 총 {result_data.get('total_count', 0)}개, 성공 {result_data.get('success_count', 0)}개, 실패 {result_data.get('fail_count', 0)}개"
            else:
                job.last_run_message = 'Manually triggered job completed successfully'

            job.successful_runs += 1
        except Exception as e:
            job.last_run_status = 'failed'
            job.last_run_message = str(e)[:500]
            job.failed_runs += 1
            raise

        db.commit()

        return {
            "message": f"Job '{job.name}' executed successfully",
            "result": result_data,
            "status": job.last_run_status,
            "details": job.last_run_message
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to run job: {str(e)}"
        )
