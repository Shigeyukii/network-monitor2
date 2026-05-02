import io
import csv
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import get_conn

router = APIRouter(prefix="/api/reports", tags=["reports"])

PERIODS = [
    ("1h",  1,   "1時間"),
    ("24h", 24,  "24時間"),
    ("7d",  168, "7日"),
    ("30d", 720, "30日"),
]


def _uptime(device_id: int, hours: int, conn) -> dict:
    rows = conn.execute(
        "SELECT status FROM ping_results "
        "WHERE device_id=? AND timestamp >= datetime('now','localtime',? || ' hours')",
        (device_id, f"-{hours}"),
    ).fetchall()
    total = len(rows)
    if total == 0:
        return {"total": 0, "pct": None}
    up = sum(1 for r in rows if r["status"])
    return {"total": total, "pct": round(up / total * 100, 1)}


def _build_rows(conn):
    devices = conn.execute("SELECT * FROM devices ORDER BY name").fetchall()
    result = []
    for d in devices:
        group = None
        if d["group_id"]:
            g = conn.execute(
                "SELECT name, color FROM groups WHERE id=?", (d["group_id"],)
            ).fetchone()
            group = dict(g) if g else None

        latest = conn.execute(
            "SELECT status, timestamp FROM ping_results "
            "WHERE device_id=? ORDER BY timestamp DESC LIMIT 1",
            (d["id"],),
        ).fetchone()

        uptimes = {key: _uptime(d["id"], hours, conn) for key, hours, _ in PERIODS}

        result.append({
            "id":          d["id"],
            "name":        d["name"],
            "ip_address":  d["ip_address"],
            "group":       group,
            "latest_ping": dict(latest) if latest else None,
            "uptimes":     uptimes,
        })
    return result


@router.get("/uptime")
def uptime_report():
    conn = get_conn()
    result = _build_rows(conn)
    conn.close()
    return result


@router.get("/uptime/csv")
def uptime_csv():
    conn = get_conn()
    rows = _build_rows(conn)
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "デバイス名", "IPアドレス", "グループ",
        "1時間稼働率(%)", "24時間稼働率(%)", "7日稼働率(%)", "30日稼働率(%)",
        "最終確認", "最終ステータス",
    ])

    for r in rows:
        def pct(key):
            v = r["uptimes"].get(key, {}).get("pct")
            return f"{v}" if v is not None else "データなし"

        latest = r["latest_ping"]
        writer.writerow([
            r["name"],
            r["ip_address"],
            r["group"]["name"] if r["group"] else "",
            pct("1h"), pct("24h"), pct("7d"), pct("30d"),
            latest["timestamp"] if latest else "",
            "UP" if latest and latest["status"] else ("DOWN" if latest else "不明"),
        ])

    # UTF-8 BOM付きでExcelで開いても文字化けしない
    encoded = ("﻿" + output.getvalue()).encode("utf-8")
    return StreamingResponse(
        iter([encoded]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=uptime_report.csv"},
    )
