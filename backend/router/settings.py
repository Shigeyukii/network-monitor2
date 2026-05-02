from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import get_conn

router = APIRouter(prefix="/api/settings", tags=["settings"])

# 数値として扱うキー（それ以外は文字列）
_NUMERIC = {"ping_interval", "snmp_interval", "notify_on_down", "notify_on_recovery",
            "trap_enabled", "trap_port"}


def _cast(key: str, value: str):
    if key in _NUMERIC:
        return int(value) if value else 0
    return value


class SettingsIn(BaseModel):
    ping_interval:      Optional[int] = None
    snmp_interval:      Optional[int] = None
    teams_webhook_url:  Optional[str] = None
    slack_webhook_url:  Optional[str] = None
    notify_on_down:     Optional[int] = None
    notify_on_recovery: Optional[int] = None
    trap_enabled:       Optional[int] = None
    trap_port:          Optional[int] = None


@router.get("")
def get_settings():
    conn = get_conn()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    return {r["key"]: _cast(r["key"], r["value"]) for r in rows}


@router.put("")
def update_settings(body: SettingsIn):
    conn = get_conn()
    for key, val in body.dict().items():
        if val is not None:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, str(val)),
            )
    conn.commit()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    return {r["key"]: _cast(r["key"], r["value"]) for r in rows}


@router.post("/test-notify")
def test_notify(body: dict):
    """Webhook の疎通テスト用エンドポイント。"""
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from notifier import send_teams, send_slack

    target = body.get("target")   # "teams" | "slack"
    url    = body.get("url", "").strip()
    if not url:
        return {"ok": False, "detail": "URL が未入力です"}

    if target == "teams":
        ok = send_teams(url, "テストデバイス", "192.168.0.1", "down", "テスト送信")
    elif target == "slack":
        ok = send_slack(url, "テストデバイス", "192.168.0.1", "down", "テスト送信")
    else:
        return {"ok": False, "detail": "不明な target"}

    return {"ok": ok}
