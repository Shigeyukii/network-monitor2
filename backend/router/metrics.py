from fastapi import APIRouter, Query
from typing import Optional
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import get_conn

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


@router.get("/ping/{device_id}")
def ping_history(device_id: int, hours: int = Query(24, ge=1, le=168)):
    conn = get_conn()
    rows = conn.execute(
        """SELECT timestamp, status, response_time FROM ping_results
           WHERE device_id=?
             AND timestamp >= datetime('now','localtime',? || ' hours')
           ORDER BY timestamp ASC""",
        (device_id, f"-{hours}"),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.get("/traffic/{device_id}")
def traffic(
    device_id: int,
    if_index: Optional[int] = None,
    hours: int = Query(24, ge=1, le=168),
):
    conn = get_conn()
    if if_index is not None:
        ifaces = conn.execute(
            "SELECT * FROM snmp_interfaces WHERE device_id=? AND if_index=?",
            (device_id, if_index),
        ).fetchall()
    else:
        ifaces = conn.execute(
            "SELECT * FROM snmp_interfaces WHERE device_id=?", (device_id,)
        ).fetchall()

    result = []
    for iface in ifaces:
        rows = conn.execute(
            """SELECT timestamp, in_bps, out_bps FROM snmp_traffic
               WHERE device_id=? AND if_index=?
                 AND timestamp >= datetime('now','localtime',? || ' hours')
                 AND in_bps IS NOT NULL
               ORDER BY timestamp ASC""",
            (device_id, iface["if_index"], f"-{hours}"),
        ).fetchall()
        result.append(
            {
                "if_index": iface["if_index"],
                "if_name":  iface["if_name"],
                "if_speed": iface["if_speed"],
                "data":     [dict(r) for r in rows],
            }
        )
    conn.close()
    return result


@router.get("/summary")
def summary():
    conn = get_conn()
    devices = conn.execute("SELECT id FROM devices").fetchall()
    total = len(devices)
    up = down = unknown = 0
    for d in devices:
        row = conn.execute(
            "SELECT status FROM ping_results WHERE device_id=? ORDER BY timestamp DESC LIMIT 1",
            (d["id"],),
        ).fetchone()
        if row is None:
            unknown += 1
        elif row["status"]:
            up += 1
        else:
            down += 1
    conn.close()
    return {"total": total, "up": up, "down": down, "unknown": unknown}
