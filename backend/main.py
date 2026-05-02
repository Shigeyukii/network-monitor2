import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from database import init_db, get_settings, cleanup_old_data
from poller import poll_ping, poll_snmp
from scheduler import scheduler, reschedule
from router import devices, metrics, settings as settings_router, groups, alerts
from apscheduler.triggers.interval import IntervalTrigger

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

FRONTEND_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend"
)


def run_ping_polls():
    conn = __import__("database").get_conn()
    rows = conn.execute("SELECT id, ip_address FROM devices").fetchall()
    conn.close()
    for row in rows:
        poll_ping(row["id"], row["ip_address"])


def run_snmp_polls():
    conn = __import__("database").get_conn()
    rows = conn.execute(
        "SELECT id, ip_address, snmp_community, snmp_port, snmp_version "
        "FROM devices WHERE snmp_enabled=1"
    ).fetchall()
    conn.close()
    for row in rows:
        poll_snmp(
            row["id"], row["ip_address"],
            row["snmp_community"], row["snmp_port"], row["snmp_version"],
        )


def apply_schedule():
    cfg = get_settings()
    reschedule("ping", run_ping_polls, int(cfg.get("ping_interval", 60)))
    reschedule("snmp", run_snmp_polls, int(cfg.get("snmp_interval", 60)))


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    apply_schedule()
    scheduler.add_job(
        cleanup_old_data,
        IntervalTrigger(hours=24),
        id="cleanup",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started")
    yield
    scheduler.shutdown()
    logger.info("Scheduler stopped")


app = FastAPI(title="Network Monitor", lifespan=lifespan)

app.include_router(groups.router)
app.include_router(devices.router)
app.include_router(metrics.router)
app.include_router(settings_router.router)
app.include_router(alerts.router)


@app.post("/api/settings/reschedule", tags=["settings"])
def reschedule_jobs():
    """Re-apply polling intervals from DB to the scheduler (call after settings update)."""
    apply_schedule()
    return {"ok": True}


# Serve frontend static assets
app.mount(
    "/static",
    StaticFiles(directory=os.path.join(FRONTEND_DIR, "static")),
    name="static",
)


@app.get("/")
def serve_index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
