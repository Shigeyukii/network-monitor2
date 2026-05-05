from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import get_conn

router = APIRouter(prefix="/api/devices", tags=["devices"])


class DeviceIn(BaseModel):
    name: str
    ip_address: str
    snmp_enabled: bool = False
    snmp_community: str = "public"
    snmp_port: int = 161
    snmp_version: str = "v2c"
    ping_interval: int = 60
    group_id: Optional[int] = None


class DeviceUpdate(BaseModel):
    name: Optional[str] = None
    ip_address: Optional[str] = None
    snmp_enabled: Optional[bool] = None
    snmp_community: Optional[str] = None
    snmp_port: Optional[int] = None
    snmp_version: Optional[str] = None
    ping_interval: Optional[int] = None
    group_id: Optional[int] = None


def _with_status(device, conn):
    d = dict(device)
    latest = conn.execute(
        "SELECT status, response_time, timestamp FROM ping_results "
        "WHERE device_id=? ORDER BY timestamp DESC LIMIT 1",
        (d["id"],),
    ).fetchone()
    d["latest_ping"] = dict(latest) if latest else None

    group = None
    if d.get("group_id"):
        row = conn.execute("SELECT id, name, color FROM groups WHERE id=?", (d["group_id"],)).fetchone()
        group = dict(row) if row else None
    d["group"] = group
    return d


@router.get("")
def list_devices():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM devices ORDER BY name").fetchall()
    result = [_with_status(r, conn) for r in rows]
    conn.close()
    return result


@router.post("", status_code=201)
def create_device(body: DeviceIn):
    conn = get_conn()
    try:
        cur = conn.execute(
            """INSERT INTO devices (name, ip_address, snmp_enabled, snmp_community,
                                    snmp_port, snmp_version, ping_interval, group_id)
               VALUES (?,?,?,?,?,?,?,?)""",
            (body.name, body.ip_address, int(body.snmp_enabled),
             body.snmp_community, body.snmp_port, body.snmp_version, body.ping_interval,
             body.group_id),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM devices WHERE id=?", (cur.lastrowid,)).fetchone()
        result = _with_status(row, conn)
        conn.close()
        return result
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{device_id}")
def get_device(device_id: int):
    conn = get_conn()
    row = conn.execute("SELECT * FROM devices WHERE id=?", (device_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Not found")
    result = _with_status(row, conn)
    conn.close()
    return result


@router.put("/{device_id}")
def update_device(device_id: int, body: DeviceUpdate):
    conn = get_conn()
    if not conn.execute("SELECT id FROM devices WHERE id=?", (device_id,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Not found")

    # group_id=0 は「グループなし」を意味するので None に変換
    body_dict = body.dict()
    if body_dict.get("group_id") == 0:
        body_dict["group_id"] = None

    updates = {k: v for k, v in body_dict.items() if v is not None}
    if "snmp_enabled" in body_dict and body_dict["snmp_enabled"] is not None:
        updates["snmp_enabled"] = int(body_dict["snmp_enabled"])
    # group_id は None（未グループ）も明示的に更新できるよう別途処理
    if "group_id" in body_dict:
        updates["group_id"] = body_dict["group_id"]

    if updates:
        set_clause = ", ".join(f"{k}=?" for k in updates)
        conn.execute(
            f"UPDATE devices SET {set_clause} WHERE id=?",
            list(updates.values()) + [device_id],
        )
        conn.commit()

    row = conn.execute("SELECT * FROM devices WHERE id=?", (device_id,)).fetchone()
    result = _with_status(row, conn)
    conn.close()
    return result


@router.delete("/{device_id}", status_code=204)
def delete_device(device_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM devices WHERE id=?", (device_id,))
    conn.commit()
    conn.close()


@router.put("/{device_id}/maintenance")
def set_maintenance(device_id: int, body: dict):
    """メンテナンスモードの ON / OFF を切り替える。"""
    enabled = int(bool(body.get("enabled", False)))
    conn = get_conn()
    if not conn.execute("SELECT id FROM devices WHERE id=?", (device_id,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Not found")
    conn.execute("UPDATE devices SET maintenance=? WHERE id=?", (enabled, device_id))
    conn.commit()
    row = conn.execute("SELECT * FROM devices WHERE id=?", (device_id,)).fetchone()
    result = _with_status(row, conn)
    conn.close()
    return result
