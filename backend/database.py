import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "monitor.db"


def get_conn():
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS devices (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT    NOT NULL,
            ip_address      TEXT    NOT NULL UNIQUE,
            snmp_enabled    INTEGER NOT NULL DEFAULT 0,
            snmp_community  TEXT    NOT NULL DEFAULT 'public',
            snmp_port       INTEGER NOT NULL DEFAULT 161,
            snmp_version    TEXT    NOT NULL DEFAULT 'v2c',
            ping_interval   INTEGER NOT NULL DEFAULT 60,
            created_at      TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS ping_results (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id     INTEGER NOT NULL,
            timestamp     TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
            status        INTEGER NOT NULL,
            response_time REAL,
            FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_ping_device_time
            ON ping_results(device_id, timestamp DESC);

        CREATE TABLE IF NOT EXISTS snmp_interfaces (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id INTEGER NOT NULL,
            if_index  INTEGER NOT NULL,
            if_name   TEXT,
            if_speed  BIGINT  DEFAULT 0,
            UNIQUE(device_id, if_index),
            FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS snmp_traffic (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id  INTEGER NOT NULL,
            if_index   INTEGER NOT NULL,
            timestamp  TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
            in_octets  BIGINT,
            out_octets BIGINT,
            in_bps     REAL,
            out_bps    REAL,
            FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_traffic_device_iface_time
            ON snmp_traffic(device_id, if_index, timestamp DESC);

        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        INSERT OR IGNORE INTO settings (key, value) VALUES ('ping_interval', '60');
        INSERT OR IGNORE INTO settings (key, value) VALUES ('snmp_interval', '60');
    """)
    conn.commit()
    conn.close()


def get_settings() -> dict:
    conn = get_conn()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    return {r["key"]: r["value"] for r in rows}


def cleanup_old_data():
    """Remove data older than retention limits to keep DB size manageable."""
    conn = get_conn()
    conn.execute("DELETE FROM ping_results WHERE timestamp < datetime('now','localtime','-7 days')")
    conn.execute("DELETE FROM snmp_traffic WHERE timestamp < datetime('now','localtime','-30 days')")
    conn.commit()
    conn.close()
