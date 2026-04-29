from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import logging

logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler(timezone="Asia/Tokyo")


def reschedule(job_id: str, func, seconds: int):
    if scheduler.get_job(job_id):
        scheduler.reschedule_job(job_id, trigger=IntervalTrigger(seconds=seconds))
        logger.info("rescheduled %s every %ds", job_id, seconds)
    else:
        scheduler.add_job(func, IntervalTrigger(seconds=seconds), id=job_id)
        logger.info("scheduled %s every %ds", job_id, seconds)
