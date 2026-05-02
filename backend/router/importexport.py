import json
import datetime
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, Response
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import get_conn

router = APIRouter(prefix="/api", tags=["import/export"])

EXPORT_VERSION = 1


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

@router.get("/export")
def export_config():
    """デバイス・グループ・ポート設定を JSON ファイルとしてダウンロード。"""
    conn = get_conn()

    # グループ
    groups = [
        {"name": r["name"], "color": r["color"]}
        for r in conn.execute("SELECT name, color FROM groups ORDER BY name").fetchall()
    ]

    # デバイス（ポート設定含む）
    devices = []
    for d in conn.execute("SELECT * FROM devices ORDER BY name").fetchall():
        group_name = None
        if d["group_id"]:
            g = conn.execute("SELECT name FROM groups WHERE id=?", (d["group_id"],)).fetchone()
            group_name = g["name"] if g else None

        ports = [
            {"port": p["port"], "label": p["label"]}
            for p in conn.execute(
                "SELECT port, label FROM port_checks WHERE device_id=? ORDER BY port",
                (d["id"],),
            ).fetchall()
        ]

        devices.append({
            "name":           d["name"],
            "ip_address":     d["ip_address"],
            "group_name":     group_name,
            "ping_interval":  d["ping_interval"],
            "snmp_enabled":   bool(d["snmp_enabled"]),
            "snmp_community": d["snmp_community"],
            "snmp_port":      d["snmp_port"],
            "snmp_version":   d["snmp_version"],
            "ports":          ports,
        })

    conn.close()

    payload = {
        "version":     EXPORT_VERSION,
        "exported_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "groups":      groups,
        "devices":     devices,
    }

    content = json.dumps(payload, ensure_ascii=False, indent=2)
    filename = f"network-monitor-{datetime.date.today()}.json"
    return Response(
        content=content.encode("utf-8"),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

@router.post("/import")
def import_config(body: dict):
    """JSON データからデバイス・グループ・ポート設定を一括登録。"""
    version = body.get("version")
    if version != EXPORT_VERSION:
        raise HTTPException(
            status_code=400,
            detail=f"非対応のバージョンです (version={version})",
        )

    groups_data  = body.get("groups",  [])
    devices_data = body.get("devices", [])

    conn = get_conn()

    # --- グループのインポート ---
    groups_created = 0
    groups_skipped = 0
    group_name_to_id: dict[str, int] = {}

    # 既存グループを先に読み込む
    for row in conn.execute("SELECT id, name FROM groups").fetchall():
        group_name_to_id[row["name"]] = row["id"]

    for g in groups_data:
        name  = g.get("name", "").strip()
        color = g.get("color", "#58a6ff")
        if not name:
            continue
        if name in group_name_to_id:
            groups_skipped += 1
        else:
            cur = conn.execute(
                "INSERT INTO groups (name, color) VALUES (?,?)", (name, color)
            )
            group_name_to_id[name] = cur.lastrowid
            groups_created += 1

    conn.commit()

    # --- デバイスのインポート ---
    devices_created = 0
    devices_skipped = 0
    ports_created   = 0

    # 既存デバイスの IP セット
    existing_ips = {
        r["ip_address"]
        for r in conn.execute("SELECT ip_address FROM devices").fetchall()
    }

    for d in devices_data:
        ip = d.get("ip_address", "").strip()
        if not ip:
            continue

        if ip in existing_ips:
            devices_skipped += 1
            continue

        group_id   = group_name_to_id.get(d.get("group_name")) if d.get("group_name") else None
        snmp_en    = int(bool(d.get("snmp_enabled", False)))

        cur = conn.execute(
            """INSERT INTO devices
               (name, ip_address, group_id, ping_interval,
                snmp_enabled, snmp_community, snmp_port, snmp_version)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                d.get("name", ip),
                ip,
                group_id,
                d.get("ping_interval", 60),
                snmp_en,
                d.get("snmp_community", "public"),
                d.get("snmp_port", 161),
                d.get("snmp_version", "v2c"),
            ),
        )
        device_id = cur.lastrowid
        existing_ips.add(ip)
        devices_created += 1

        for p in d.get("ports", []):
            port  = p.get("port")
            label = p.get("label", "")
            if port and 1 <= port <= 65535:
                try:
                    conn.execute(
                        "INSERT INTO port_checks (device_id, port, label) VALUES (?,?,?)",
                        (device_id, port, label),
                    )
                    ports_created += 1
                except Exception:
                    pass  # UNIQUE 制約違反などは無視

    conn.commit()
    conn.close()

    return {
        "ok":              True,
        "groups_created":  groups_created,
        "groups_skipped":  groups_skipped,
        "devices_created": devices_created,
        "devices_skipped": devices_skipped,
        "ports_created":   ports_created,
    }
