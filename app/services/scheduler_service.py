import threading
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.executors.pool import ThreadPoolExecutor
from loguru import logger
from app.database.db import db_conn, db_transaction
from app.services.transfer_service import TransferService

class SchedulerService:
    """Manages APScheduler background jobs, scheduling triggers, and manual task execution."""
    
    _scheduler = None
    _lock = threading.Lock()

    @staticmethod
    def get_scheduler() -> BackgroundScheduler:
        """Returns the single scheduler instance, initializing it if necessary."""
        with SchedulerService._lock:
            if SchedulerService._scheduler is None:
                executors = {
                    'default': ThreadPoolExecutor(max_workers=5)
                }
                job_defaults = {
                    'coalesce': True,
                    'max_instances': 1 # Critical constraint from AGENTS.md
                }
                SchedulerService._scheduler = BackgroundScheduler(
                    executors=executors,
                    job_defaults=job_defaults,
                    timezone='Asia/Shanghai'
                )
            return SchedulerService._scheduler

    @staticmethod
    def start():
        """Starts the background scheduler and loads enabled jobs from database."""
        sched = SchedulerService.get_scheduler()
        if not sched.running:
            sched.start()
            logger.info("Background scheduler started.")
            
            # Register daily log cleanup job at 3:00 AM daily to prevent DB bloat
            try:
                if sched.get_job("daily_log_cleanup"):
                    sched.remove_job("daily_log_cleanup")
                sched.add_job(
                    func=SchedulerService.cleanup_old_runs,
                    trigger='cron',
                    hour=3,
                    minute=0,
                    id='daily_log_cleanup',
                    name='Daily Database Logs Cleanup'
                )
                logger.info("Scheduled daily database logs cleanup task at 3:00 AM.")
            except Exception as e:
                logger.error(f"Failed to schedule daily database logs cleanup: {e}")
                
            SchedulerService.reload_jobs()

    @staticmethod
    def shutdown():
        """Stops the background scheduler."""
        sched = SchedulerService.get_scheduler()
        if sched.running:
            sched.shutdown(wait=False)
            logger.info("Background scheduler shut down.")

    @staticmethod
    def reload_jobs():
        """Clears all scheduled jobs and reloads enabled ones from database."""
        sched = SchedulerService.get_scheduler()
        sched.remove_all_jobs()
        logger.info("Reloading enabled subscription jobs...")
        
        with db_conn() as conn:
            enabled_subs = conn.execute("SELECT id, name, cron_expression FROM subscriptions WHERE enabled = 1").fetchall()
            
        for sub in enabled_subs:
            try:
                SchedulerService.add_subscription_job(sub["id"], sub["cron_expression"], sub["name"])
            except Exception as e:
                logger.error(f"Failed to schedule job '{sub['name']}' (ID: {sub['id']}): {e}")

    @staticmethod
    def add_subscription_job(subscription_id: int, cron_expr: str, name: str = ""):
        """Schedules a new recurring job for a subscription. Removes any existing job first."""
        sched = SchedulerService.get_scheduler()
        job_id = f"sub_{subscription_id}"
        
        # Remove existing if present
        if sched.get_job(job_id):
            sched.remove_job(job_id)
            
        # Parse cron expression
        try:
            trigger = CronTrigger.from_crontab(cron_expr)
        except Exception as e:
            logger.error(f"Invalid cron expression '{cron_expr}' for subscription {subscription_id}: {e}. Falling back to default.")
            trigger = CronTrigger.from_crontab("0 2 * * *") # Default 2 AM daily
            
        sched.add_job(
            func=SchedulerService.run_job_wrapper,
            args=[subscription_id, "scheduler"],
            id=job_id,
            name=name or f"Subscription Task {subscription_id}",
            trigger=trigger
        )
        logger.info(f"Scheduled job '{name}' (ID: {subscription_id}) with cron: {cron_expr}")

    @staticmethod
    def remove_subscription_job(subscription_id: int):
        """Cancels and removes the scheduled job for a subscription."""
        sched = SchedulerService.get_scheduler()
        job_id = f"sub_{subscription_id}"
        if sched.get_job(job_id):
            sched.remove_job(job_id)
            logger.info(f"Removed scheduled job for subscription {subscription_id}")

    @staticmethod
    def trigger_now(subscription_id: int):
        """Launches task execution immediately in a background thread."""
        logger.info(f"Manual trigger requested for subscription {subscription_id}")
        t = threading.Thread(
            target=SchedulerService.run_job_wrapper,
            args=[subscription_id, "manual"],
            daemon=True
        )
        t.start()

    @staticmethod
    def run_job_wrapper(subscription_id: int, trigger_type: str = "scheduler"):
        """Wrapper method verifying concurrency limits before executing the actual transfer job."""
        # 1. Double check concurrency status in DB
        with db_conn() as conn:
            running_run = conn.execute("""
            SELECT id FROM task_runs WHERE subscription_id = ? AND status = 'running'
            """, (subscription_id,)).fetchone()
            
            if running_run:
                logger.warning(
                    f"Job execution skipped for subscription {subscription_id}. "
                    f"Another execution is already active (Run ID: {running_run['id']})."
                )
                return

        # 2. Run the actual transfer service
        try:
            run_id = TransferService.execute_run(subscription_id, trigger_type)
            # Update next_run_at calculation
            SchedulerService._update_next_run_at(subscription_id)
        except Exception as e:
            logger.error(f"Failed executing job for subscription {subscription_id}: {e}")

    @staticmethod
    def _update_next_run_at(subscription_id: int):
        """Calculates and updates the next run timestamp in the database."""
        sched = SchedulerService.get_scheduler()
        job_id = f"sub_{subscription_id}"
        job = sched.get_job(job_id)
        if job and job.next_run_time:
            next_run_str = job.next_run_time.strftime("%Y-%m-%d %H:%M:%S")
            with db_transaction() as conn:
                conn.execute("""
                UPDATE subscriptions SET next_run_at = ? WHERE id = ?
                """, (next_run_str, subscription_id))
                
    @staticmethod
    def cleanup_old_runs(days_limit: int = 30):
        """Deletes task runs and cascaded operation logs older than the specified days to prevent database bloat."""
        import datetime
        cutoff_date = (datetime.datetime.now() - datetime.timedelta(days=days_limit)).strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"Starting daily database logs cleanup. Cutoff date: {cutoff_date}")
        try:
            with db_transaction() as conn:
                cursor = conn.execute("DELETE FROM task_runs WHERE started_at < ?", (cutoff_date,))
                deleted_count = cursor.rowcount
            logger.info(f"Database logs cleanup completed. Deleted {deleted_count} old task run records.")
        except Exception as e:
            logger.error(f"Failed to cleanup old database logs: {e}")
