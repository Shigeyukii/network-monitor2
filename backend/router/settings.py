from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator
from typing import Optional
from urllib.parse import urlparse
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import get_conn

# 許可する Webhook ホスト（SSRF 対策）
_ALLOWED_WEBHOOK_HOSTS = {
    "outlook.office.com",
    "outlook.office365.com",
    "hooks.slack.com",
    "discord.com",
    "hooks.office.com",
}

router = APIRouter(prefix="/api/settings", tags=["settings"])

# 数値として扱うキー（それ以外は文字列）
_NUMERIC = {"ping_interval", "snmp_interval", "notify_on_down", "notify_on_recovery",
            "trap_enabled", "trap_port"}


def _cast(key: str, value: str):
    if key in _NUMERIC:
        return int(value) if value else 0
    return value


def _validate_webhook_url(v: Optional[str]) -> Optional[str]:
    if not v:
        return v
    parsed = urlparse(v)
    if parsed.scheme != "https":
        raise ValueError("Webhook URL は https:// で始まる必要があります")
    host = parsed.hostname or ""
    if not any(host == h or host.endswith("." + h) for h in _ALLOWED_WEBHOOK_HOSTS):
        allowed = ", ".join(sorted(_ALLOWED_WEBHOOK_HOSTS))
        raise ValueError(f"Webhook URL のホストが許可されていません。許可ホスト: {allowed}")
    return v


class SettingsIn(BaseModel):
    ping_interval:      Optional[int] = None
    snmp_interval:      Optional[int] = None
    teams_webhook_url:  Optional[str] = None
    slack_webhook_url:  Optional[str] = None
    notify_on_down:     Optional[int] = None
    notify_on_recovery: Optional[int] = None
    trap_enabled:       Optional[int] = None
    trap_port:          Optional[int] = None

    @field_validator("teams_webhook_url", "slack_webhook_url")
    @classmethod
    def validate_webhook(cls, v: Optional[str]) -> Optional[str]:
        return _validate_webhook_url(v)


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

    # SSRF 対策: URL を同じルールで検証する
    try:
        _validate_webhook_url(url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if target == "teams":
        ok = send_teams(url, "テストデバイス", "192.168.0.1", "down", "テスト送信")
    elif target == "slack":
        ok = send_slack(url, "テストデバイス", "192.168.0.1", "down", "テスト送信")
    else:
        return {"ok": False, "detail": "不明な target"}

    return {"ok": ok}
