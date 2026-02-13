"""
Job Scheduler Service using APScheduler
"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR
from datetime import datetime
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.scheduled_job import ScheduledJob
from app.models.application import Application
from app.models.category import AICategory
from app.models.evaluation import EvaluationCriteria
from app.services.confluence_parser import confluence_parser
from app.services.ai_classifier import ai_classifier
from app.services.llm_evaluator import llm_evaluator
import logging

logger = logging.getLogger(__name__)


class JobScheduler:
    """Background job scheduler"""

    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.scheduler.add_listener(self._job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)

    def start(self):
        """Start the scheduler"""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("Job scheduler started")
            self.load_jobs_from_db()

    def shutdown(self):
        """Shutdown the scheduler"""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Job scheduler stopped")

    def load_jobs_from_db(self):
        """Load active jobs from database and schedule them"""
        db = SessionLocal()
        try:
            jobs = db.query(ScheduledJob).filter(ScheduledJob.is_active == True).all()
            for job in jobs:
                self.schedule_job(job)
            logger.info(f"Loaded {len(jobs)} active jobs from database")
        except Exception as e:
            logger.error(f"Error loading jobs from database: {e}")
        finally:
            db.close()

    def schedule_job(self, job: ScheduledJob):
        """Schedule a job based on its configuration"""
        try:
            # Remove existing job if any
            try:
                self.scheduler.remove_job(job.job_type)
            except:
                pass

            if not job.is_active:
                return

            # Parse cron expression
            trigger = CronTrigger.from_crontab(job.cron_expression)

            # Map job type to function
            job_func = self._get_job_function(job.job_type)
            if not job_func:
                logger.error(f"Unknown job type: {job.job_type}")
                return

            # Add job to scheduler
            self.scheduler.add_job(
                job_func,
                trigger=trigger,
                id=job.job_type,
                name=job.name,
                replace_existing=True
            )

            # Update next run time
            db = SessionLocal()
            try:
                db_job = db.query(ScheduledJob).filter(ScheduledJob.job_type == job.job_type).first()
                if db_job:
                    scheduled_job = self.scheduler.get_job(job.job_type)
                    if scheduled_job:
                        db_job.next_run_at = scheduled_job.next_run_time
                        db.commit()
            finally:
                db.close()

            logger.info(f"Scheduled job: {job.name} with cron: {job.cron_expression}")

        except Exception as e:
            logger.error(f"Error scheduling job {job.job_type}: {e}")

    def unschedule_job(self, job_type: str):
        """Remove a job from scheduler"""
        try:
            self.scheduler.remove_job(job_type)
            logger.info(f"Unscheduled job: {job_type}")
        except:
            pass

    def _get_job_function(self, job_type: str):
        """Get the function to execute for a job type"""
        job_functions = {
            'confluence_sync': self._run_confluence_sync,
            'ai_evaluation': self._run_ai_evaluation
        }
        return job_functions.get(job_type)

    def _job_listener(self, event):
        """Listen to job execution events"""
        db = SessionLocal()
        try:
            job_id = event.job_id
            job = db.query(ScheduledJob).filter(ScheduledJob.job_type == job_id).first()

            if not job:
                return

            job.total_runs += 1

            if event.exception:
                job.last_run_status = 'failed'
                job.last_run_message = str(event.exception)[:500]
                job.failed_runs += 1
                logger.error(f"Job {job_id} failed: {event.exception}")
            else:
                job.last_run_status = 'success'
                job.last_run_message = 'Job completed successfully'
                job.successful_runs += 1
                logger.info(f"Job {job_id} completed successfully")

            job.last_run_at = datetime.utcnow()

            # Update next run time
            scheduled_job = self.scheduler.get_job(job_id)
            if scheduled_job:
                job.next_run_at = scheduled_job.next_run_time

            db.commit()

        except Exception as e:
            logger.error(f"Error in job listener: {e}")
        finally:
            db.close()

    def _run_confluence_sync(self):
        """Run Confluence synchronization"""
        logger.info("Starting scheduled Confluence sync")
        db = SessionLocal()
        try:
            # Update job status to running
            job = db.query(ScheduledJob).filter(ScheduledJob.job_type == 'confluence_sync').first()
            if job:
                job.last_run_status = 'running'
                job.last_run_at = datetime.utcnow()
                db.commit()

            # Run sync
            result = confluence_parser.sync_applications(db)

            logger.info(f"Confluence sync completed: {result.get('new_count', 0)} created, {result.get('updated_count', 0)} updated")

            return result

        except Exception as e:
            logger.error(f"Confluence sync failed: {e}")
            raise
        finally:
            db.close()

    def _run_ai_evaluation(self):
        """Run AI evaluation on pending applications"""
        logger.info("Starting scheduled AI evaluation")
        db = SessionLocal()
        try:
            # Update job status to running
            job = db.query(ScheduledJob).filter(ScheduledJob.job_type == 'ai_evaluation').first()
            if job:
                job.last_run_status = 'running'
                job.last_run_at = datetime.utcnow()
                db.commit()

            # Get pending applications
            applications = db.query(Application).filter(Application.ai_grade.is_(None)).all()

            if not applications:
                logger.info("No pending applications to evaluate")
                return

            # Get evaluation criteria
            criteria_list = db.query(EvaluationCriteria).filter(
                EvaluationCriteria.is_active == True
            ).order_by(EvaluationCriteria.display_order).all()

            # Get AI categories
            categories = db.query(AICategory).filter(AICategory.is_active == True).all()

            # Evaluate each application
            success_count = 0
            fail_count = 0
            total_count = len(applications)

            for app in applications:
                try:
                    # Classify AI technology
                    ai_classifier.classify_and_update(db, app, categories)

                    # Evaluate with LLM
                    success = llm_evaluator.evaluate_application(db, app, criteria_list)

                    if success:
                        success_count += 1
                    else:
                        fail_count += 1

                except Exception as e:
                    logger.error(f"Error evaluating application {app.id}: {e}")
                    fail_count += 1

            result = {
                "total_count": total_count,
                "success_count": success_count,
                "fail_count": fail_count
            }

            logger.info(f"AI evaluation completed: {success_count} success, {fail_count} failed out of {total_count} total")

            return result

        except Exception as e:
            logger.error(f"AI evaluation failed: {e}")
            raise
        finally:
            db.close()


# Global scheduler instance
job_scheduler = JobScheduler()
