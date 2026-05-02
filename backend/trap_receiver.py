"""
SNMP Trap Receiver
- UDP ソケットで待ち受けて v1 / v2c トラップを受信・解析・DB 保存
- pysnmp は Python 3.14 非対応のため BER を自前デコード
"""
import socket
import json
import threading
import logging

from database import get_conn

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# BER デコーダ
# ---------------------------------------------------------------------------

def _decode_length(data: bytes, pos: int):
    b = data[pos]
    if b < 0x80:
        return b, pos + 1
    n = b & 0x7f
    return int.from_bytes(data[pos + 1: pos + 1 + n], "big"), pos + 1 + n


def _decode_oid(data: bytes) -> str:
    if not data:
        return ""
    parts = [str(data[0] // 40), str(data[0] % 40)]
    i, val = 1, 0
    while i < len(data):
        b = data[i]; i += 1
        val = (val << 7) | (b & 0x7f)
        if not (b & 0x80):
            parts.append(str(val))
            val = 0
    return ".".join(parts)


def _decode_value(tag: int, data: bytes) -> str:
    if not data:
        return ""
    try:
        if tag == 0x02:                                  # INTEGER
            return str(int.from_bytes(data, "big", signed=True))
        if tag == 0x04:                                  # OCTET STRING
            try: return data.decode("utf-8")
            except: return data.hex()
        if tag == 0x05:                                  # NULL
            return ""
        if tag == 0x06:                                  # OID
            return _decode_oid(data)
        if tag == 0x40:                                  # IpAddress
            return ".".join(str(b) for b in data[:4])
        if tag in (0x41, 0x42, 0x43, 0x46, 0x47):      # Counter/Gauge/TimeTicks/…
            return str(int.from_bytes(data, "big"))
        return data.hex()
    except Exception:
        return data.hex() if data else ""


def _tlv(data: bytes, pos: int):
    """Return (tag, value_bytes, next_pos)."""
    if pos >= len(data):
        return None, b"", pos
    tag = data[pos]; pos += 1
    length, pos = _decode_length(data, pos)
    return tag, data[pos: pos + length], pos + length


def _parse_varbinds(data: bytes) -> list:
    bindings, pos = [], 0
    while pos < len(data):
        tag, vb, pos = _tlv(data, pos)
        if tag != 0x30:
            continue
        p = 0
        t, oid_b, p = _tlv(vb, p)
        if t != 0x06:
            continue
        t, val_b, p = _tlv(vb, p)
        bindings.append({"oid": _decode_oid(oid_b), "value": _decode_value(t, val_b)})
    return bindings


# OID → 名前マッピング（代表的な標準トラップ）
_TRAP_NAMES = {
    "1.3.6.1.6.3.1.1.5.1": "coldStart",
    "1.3.6.1.6.3.1.1.5.2": "warmStart",
    "1.3.6.1.6.3.1.1.5.3": "linkDown",
    "1.3.6.1.6.3.1.1.5.4": "linkUp",
    "1.3.6.1.6.3.1.1.5.5": "authenticationFailure",
    "1.3.6.1.6.3.1.1.5.6": "egpNeighborLoss",
}
_V1_GENERIC = {
    0: "coldStart", 1: "warmStart", 2: "linkDown",
    3: "linkUp",    4: "authenticationFailure", 5: "egpNeighborLoss",
    6: "enterpriseSpecific",
}


def parse_snmp_trap(raw: bytes) -> dict | None:
    """
    SNMP v1 / v2c トラップパケットを解析して dict を返す。
    解析失敗時は None。
    """
    try:
        pos = 0
        tag, pkt, _ = _tlv(raw, pos)
        if tag != 0x30:          # outer SEQUENCE
            return None

        p = 0
        # version
        t, v, p = _tlv(pkt, p)
        if t != 0x02:
            return None
        version_num = int.from_bytes(v, "big") if v else 0
        version_str = {0: "v1", 1: "v2c"}.get(version_num, f"v{version_num}")

        # community
        t, v, p = _tlv(pkt, p)
        community = v.decode("utf-8", errors="replace") if t == 0x04 else ""

        # PDU
        t, pdu, p = _tlv(pkt, p)

        result = dict(version=version_str, community=community,
                      trap_oid="", generic_type="", uptime="", varbinds=[])

        if t == 0xa4:          # v1 Trap-PDU
            q = 0
            t2, v2, q = _tlv(pdu, q)
            if t2 == 0x06:
                result["trap_oid"] = _decode_oid(v2)
            t2, v2, q = _tlv(pdu, q)  # agent addr (skip)
            t2, v2, q = _tlv(pdu, q)  # generic-trap
            generic = int.from_bytes(v2, "big") if v2 else 0
            result["generic_type"] = _V1_GENERIC.get(generic, str(generic))
            t2, v2, q = _tlv(pdu, q)  # specific-trap (skip)
            t2, v2, q = _tlv(pdu, q)  # time-stamp
            if t2 == 0x43:
                ticks = int.from_bytes(v2, "big") if v2 else 0
                result["uptime"] = f"{ticks // 100} 秒"
            t2, v2, q = _tlv(pdu, q)  # VarBindList
            if t2 == 0x30:
                result["varbinds"] = _parse_varbinds(v2)

        elif t in (0xa7, 0xa6):  # v2c SNMPv2-Trap / InformRequest
            q = 0
            t2, v2, q = _tlv(pdu, q)  # request-id (skip)
            t2, v2, q = _tlv(pdu, q)  # error-status (skip)
            t2, v2, q = _tlv(pdu, q)  # error-index (skip)
            t2, v2, q = _tlv(pdu, q)  # VarBindList
            if t2 == 0x30:
                vbs = _parse_varbinds(v2)
                result["varbinds"] = vbs
                for vb in vbs:
                    if vb["oid"] == "1.3.6.1.2.1.1.3.0":      # sysUpTime
                        result["uptime"] = f"{int(vb['value']) // 100} 秒" if vb["value"].isdigit() else vb["value"]
                    elif vb["oid"] == "1.3.6.1.6.3.1.1.4.1.0":  # snmpTrapOID
                        result["trap_oid"]     = vb["value"]
                        result["generic_type"] = _TRAP_NAMES.get(vb["value"], "")
        else:
            return None  # 未知の PDU タイプ

        return result
    except Exception as e:
        logger.debug("trap parse error: %s", e)
        return None


# ---------------------------------------------------------------------------
# 受信スレッド
# ---------------------------------------------------------------------------

class TrapReceiver:
    def __init__(self):
        self.host       = "0.0.0.0"
        self.port       = 1620
        self._sock      = None
        self._thread    = None
        self._stop      = threading.Event()
        self._running   = False

    def start(self, port: int | None = None):
        if port is not None:
            self.port = port
        if self._running:
            self.stop()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="trap-receiver")
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._sock:
            try: self._sock.close()
            except Exception: pass
        self._running = False

    def _run(self):
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._sock.settimeout(1.0)
            self._sock.bind((self.host, self.port))
            self._running = True
            logger.info("SNMP Trap receiver started on %s:%d", self.host, self.port)
            while not self._stop.is_set():
                try:
                    data, addr = self._sock.recvfrom(65535)
                    self._handle(data, addr[0])
                except socket.timeout:
                    continue
        except PermissionError:
            logger.error(
                "ポート %d のバインドには root 権限が必要です。"
                "設定でポートを 1024 より大きい値（例: 1620）に変更してください。", self.port
            )
        except OSError as e:
            if not self._stop.is_set():
                logger.error("Trap receiver OSError: %s", e)
        finally:
            self._running = False
            if self._sock:
                try: self._sock.close()
                except Exception: pass

    def _handle(self, raw: bytes, source_ip: str):
        trap = parse_snmp_trap(raw)
        if trap is None:
            logger.warning("解析できないトラップを受信 from %s (%d bytes)", source_ip, len(raw))
            return

        conn = get_conn()
        conn.execute(
            """INSERT INTO traps
               (source_ip, community, version, trap_oid, generic_type, uptime, varbinds)
               VALUES (?,?,?,?,?,?,?)""",
            (source_ip, trap["community"], trap["version"],
             trap["trap_oid"], trap["generic_type"], trap["uptime"],
             json.dumps(trap["varbinds"], ensure_ascii=False)),
        )
        conn.commit()
        conn.close()
        label = trap["generic_type"] or trap["trap_oid"] or "(不明)"
        logger.info("Trap received from %-15s  %s [%s]", source_ip, label, trap["version"])


# モジュールレベルのシングルトン
trap_receiver = TrapReceiver()
