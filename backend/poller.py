import subprocess
import platform
import re
import time
import datetime
import asyncio
import socket
import logging

logger = logging.getLogger(__name__)

try:
    from puresnmp import PyWrapper, V2C, V1
    from puresnmp.api.raw import Client
    SNMP_AVAILABLE = True
except ImportError:
    SNMP_AVAILABLE = False
    logger.warning("puresnmp not available — SNMP polling disabled")

from database import get_conn, get_settings


# ---------------------------------------------------------------------------
# Ping
# ---------------------------------------------------------------------------

def ping_host(ip: str, timeout: int = 2) -> tuple:
    """Return (is_up: bool, response_time_ms: float|None)."""
    system = platform.system()
    if system == "Windows":
        cmd = ["ping", "-n", "1", "-w", str(timeout * 1000), ip]
    else:
        cmd = ["ping", "-c", "1", "-W", str(timeout), ip]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout + 3
        )
        if result.returncode == 0:
            m = re.search(r"time[=<]([\d.]+)\s*ms", result.stdout, re.IGNORECASE)
            rtt = float(m.group(1)) if m else None
            return True, rtt
        return False, None
    except subprocess.TimeoutExpired:
        return False, None
    except Exception as e:
        logger.error("ping error %s: %s", ip, e)
        return False, None


def _get_last_alert_type(conn, device_id: int, alert_types: tuple) -> str | None:
    """指定タイプ群の中で最新のアラートタイプを返す。"""
    placeholders = ",".join("?" * len(alert_types))
    row = conn.execute(
        f"SELECT type FROM alerts WHERE device_id=? AND type IN ({placeholders}) "
        "ORDER BY timestamp DESC LIMIT 1",
        (device_id, *alert_types),
    ).fetchone()
    return row["type"] if row else None


def poll_ping(device_id: int, ip: str):
    status, rtt = ping_host(ip)
    conn = get_conn()

    device_row = conn.execute(
        "SELECT name, rtt_threshold_ms FROM devices WHERE id=?", (device_id,)
    ).fetchone()
    device_name = device_row["name"] if device_row else str(device_id)
    rtt_threshold = device_row["rtt_threshold_ms"] if device_row else None

    # ---- 死活アラート ----
    prev = conn.execute(
        "SELECT status FROM ping_results WHERE device_id=? ORDER BY timestamp DESC LIMIT 1",
        (device_id,),
    ).fetchone()

    alert_type = None
    if prev is not None:
        if prev["status"] == 1 and not status:
            alert_type = "down"
        elif prev["status"] == 0 and status:
            alert_type = "recovery"

    if alert_type:
        conn.execute(
            "INSERT INTO alerts (device_id, type) VALUES (?, ?)",
            (device_id, alert_type),
        )

    # ---- RTT 閾値アラート（UP かつ RTT 取得済みのときのみ） ----
    rtt_alert_type = None
    if status and rtt is not None and rtt_threshold is not None:
        last_rtt = _get_last_alert_type(conn, device_id, ("rtt_high", "rtt_recovered"))
        if rtt > rtt_threshold and last_rtt != "rtt_high":
            rtt_alert_type = "rtt_high"
        elif rtt <= rtt_threshold and last_rtt == "rtt_high":
            rtt_alert_type = "rtt_recovered"

        if rtt_alert_type:
            conn.execute(
                "INSERT INTO alerts (device_id, type) VALUES (?, ?)",
                (device_id, rtt_alert_type),
            )
            logger.warning("ALERT %s: %s (%s) RTT=%.1fms threshold=%dms",
                           rtt_alert_type.upper(), device_name, ip, rtt, rtt_threshold)

    conn.execute(
        "INSERT INTO ping_results (device_id, status, response_time) VALUES (?, ?, ?)",
        (device_id, 1 if status else 0, rtt),
    )
    conn.commit()
    conn.close()
    logger.info("ping %s → %s  %s", ip, "UP" if status else "DOWN",
                f"{rtt:.1f}ms" if rtt is not None else "timeout")

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    settings = get_settings()

    if alert_type:
        logger.warning("ALERT %s: %s (%s)", alert_type.upper(), device_name, ip)
        try:
            from notifier import notify
            notify(device_name, ip, alert_type, timestamp, settings)
        except Exception as e:
            logger.error("notify error: %s", e)

    if rtt_alert_type:
        try:
            from notifier import notify_threshold
            notify_threshold(device_name, ip, "rtt", rtt_alert_type,
                             rtt, rtt_threshold, timestamp, settings)
        except Exception as e:
            logger.error("notify threshold error: %s", e)


# ---------------------------------------------------------------------------
# TCP Port check
# ---------------------------------------------------------------------------

def check_port(ip: str, port: int, timeout: int = 3) -> tuple:
    """Return (is_open: bool, response_time_ms: float|None)."""
    start = time.time()
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((ip, port))
        elapsed = (time.time() - start) * 1000
        sock.close()
        if result == 0:
            return True, round(elapsed, 2)
        return False, None
    except Exception as e:
        logger.debug("port check error %s:%d: %s", ip, port, e)
        return False, None


def poll_ports(device_id: int, ip: str):
    conn = get_conn()
    checks = conn.execute(
        "SELECT port FROM port_checks WHERE device_id=? AND enabled=1",
        (device_id,),
    ).fetchall()
    if not checks:
        conn.close()
        return

    for check in checks:
        port = check["port"]
        status, rtt = check_port(ip, port)
        conn.execute(
            "INSERT INTO port_results (device_id, port, status, response_time) VALUES (?,?,?,?)",
            (device_id, port, 1 if status else 0, rtt),
        )
        logger.info("port %s:%d → %s  %s", ip, port,
                    "OPEN" if status else "CLOSED",
                    f"{rtt:.1f}ms" if rtt else "timeout")

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# SNMP helpers (puresnmp async, called via asyncio.run)
# ---------------------------------------------------------------------------

def _make_creds(community: str, version: str):
    return V2C(community) if version == "v2c" else V1(community)


async def _walk_oid(ip: str, community: str, port: int, version: str, oid: str) -> dict:
    """Return {if_index (int): value} for the given OID subtree."""
    creds = _make_creds(community, version)
    client = PyWrapper(Client(ip, creds, port=port))
    result = {}
    try:
        async for vb in client.walk(oid):
            idx = int(str(vb.oid).split(".")[-1])
            result[idx] = vb.value
    except Exception as e:
        logger.debug("SNMP walk %s %s: %s", oid, ip, e)
    return result


def _decode_str(value) -> str:
    """puresnmp が返す bytes / str を安全に文字列へ変換する。"""
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8").strip()
        except Exception:
            return value.decode("latin-1", errors="replace").strip()
    return str(value).strip() if value is not None else ""


async def _get_interfaces_async(ip, community, port, version):
    names, speeds = await asyncio.gather(
        _walk_oid(ip, community, port, version, "1.3.6.1.2.1.2.2.1.2"),   # ifDescr
        _walk_oid(ip, community, port, version, "1.3.6.1.2.1.2.2.1.5"),   # ifSpeed
    )
    interfaces = {}
    for idx, name in names.items():
        decoded = _decode_str(name)
        interfaces[idx] = {
            "name":  decoded if decoded else f"if{idx}",
            "speed": int(speeds.get(idx, 0) or 0),
        }
    return interfaces


async def _get_counters_async(ip, community, port, version):
    """Return {if_index: {"in": octets, "out": octets}}."""
    # Try 64-bit HC counters first
    hc_in, hc_out = await asyncio.gather(
        _walk_oid(ip, community, port, version, "1.3.6.1.2.1.31.1.1.1.6"),   # ifHCInOctets
        _walk_oid(ip, community, port, version, "1.3.6.1.2.1.31.1.1.1.10"),  # ifHCOutOctets
    )
    if hc_in:
        counters = {}
        for idx in set(hc_in) | set(hc_out):
            counters[idx] = {
                "in":  int(hc_in.get(idx)  or 0),
                "out": int(hc_out.get(idx) or 0),
            }
        return counters

    # Fall back to 32-bit counters
    std_in, std_out = await asyncio.gather(
        _walk_oid(ip, community, port, version, "1.3.6.1.2.1.2.2.1.10"),   # ifInOctets
        _walk_oid(ip, community, port, version, "1.3.6.1.2.1.2.2.1.16"),  # ifOutOctets
    )
    counters = {}
    for idx in set(std_in) | set(std_out):
        counters[idx] = {
            "in":  int(std_in.get(idx)  or 0),
            "out": int(std_out.get(idx) or 0),
        }
    return counters


# ---------------------------------------------------------------------------
# SNMP poll (called by scheduler)
# ---------------------------------------------------------------------------

def poll_snmp(device_id: int, ip: str, community: str, port: int, version: str):
    if not SNMP_AVAILABLE:
        return

    try:
        interfaces, counters = asyncio.run(_poll_snmp_async(ip, community, port, version))
    except Exception as e:
        logger.error("SNMP poll failed %s: %s", ip, e)
        return

    conn = get_conn()
    now_ts = time.time()

    for idx, info in interfaces.items():
        conn.execute(
            "INSERT OR REPLACE INTO snmp_interfaces (device_id, if_index, if_name, if_speed) VALUES (?,?,?,?)",
            (device_id, idx, info["name"], info["speed"]),
        )
    conn.commit()

    for idx, ctr in counters.items():
        in_oct  = ctr["in"]
        out_oct = ctr["out"]
        in_bps  = None
        out_bps = None

        prev = conn.execute(
            "SELECT in_octets, out_octets, timestamp FROM snmp_traffic "
            "WHERE device_id=? AND if_index=? ORDER BY timestamp DESC LIMIT 1",
            (device_id, idx),
        ).fetchone()

        if prev and prev["in_octets"] is not None:
            prev_ts  = datetime.datetime.fromisoformat(prev["timestamp"]).timestamp()
            elapsed  = now_ts - prev_ts
            if elapsed > 0:
                in_diff  = in_oct  - prev["in_octets"]
                out_diff = out_oct - prev["out_octets"]
                # 32-bit counter wrap guard (64-bit counters rarely wrap)
                if in_diff  < 0: in_diff  += 2 ** 32
                if out_diff < 0: out_diff += 2 ** 32
                in_bps  = (in_diff  * 8) / elapsed
                out_bps = (out_diff * 8) / elapsed

        conn.execute(
            "INSERT INTO snmp_traffic (device_id, if_index, in_octets, out_octets, in_bps, out_bps) "
            "VALUES (?,?,?,?,?,?)",
            (device_id, idx, in_oct, out_oct, in_bps, out_bps),
        )

    conn.commit()

    # ---- 帯域幅閾値アラート ----
    bw_threshold_pct = None
    try:
        from database import get_settings as _gs
        val = _gs().get("bandwidth_threshold_pct", "")
        bw_threshold_pct = int(val) if val else None
    except Exception:
        pass

    if bw_threshold_pct is not None:
        device_row = conn.execute("SELECT name FROM devices WHERE id=?", (device_id,)).fetchone()
        device_name = device_row["name"] if device_row else str(device_id)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for idx, ctr in counters.items():
            iface = conn.execute(
                "SELECT if_name, if_speed FROM snmp_interfaces WHERE device_id=? AND if_index=?",
                (device_id, idx),
            ).fetchone()
            if not iface or not iface["if_speed"]:
                continue
            speed_bps = iface["if_speed"]
            # 直近 bps を再取得
            latest = conn.execute(
                "SELECT in_bps, out_bps FROM snmp_traffic "
                "WHERE device_id=? AND if_index=? AND in_bps IS NOT NULL "
                "ORDER BY timestamp DESC LIMIT 1",
                (device_id, idx),
            ).fetchone()
            if not latest:
                continue
            max_bps = max(latest["in_bps"] or 0, latest["out_bps"] or 0)
            usage_pct = (max_bps / speed_bps) * 100 if speed_bps > 0 else 0

            last_bw = _get_last_alert_type(
                conn, device_id,
                (f"bw_high_{idx}", f"bw_recovered_{idx}"),
            )
            bw_alert = None
            if usage_pct > bw_threshold_pct and last_bw != f"bw_high_{idx}":
                bw_alert = f"bw_high_{idx}"
            elif usage_pct <= bw_threshold_pct and last_bw == f"bw_high_{idx}":
                bw_alert = f"bw_recovered_{idx}"

            if bw_alert:
                conn.execute(
                    "INSERT INTO alerts (device_id, type) VALUES (?, ?)",
                    (device_id, bw_alert),
                )
                alert_kind = "bw_high" if bw_alert.startswith("bw_high") else "bw_recovered"
                if_name = iface["if_name"] or f"if{idx}"
                logger.warning("ALERT %s: %s (%s) if=%s usage=%.1f%% threshold=%d%%",
                               bw_alert.upper(), device_name, ip,
                               if_name, usage_pct, bw_threshold_pct)
                try:
                    from notifier import notify_threshold
                    notify_threshold(device_name, ip, "bandwidth", alert_kind,
                                     usage_pct, bw_threshold_pct, timestamp,
                                     get_settings(), if_name=if_name)
                except Exception as e:
                    logger.error("notify threshold error: %s", e)

        conn.commit()

    conn.close()
    logger.info("snmp %s → %d interfaces", ip, len(counters))


async def _poll_snmp_async(ip, community, port, version):
    interfaces, counters = await asyncio.gather(
        _get_interfaces_async(ip, community, port, version),
        _get_counters_async(ip, community, port, version),
    )
    return interfaces, counters
