from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import get_conn

router = APIRouter(prefix="/api/devices/{device_id}/ports", tags=["ports"])


class PortIn(BaseModel):
    port:  int
    label: str = ""


def _with_latest(check, conn):
    c = dict(check)
    latest = conn.execute(
        "SELECT status, response_time, timestamp FROM port_results "
        "WHERE device_id=? AND port=? ORDER BY timestamp DESC LIMIT 1",
        (c["device_id"], c["port"]),
    ).fetchone()
    c["latest"] = dict(latest) if latest else None
    return c


@router.get("")
def list_ports(device_id: int):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM port_checks WHERE device_id=? ORDER BY port",
        (device_id,),
    ).fetchall()
    result = [_with_latest(r, conn) for r in rows]
    conn.close()
    return result


@router.post("", status_code=201)
def add_port(device_id: int, body: PortIn):
    if not (1 <= body.port <= 65535):
        raise HTTPException(status_code=400, detail="ポート番号は 1〜65535 で指定してください")
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO port_checks (device_id, port, label) VALUES (?,?,?)",
            (device_id, body.port, body.label),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM port_checks WHERE device_id=? AND port=?",
            (device_id, body.port),
        ).fetchone()
        result = _with_latest(row, conn)
        conn.close()
        return result
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{port}", status_code=204)
def remove_port(device_id: int, port: int):
    conn = get_conn()
    conn.execute(
        "DELETE FROM port_checks WHERE device_id=? AND port=?", (device_id, port)
    )
    conn.commit()
    conn.close()


@router.get("/history")
def port_history(
    device_id: int,
    port: int = Query(...),
    hours: int = Query(24, ge=1, le=168),
):
    conn = get_conn()
    rows = conn.execute(
        """SELECT timestamp, status, response_time FROM port_results
           WHERE device_id=? AND port=?
             AND timestamp >= datetime('now','localtime',? || ' hours')
           ORDER BY timestamp ASC""",
        (device_id, port, f"-{hours}"),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
