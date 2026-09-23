"""Authentication and user-management business logic."""
from dataclasses import dataclass
from typing import Optional

from database.db_manager import DEFAULT_ADMIN_USERNAME, get_connection
from logic.security import hash_password, verify_password
from logic.settings import get_setting, set_setting

VALID_ROLES = ("admin", "cashier")


@dataclass
class User:
    id: int
    username: str
    full_name: str
    role: str
    is_active: bool

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


def _row_to_user(row) -> User:
    return User(
        id=row["id"],
        username=row["username"],
        full_name=row["full_name"] or "",
        role=row["role"],
        is_active=bool(row["is_active"]),
    )


def login(username: str, password: str) -> Optional[User]:
    """Return a User on success, or None if credentials are invalid/inactive."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ? COLLATE NOCASE", (username.strip(),)
        ).fetchone()
        if row is None or not row["is_active"]:
            return None
        if not verify_password(password, row["password_hash"]):
            return None
        return _row_to_user(row)
    finally:
        conn.close()


def list_users() -> list[User]:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM users ORDER BY username").fetchall()
        return [_row_to_user(r) for r in rows]
    finally:
        conn.close()


def create_user(username: str, password: str, full_name: str, role: str) -> User:
    username = username.strip()
    if not username:
        raise ValueError("Username is required.")
    if not password or len(password) < 4:
        raise ValueError("Password must be at least 4 characters.")
    if role not in VALID_ROLES:
        raise ValueError(f"Role must be one of {VALID_ROLES}.")

    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT id FROM users WHERE username = ? COLLATE NOCASE", (username,)
        ).fetchone()
        if existing:
            raise ValueError(f"Username '{username}' already exists.")
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, full_name, role) "
            "VALUES (?, ?, ?, ?)",
            (username, hash_password(password), full_name.strip(), role),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM users WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return _row_to_user(row)
    finally:
        conn.close()


def update_user(
    user_id: int,
    full_name: str,
    role: str,
    is_active: bool,
    new_password: Optional[str] = None,
) -> None:
    if role not in VALID_ROLES:
        raise ValueError(f"Role must be one of {VALID_ROLES}.")

    conn = get_connection()
    try:
        if new_password:
            if len(new_password) < 4:
                raise ValueError("Password must be at least 4 characters.")
            conn.execute(
                "UPDATE users SET full_name=?, role=?, is_active=?, password_hash=? "
                "WHERE id=?",
                (full_name.strip(), role, int(is_active), hash_password(new_password), user_id),
            )
        else:
            conn.execute(
                "UPDATE users SET full_name=?, role=?, is_active=? WHERE id=?",
                (full_name.strip(), role, int(is_active), user_id),
            )
        conn.commit()
    finally:
        conn.close()


def delete_user(user_id: int, current_user_id: int) -> None:
    if user_id == current_user_id:
        raise ValueError("You cannot delete the account you are logged in as.")

    conn = get_connection()
    try:
        remaining_admins = conn.execute(
            "SELECT COUNT(*) AS c FROM users WHERE role='admin' AND id != ?",
            (user_id,),
        ).fetchone()["c"]
        target = conn.execute("SELECT role FROM users WHERE id=?", (user_id,)).fetchone()
        if target and target["role"] == "admin" and remaining_admins == 0:
            raise ValueError("Cannot delete the last remaining admin account.")
        conn.execute("DELETE FROM users WHERE id=?", (user_id,))
        conn.commit()
    finally:
        conn.close()


RECOVERY_PASSWORD = "admin123"

_RECOVERY_PIN_SETTING_KEY = "recovery_pin_hash"

# Developer-only fallback: if the shop owner sets their own recovery PIN
# (below) and later forgets that too, this fixed PIN still lets the
# developer reset admin access over the phone without needing physical/DB
# access to that shop's PC. Only its PBKDF2 hash is embedded here -- never
# the plaintext -- so extracting this source (or decompiling the frozen
# .exe) doesn't directly hand out the PIN. This is a *different* secret
# from the installer password on purpose: reusing one secret for both would
# mean a single leak compromises both the install gate and every shop's
# admin recovery at once.
_MASTER_PIN_HASH = (
    "b384feb97209baf1e82067f08a103ebd$"
    "033fc74a63d6c6296d3ab3f5b974c757107735e2318648e338770fef3bd90103"
)


def has_recovery_pin() -> bool:
    """Whether the shop owner has set their own recovery PIN yet."""
    return bool(get_setting(_RECOVERY_PIN_SETTING_KEY, ""))


def set_recovery_pin(pin: str) -> None:
    pin = pin.strip()
    if len(pin) < 4:
        raise ValueError("Recovery PIN must be at least 4 characters.")
    set_setting(_RECOVERY_PIN_SETTING_KEY, hash_password(pin))


def verify_recovery_pin(pin: str) -> bool:
    """Accept either the shop owner's own recovery PIN (if they've set one)
    or the developer's master PIN -- so the reset button never permanently
    locks a shop out even if the owner never configured their own PIN."""
    pin = pin.strip()
    if not pin:
        return False
    owner_hash = get_setting(_RECOVERY_PIN_SETTING_KEY, "")
    if owner_hash and verify_password(pin, owner_hash):
        return True
    return verify_password(pin, _MASTER_PIN_HASH)


def recover_admin_access() -> str:
    """Reset the oldest admin account's password (and reactivate/re-promote
    it if needed) without requiring a login. This is the only way back into
    the app if every admin password has been forgotten -- since it's a fully
    offline app there is no email/SMS reset path, and the normal Backup/
    Restore screen is itself only reachable after logging in as an admin, so
    a locked-out shop would otherwise have no recovery route at all.

    Returns the username that was reset. Invoked via `main.py --recover-admin`
    (see ui.login_window's "Forgot password?" link), which runs this before
    any login is required.
    """
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, username FROM users WHERE role='admin' ORDER BY id LIMIT 1"
        ).fetchone()
        if row is None:
            # No admin account exists at all (shouldn't normally happen) --
            # recreate the default one from scratch.
            conn.execute(
                "INSERT INTO users (username, password_hash, full_name, role, is_active) "
                "VALUES (?, ?, ?, 'admin', 1)",
                (DEFAULT_ADMIN_USERNAME, hash_password(RECOVERY_PASSWORD), "Administrator"),
            )
            conn.commit()
            return DEFAULT_ADMIN_USERNAME

        conn.execute(
            "UPDATE users SET password_hash=?, is_active=1, role='admin' WHERE id=?",
            (hash_password(RECOVERY_PASSWORD), row["id"]),
        )
        conn.commit()
        return row["username"]
    finally:
        conn.close()
