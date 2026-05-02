from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import get_conn

router = APIRouter(prefix="/api/map", tags=["map"])


class NodePosition(BaseModel):
    x: float
    y: float


class EdgeIn(BaseModel):
    source_id: int
    target_id: int
    label: str = ""


# ---------------------------------------------------------------------------
# Map data
# ---------------------------------------------------------------------------

@router.get("")
def get_map():
    conn = get_conn()

    # 配置済みノード
    placed = conn.execute(
        "SELECT mn.device_id, mn.x, mn.y, d.name, d.ip_address "
        "FROM map_nodes mn JOIN devices d ON d.id = mn.device_id"
    ).fetchall()

    nodes = []
    for r in placed:
        # 最新 Ping 状態
        ping = conn.execute(
            "SELECT status, response_time FROM ping_results "
            "WHERE device_id=? ORDER BY timestamp DESC LIMIT 1",
            (r["device_id"],),
        ).fetchone()
        status = "unknown"
        rtt = None
        if ping:
            status = "up" if ping["status"] else "down"
            rtt = ping["response_time"]

        # 直近 5 分のトラフィック合計 bps
        traffic = conn.execute(
            "SELECT SUM(in_bps + out_bps) as total FROM snmp_traffic "
            "WHERE device_id=? AND in_bps IS NOT NULL "
            "AND timestamp >= datetime('now','localtime','-5 minutes')",
            (r["device_id"],),
        ).fetchone()
        traffic_bps = float(traffic["total"]) if traffic and traffic["total"] else 0.0

        nodes.append({
            "device_id":   r["device_id"],
            "name":        r["name"],
            "ip_address":  r["ip_address"],
            "x":           r["x"],
            "y":           r["y"],
            "status":      status,
            "rtt":         rtt,
            "traffic_bps": traffic_bps,
        })

    # 接続エッジ
    edges = [dict(e) for e in conn.execute("SELECT * FROM map_edges").fetchall()]

    # 未配置デバイス
    placed_ids = {n["device_id"] for n in nodes}
    unplaced = [
        {"device_id": d["id"], "name": d["name"], "ip_address": d["ip_address"]}
        for d in conn.execute("SELECT id, name, ip_address FROM devices ORDER BY name").fetchall()
        if d["id"] not in placed_ids
    ]

    conn.close()
    return {"nodes": nodes, "edges": edges, "unplaced": unplaced}


# ---------------------------------------------------------------------------
# Node (デバイスをマップに追加・移動・削除)
# ---------------------------------------------------------------------------

@router.post("/nodes/{device_id}", status_code=201)
def add_node(device_id: int, pos: NodePosition = NodePosition(x=0.5, y=0.5)):
    conn = get_conn()
    if not conn.execute("SELECT id FROM devices WHERE id=?", (device_id,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Device not found")
    conn.execute(
        "INSERT OR IGNORE INTO map_nodes (device_id, x, y) VALUES (?,?,?)",
        (device_id, pos.x, pos.y),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


@router.put("/nodes/{device_id}")
def update_node_position(device_id: int, pos: NodePosition):
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO map_nodes (device_id, x, y) VALUES (?,?,?)",
        (device_id, pos.x, pos.y),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


@router.delete("/nodes/{device_id}", status_code=204)
def remove_node(device_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM map_nodes WHERE device_id=?", (device_id,))
    # そのデバイスに関連するエッジも削除
    conn.execute(
        "DELETE FROM map_edges WHERE source_id=? OR target_id=?",
        (device_id, device_id),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Edges (接続線)
# ---------------------------------------------------------------------------

@router.post("/edges", status_code=201)
def add_edge(body: EdgeIn):
    if body.source_id == body.target_id:
        raise HTTPException(status_code=400, detail="同じデバイスには接続できません")
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO map_edges (source_id, target_id, label) VALUES (?,?,?)",
            (body.source_id, body.target_id, body.label),
        )
        conn.commit()
        edge = conn.execute(
            "SELECT * FROM map_edges WHERE id=?", (cur.lastrowid,)
        ).fetchone()
        conn.close()
        return dict(edge)
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/edges/{edge_id}", status_code=204)
def remove_edge(edge_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM map_edges WHERE id=?", (edge_id,))
    conn.commit()
    conn.close()
