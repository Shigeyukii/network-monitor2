from fastapi import APIRouter, Query
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import get_conn

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


def _with_device(alert, conn):
    a = dict(alert)
    row = conn.execute(
        "SELECT name, ip_address FROM devices WHERE id=?", (a["device_id"],)
    ).fetchone()
    a["device_name"]       = row["name"]       if row else "削除済みデバイス"
    a["device_ip_address"] = row["ip_address"] if row else "—"
    return a


@router.get("")
def list_alerts(limit: int = Query(50, ge=1, le=200)):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM alerts ORDER BY timestamp DESC LIMIT ?", (limit,)
    ).fetchall()
    result = [_with_device(r, conn) for r in rows]
    conn.close()
    return result


@router.get("/unread-count")
def unread_count():
    conn = get_conn()
    count = conn.execute(
        "SELECT COUNT(*) FROM alerts WHERE acknowledged=0"
    ).fetchone()[0]
    conn.close()
    return {"count": count}


@router.put("/{alert_id}/acknowledge")
def acknowledge(alert_id: int):
    conn = get_conn()
    conn.execute("UPDATE alerts SET acknowledged=1 WHERE id=?", (alert_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


@router.post("/acknowledge-all")
def acknowledge_all():
    conn = get_conn()
    conn.execute("UPDATE alerts SET acknowledged=1 WHERE acknowledged=0")
    conn.commit()
    conn.close()
    return {"ok": True}
