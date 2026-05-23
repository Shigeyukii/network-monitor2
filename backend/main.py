import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from database import init_db, get_settings, cleanup_old_data
from poller import poll_ping, poll_snmp, poll_ports
from scheduler import scheduler, reschedule
from auth import auth_enabled, verify_password, create_token, revoke_token, check_token, set_password
from router import devices, metrics, settings as settings_router, groups, alerts, ports, reports, importexport, networkmap, traps
from trap_receiver import trap_receiver
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
    rows = conn.execute(
        "SELECT id, ip_address FROM devices WHERE maintenance=0"
    ).fetchall()
    conn.close()
    for row in rows:
        poll_ping(row["id"], row["ip_address"])
        poll_ports(row["id"], row["ip_address"])


def run_snmp_polls():
    conn = __import__("database").get_conn()
    rows = conn.execute(
        "SELECT id, ip_address, snmp_community, snmp_port, snmp_version "
        "FROM devices WHERE snmp_enabled=1 AND maintenance=0"
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

    # SNMP トラップ受信器
    cfg = get_settings()
    if str(cfg.get("trap_enabled", "0")) == "1":
        trap_receiver.start(int(cfg.get("trap_port", 1620)))

    yield

    trap_receiver.stop()
    scheduler.shutdown()
    logger.info("Scheduler stopped")


app = FastAPI(title="Network Monitor", lifespan=lifespan)

# ---------------------------------------------------------------------------
# 認証ミドルウェア
# ---------------------------------------------------------------------------

# 認証不要なパス（ログイン・ステータス確認・静的ファイル・フロントエンド）
_AUTH_EXEMPT = {"/api/auth/login", "/api/auth/status"}


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/") and path not in _AUTH_EXEMPT:
        if auth_enabled():
            auth_header = request.headers.get("Authorization", "")
            token = auth_header.removeprefix("Bearer ").strip()
            if not check_token(token):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "認証が必要です"},
                    headers={"WWW-Authenticate": "Bearer"},
                )
    return await call_next(request)


# ---------------------------------------------------------------------------
# 認証エンドポイント
# ---------------------------------------------------------------------------

@app.get("/api/auth/status", tags=["auth"])
def get_auth_status():
    return {"auth_enabled": auth_enabled()}


@app.post("/api/auth/login", tags=["auth"])
async def login(request: Request):
    body = await request.json()
    password = body.get("password", "")
    if verify_password(password):
        token = create_token()
        return {"ok": True, "token": token}
    raise HTTPException(status_code=401, detail="パスワードが違います")


@app.post("/api/auth/logout", tags=["auth"])
async def logout(request: Request):
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.removeprefix("Bearer ").strip()
    revoke_token(token)
    return {"ok": True}


@app.put("/api/auth/password", tags=["auth"])
async def change_password(request: Request):
    body = await request.json()
    new_password = body.get("password", "")
    set_password(new_password)
    msg = "パスワードを設定しました" if new_password else "パスワード認証を無効化しました"
    return {"ok": True, "detail": msg}

app.include_router(groups.router)
app.include_router(devices.router)
app.include_router(metrics.router)
app.include_router(settings_router.router)
app.include_router(alerts.router)
app.include_router(ports.router)
app.include_router(reports.router)
app.include_router(importexport.router)
app.include_router(networkmap.router)
app.include_router(traps.router)


@app.post("/api/settings/restart-trap", tags=["settings"])
def restart_trap():
    """設定変更後にトラップ受信器を再起動する。"""
    trap_receiver.stop()
    cfg = get_settings()
    if str(cfg.get("trap_enabled", "0")) == "1":
        trap_receiver.start(int(cfg.get("trap_port", 1620)))
        return {"ok": True, "running": True, "port": int(cfg.get("trap_port", 1620))}
    return {"ok": True, "running": False}


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
