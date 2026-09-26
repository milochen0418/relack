"""Cross-subdomain SSO cookie helpers for *.reflex-ddns.com.

Sets a `ddns_auth` JWT cookie on the parent domain so that all
Reflex apps on *.reflex-ddns.com share the same login state.
"""

import os
import logging
from urllib.parse import urlparse

from starlette.requests import Request
from starlette.responses import Response

try:
    import jwt as _jwt
except ImportError:
    _jwt = None  # type: ignore[assignment]

from relack.models import UserProfile

logger = logging.getLogger(__name__)

DDNS_AUTH_SECRET = os.environ.get("DDNS_AUTH_SECRET", "")
DDNS_AUTH_COOKIE = os.environ.get("DDNS_AUTH_COOKIE", "ddns_auth")
DDNS_AUTH_MAX_AGE = 86400 * 30
DDNS_PARENT_DOMAIN = os.environ.get("DDNS_PARENT_DOMAIN", "")


def _detect_parent_domain(request: Request) -> str:
    """Detect the parent domain from the request for cross-subdomain cookies.

    Returns ".reflex-ddns.com" when the host is *.reflex-ddns.com,
    or "" for localhost (no Domain attribute needed).
    """
    if DDNS_PARENT_DOMAIN:
        return DDNS_PARENT_DOMAIN

    host = (
        request.headers.get("x-forwarded-host")
        or request.headers.get("host")
        or request.url.netloc
    )
    host = host.split(",")[0].strip().split(":")[0]

    if host in ("localhost", "127.0.0.1", "0.0.0.0"):
        return ""

    parts = host.split(".")
    if len(parts) >= 2:
        return "." + ".".join(parts[-2:])
    return ""


def _is_secure(request: Request) -> bool:
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    return proto == "https"


def _get_approval_status(email: str) -> bool:
    """Check if a user is admin-approved, via the shared lobby state."""
    try:
        from relack.auth.session import get_approved_status
        return get_approved_status(email)
    except Exception:
        return False


def set_ddns_auth_cookie(response: Response, profile: UserProfile, request: Request):
    """Set a cross-subdomain JWT cookie containing user identity."""
    if _jwt is None:
        logger.warning("PyJWT not installed — skipping ddns_auth cookie")
        return
    if not DDNS_AUTH_SECRET:
        logger.debug("DDNS_AUTH_SECRET not set — skipping ddns_auth cookie")
        return

    import time
    payload = {
        "email": profile.email,
        "name": profile.nickname or profile.username,
        "picture": profile.avatar_url or "",
        "approved": profile.is_approved or _get_approval_status(profile.email),
        "iat": int(time.time()),
        "exp": int(time.time()) + DDNS_AUTH_MAX_AGE,
    }
    token = _jwt.encode(payload, DDNS_AUTH_SECRET, algorithm="HS256")

    domain = _detect_parent_domain(request)
    secure = _is_secure(request)

    kwargs: dict = {
        "httponly": True,
        "secure": secure,
        "samesite": "lax",
        "max_age": DDNS_AUTH_MAX_AGE,
        "path": "/",
    }
    if domain:
        kwargs["domain"] = domain

    response.set_cookie(DDNS_AUTH_COOKIE, token, **kwargs)


def clear_ddns_auth_cookie(response: Response, request: Request):
    """Remove the cross-subdomain JWT cookie."""
    domain = _detect_parent_domain(request)
    kwargs: dict = {"path": "/"}
    if domain:
        kwargs["domain"] = domain
    response.delete_cookie(DDNS_AUTH_COOKIE, **kwargs)
