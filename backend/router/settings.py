from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import get_conn

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsIn(BaseModel):
    ping_interval: Optional[int] = None
    snmp_interval: Optional[int] = None


@router.get("")
def get_settings():
    conn = get_conn()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    return {r["key"]: int(r["value"]) for r in rows}


@router.put("")
def update_settings(body: SettingsIn):
    conn = get_conn()
    if body.ping_interval is not None:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('ping_interval', ?)",
            (str(body.ping_interval),),
        )
    if body.snmp_interval is not None:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('snmp_interval', ?)",
            (str(body.snmp_interval),),
        )
    conn.commit()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    result = {r["key"]: int(r["value"]) for r in rows}
    return result
