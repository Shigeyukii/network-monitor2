import json
from fastapi import APIRouter, Query
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import get_conn

router = APIRouter(prefix="/api/traps", tags=["traps"])


@router.get("")
def list_traps(limit: int = Query(100, ge=1, le=500)):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM traps ORDER BY timestamp DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        try:
            d["varbinds"] = json.loads(d["varbinds"])
        except Exception:
            d["varbinds"] = []
        result.append(d)
    return result


@router.get("/unread-count")
def unread_count():
    conn = get_conn()
    count = conn.execute(
        "SELECT COUNT(*) FROM traps WHERE acknowledged=0"
    ).fetchone()[0]
    conn.close()
    return {"count": count}


@router.put("/{trap_id}/acknowledge")
def acknowledge(trap_id: int):
    conn = get_conn()
    conn.execute("UPDATE traps SET acknowledged=1 WHERE id=?", (trap_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


@router.post("/acknowledge-all")
def acknowledge_all():
    conn = get_conn()
    conn.execute("UPDATE traps SET acknowledged=1 WHERE acknowledged=0")
    conn.commit()
    conn.close()
    return {"ok": True}


@router.delete("/clear", status_code=204)
def clear_all():
    """既読トラップをすべて削除。"""
    conn = get_conn()
    conn.execute("DELETE FROM traps WHERE acknowledged=1")
    conn.commit()
    conn.close()
