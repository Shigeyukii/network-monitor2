"""
シンプルなトークンベース認証モジュール。

パスワードは DB の settings テーブルに SHA-256 ハッシュで保存する。
パスワード未設定時は認証なし（後方互換）。
発行済みトークンはプロセス内メモリで管理する（再起動で失効）。
"""
import secrets
import hashlib
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import get_conn

# プロセス内で有効なトークンセット
_active_tokens: set[str] = set()

_PASSWORD_KEY = "auth_password_hash"


def _get_stored_hash() -> str | None:
    conn = get_conn()
    row = conn.execute(
        "SELECT value FROM settings WHERE key=?", (_PASSWORD_KEY,)
    ).fetchone()
    conn.close()
    return row["value"] if row and row["value"] else None


def auth_enabled() -> bool:
    """パスワードが設定されている場合のみ True。"""
    return bool(_get_stored_hash())


def verify_password(password: str) -> bool:
    stored = _get_stored_hash()
    if not stored:
        return True  # パスワード未設定 = 誰でも通過
    return hashlib.sha256(password.encode("utf-8")).hexdigest() == stored


def set_password(password: str) -> None:
    """パスワードをハッシュ化して DB に保存する。空文字で認証無効化。"""
    conn = get_conn()
    if password:
        hashed = hashlib.sha256(password.encode("utf-8")).hexdigest()
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (_PASSWORD_KEY, hashed),
        )
    else:
        conn.execute("DELETE FROM settings WHERE key=?", (_PASSWORD_KEY,))
        _active_tokens.clear()
    conn.commit()
    conn.close()


def create_token() -> str:
    token = secrets.token_urlsafe(32)
    _active_tokens.add(token)
    return token


def check_token(token: str) -> bool:
    if not auth_enabled():
        return True
    return token in _active_tokens


def revoke_token(token: str) -> None:
    _active_tokens.discard(token)
