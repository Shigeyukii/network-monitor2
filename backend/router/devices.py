from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator
from typing import Optional
import ipaddress
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import get_conn

router = APIRouter(prefix="/api/devices", tags=["devices"])

_SNMP_VERSIONS = {"v1", "v2c"}


def _validate_ip(v: str) -> str:
    try:
        ipaddress.ip_address(v)
    except ValueError:
        raise ValueError(f"'{v}' は有効な IPv4/IPv6 アドレスではありません")
    return v


class DeviceIn(BaseModel):
    name: str
    ip_address: str
    snmp_enabled: bool = False
    snmp_community: str = "public"
    snmp_port: int = 161
    snmp_version: str = "v2c"
    ping_interval: int = 60
    group_id: Optional[int] = None
    rtt_threshold_ms: Optional[int] = None

    @field_validator("ip_address")
    @classmethod
    def validate_ip(cls, v: str) -> str:
        return _validate_ip(v)

    @field_validator("snmp_version")
    @classmethod
    def validate_snmp_version(cls, v: str) -> str:
        if v not in _SNMP_VERSIONS:
            raise ValueError(f"snmp_version は {_SNMP_VERSIONS} のいずれかを指定してください")
        return v

    @field_validator("ping_interval")
    @classmethod
    def validate_ping_interval(cls, v: int) -> int:
        if v < 5 or v > 3600:
            raise ValueError("ping_interval は 5〜3600 秒の範囲で指定してください")
        return v


class DeviceUpdate(BaseModel):
    name: Optional[str] = None
    ip_address: Optional[str] = None
    snmp_enabled: Optional[bool] = None
    snmp_community: Optional[str] = None
    snmp_port: Optional[int] = None
    snmp_version: Optional[str] = None
    ping_interval: Optional[int] = None
    group_id: Optional[int] = None
    rtt_threshold_ms: Optional[int] = None

    @field_validator("ip_address")
    @classmethod
    def validate_ip(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return _validate_ip(v)
        return v

    @field_validator("snmp_version")
    @classmethod
    def validate_snmp_version(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _SNMP_VERSIONS:
            raise ValueError(f"snmp_version は {_SNMP_VERSIONS} のいずれかを指定してください")
        return v

    @field_validator("ping_interval")
    @classmethod
    def validate_ping_interval(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and (v < 5 or v > 3600):
            raise ValueError("ping_interval は 5〜3600 秒の範囲で指定してください")
        return v


def _with_status(device, conn, *, mask_community: bool = True):
    d = dict(device)
    if mask_community:
        # 一覧取得時は SNMP コミュニティ文字列をマスク（詳細ビューのみ平文で返す）
        if d.get("snmp_community"):
            d["snmp_community"] = "****"
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
                                    snmp_port, snmp_version, ping_interval, group_id,
                                    rtt_threshold_ms)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (body.name, body.ip_address, int(body.snmp_enabled),
             body.snmp_community, body.snmp_port, body.snmp_version, body.ping_interval,
             body.group_id, body.rtt_threshold_ms),
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
    # 詳細ビューでは編集フォームのためコミュニティ文字列をそのまま返す
    result = _with_status(row, conn, mask_community=False)
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
    # group_id / rtt_threshold_ms は None（無効化）も明示的に更新できるよう別途処理
    if "group_id" in body_dict:
        updates["group_id"] = body_dict["group_id"]
    if "rtt_threshold_ms" in body_dict:
        updates["rtt_threshold_ms"] = body_dict["rtt_threshold_ms"]

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
