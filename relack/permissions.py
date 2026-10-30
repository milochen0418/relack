"""Who may do what: the admin's permission switches, approvals and admin accounts.

Admins are the passcode holder (per tab, AdminState) and the accounts listed in
the `admins` setting. Guests have no password, so they can never be admins.
"""

from relack import db
from relack.models import PermissionConfig, UserProfile


def config() -> PermissionConfig:
    return PermissionConfig(**(db.get_setting("permissions") or {}))


def admins() -> list[str]:
    return list(db.get_setting("admins", []) or [])


def is_admin(user: UserProfile | None) -> bool:
    return bool(user) and not user.is_guest and user.username in admins()


def set_admin(username: str, admin: bool):
    names = [u for u in admins() if u != username]
    db.set_setting("admins", [*names, username] if admin else names)


def is_approved(user: UserProfile) -> bool:
    return bool((db.get_setting("approved_users", {}) or {}).get(user.username))


def is_pending(user: UserProfile | None) -> bool:
    """Signed in, but waiting for an admin before they can use the app."""
    if not user or is_admin(user):
        return False
    cfg = config()
    required = cfg.guest_requires_approval if user.is_guest else cfg.google_requires_approval
    return required and not is_approved(user)


def can(user: UserProfile | None, action: str) -> bool:
    """`action` is create_room, mention_users or view_profiles."""
    if not user:
        return False
    if is_admin(user):
        return True
    return bool(getattr(config(), f"{'guest' if user.is_guest else 'google'}_can_{action}"))
