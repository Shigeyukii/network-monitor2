import subprocess
import platform
import re
import time
import datetime
import asyncio
import logging

logger = logging.getLogger(__name__)

try:
    from puresnmp import PyWrapper, V2C, V1
    from puresnmp.api.raw import Client
    SNMP_AVAILABLE = True
except ImportError:
    SNMP_AVAILABLE = False
    logger.warning("puresnmp not available — SNMP polling disabled")

from database import get_conn


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


def poll_ping(device_id: int, ip: str):
    status, rtt = ping_host(ip)
    conn = get_conn()

    # 状態遷移を検知してアラートを生成
    prev = conn.execute(
        "SELECT status FROM ping_results WHERE device_id=? ORDER BY timestamp DESC LIMIT 1",
        (device_id,),
    ).fetchone()

    if prev is not None:
        if prev["status"] == 1 and not status:
            conn.execute(
                "INSERT INTO alerts (device_id, type) VALUES (?, 'down')",
                (device_id,),
            )
            logger.warning("ALERT DOWN: device_id=%d ip=%s", device_id, ip)
        elif prev["status"] == 0 and status:
            conn.execute(
                "INSERT INTO alerts (device_id, type) VALUES (?, 'recovery')",
                (device_id,),
            )
            logger.info("ALERT RECOVERY: device_id=%d ip=%s", device_id, ip)

    conn.execute(
        "INSERT INTO ping_results (device_id, status, response_time) VALUES (?, ?, ?)",
        (device_id, 1 if status else 0, rtt),
    )
    conn.commit()
    conn.close()
    logger.info("ping %s → %s  %s", ip, "UP" if status else "DOWN",
                f"{rtt:.1f}ms" if rtt is not None else "timeout")


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


async def _get_interfaces_async(ip, community, port, version):
    names, speeds = await asyncio.gather(
        _walk_oid(ip, community, port, version, "1.3.6.1.2.1.2.2.1.2"),   # ifDescr
        _walk_oid(ip, community, port, version, "1.3.6.1.2.1.2.2.1.5"),   # ifSpeed
    )
    interfaces = {}
    for idx, name in names.items():
        interfaces[idx] = {
            "name":  str(name) if name is not None else f"if{idx}",
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
    conn.close()
    logger.info("snmp %s → %d interfaces", ip, len(counters))


async def _poll_snmp_async(ip, community, port, version):
    interfaces, counters = await asyncio.gather(
        _get_interfaces_async(ip, community, port, version),
        _get_counters_async(ip, community, port, version),
    )
    return interfaces, counters
