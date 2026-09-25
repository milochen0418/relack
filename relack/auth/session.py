import secrets
from http.cookies import SimpleCookie
from relack.models import UserProfile

_sessions: dict[str, UserProfile] = {}
_claim_tokens: dict[str, str] = {}


def create_session(profile: UserProfile) -> str:
    session_id = secrets.token_urlsafe(32)
    _sessions[session_id] = profile
    return session_id


def get_session(session_id: str) -> UserProfile | None:
    return _sessions.get(session_id)


def delete_session(session_id: str):
    _sessions.pop(session_id, None)


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
