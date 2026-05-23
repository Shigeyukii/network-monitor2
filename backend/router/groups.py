from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator
from typing import Optional
import re
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import get_conn

router = APIRouter(prefix="/api/groups", tags=["groups"])

_COLOR_RE = re.compile(r'^#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?$')


class GroupIn(BaseModel):
    name: str
    color: str = "#58a6ff"

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: str) -> str:
        if not _COLOR_RE.match(v):
            raise ValueError("color は #RGB または #RRGGBB 形式で入力してください")
        return v


class GroupUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not _COLOR_RE.match(v):
            raise ValueError("color は #RGB または #RRGGBB 形式で入力してください")
        return v


def _with_stats(group, conn):
    g = dict(group)
    rows = conn.execute(
        "SELECT id FROM devices WHERE group_id=?", (g["id"],)
    ).fetchall()
    device_ids = [r["id"] for r in rows]
    g["device_count"] = len(device_ids)

    up = down = unknown = 0
    for did in device_ids:
        latest = conn.execute(
            "SELECT status FROM ping_results WHERE device_id=? ORDER BY timestamp DESC LIMIT 1",
            (did,),
        ).fetchone()
        if latest is None:
            unknown += 1
        elif latest["status"]:
            up += 1
        else:
            down += 1
    g["up"] = up
    g["down"] = down
    g["unknown"] = unknown
    return g


@router.get("")
def list_groups():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM groups ORDER BY name").fetchall()
    result = [_with_stats(r, conn) for r in rows]
    conn.close()
    return result


@router.post("", status_code=201)
def create_group(body: GroupIn):
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO groups (name, color) VALUES (?,?)",
            (body.name, body.color),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM groups WHERE id=?", (cur.lastrowid,)).fetchone()
        result = _with_stats(row, conn)
        conn.close()
        return result
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{group_id}")
def update_group(group_id: int, body: GroupUpdate):
    conn = get_conn()
    if not conn.execute("SELECT id FROM groups WHERE id=?", (group_id,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Not found")

    updates = {k: v for k, v in body.dict().items() if v is not None}
    if updates:
        set_clause = ", ".join(f"{k}=?" for k in updates)
        conn.execute(
            f"UPDATE groups SET {set_clause} WHERE id=?",
            list(updates.values()) + [group_id],
        )
        conn.commit()

    row = conn.execute("SELECT * FROM groups WHERE id=?", (group_id,)).fetchone()
    result = _with_stats(row, conn)
    conn.close()
    return result


@router.delete("/{group_id}", status_code=204)
def delete_group(group_id: int):
    conn = get_conn()
    # group_id は ON DELETE SET NULL なので devices は自動的に未グループになる
    conn.execute("DELETE FROM groups WHERE id=?", (group_id,))
    conn.commit()
    conn.close()
