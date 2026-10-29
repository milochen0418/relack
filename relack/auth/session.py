import secrets
from http.cookies import SimpleCookie
from relack import db
from relack.models import UserProfile

# Logins are kept in the database (so they survive restarts); this is a cache.
_sessions: dict[str, UserProfile] = {}
_claim_tokens: dict[str, str] = {}


def create_session(profile: UserProfile) -> str:
    session_id = secrets.token_urlsafe(32)
    db.save_session(session_id, profile)
    _sessions[session_id] = profile
    return session_id


def get_session(session_id: str) -> UserProfile | None:
    profile = _sessions.get(session_id)
    if profile is None and session_id:
        profile = db.load_session(session_id)
        if profile is not None:
            _sessions[session_id] = profile
    return profile


def delete_session(session_id: str):
    _sessions.pop(session_id, None)
    db.delete_session(session_id)


def update_profile(profile: UserProfile):
    """Show an edited nickname and bio in every login of that person."""
    db.update_session_profiles(profile)
    for session_id, cached in list(_sessions.items()):
        if cached.username == profile.username:
            _sessions[session_id] = cached.model_copy(update={"nickname": profile.nickname, "bio": profile.bio})


def create_claim_token(session_id: str) -> str:
    token = secrets.token_urlsafe(32)
    _claim_tokens[token] = session_id
    return token


def redeem_claim_token(token: str) -> str | None:
    return _claim_tokens.pop(token, None)


def parse_session_id(cookie_header: str) -> str:
    if not cookie_header:
        return ""
    try:
        cookies = SimpleCookie(cookie_header)
        morsel = cookies.get("relack_sid")
        return morsel.value if morsel else ""
    except Exception:
        return ""


def set_approved_status(email: str, approved: bool):
    approved_users = dict(db.get_setting("approved_users", {}) or {})
    approved_users[email] = approved
    db.set_setting("approved_users", approved_users)


def get_approved_status(email: str) -> bool:
    return bool((db.get_setting("approved_users", {}) or {}).get(email, False))
