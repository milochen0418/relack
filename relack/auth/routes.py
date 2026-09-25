import os
import secrets
import datetime
import logging
from urllib.parse import urlencode

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import RedirectResponse
from starlette.routing import Route
from google.oauth2.id_token import verify_oauth2_token
from google.auth.transport import requests as google_requests
from httpx import AsyncClient

from relack.models import UserProfile
from relack.auth.session import (
    create_session,
    delete_session,
    create_claim_token,
    redeem_claim_token,
)

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
COOKIE_NAME = "relack_sid"
COOKIE_MAX_AGE = 86400 * 30
TOKEN_URI = "https://oauth2.googleapis.com/token"
AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"


def _frontend_url() -> str:
    return os.environ.get("FRONTEND_URL", "http://localhost:3000")


def _backend_url() -> str:
    return os.environ.get("BACKEND_URL", "http://localhost:8000")


async def google_login(request: Request):
    state = secrets.token_urlsafe(16)
    redirect_uri = f"{_backend_url()}/auth/google/callback"
    params = urlencode({
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    })
    response = RedirectResponse(f"{AUTH_URI}?{params}")
    response.set_cookie(
        "relack_oauth_state", state,
        httponly=True, samesite="lax", max_age=600, path="/",
    )
    return response


async def google_callback(request: Request):
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    cookie_state = request.cookies.get("relack_oauth_state")

    if not state or state != cookie_state:
        logging.warning("OAuth state mismatch")
        return RedirectResponse(f"{_frontend_url()}/?auth_error=invalid_state")

    if not code:
        return RedirectResponse(f"{_frontend_url()}/?auth_error=no_code")

    redirect_uri = f"{_backend_url()}/auth/google/callback"

    try:
        async with AsyncClient() as client:
            token_resp = await client.post(TOKEN_URI, data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            })
            if token_resp.status_code != 200:
                logging.error("Token exchange failed: %s", token_resp.text)
                return RedirectResponse(f"{_frontend_url()}/?auth_error=token_failed")
            token_data = token_resp.json()
    except Exception:
        logging.exception("Token exchange error")
        return RedirectResponse(f"{_frontend_url()}/?auth_error=token_failed")

    id_token_str = token_data.get("id_token")
    if not id_token_str:
        return RedirectResponse(f"{_frontend_url()}/?auth_error=no_id_token")

    try:
        id_info = verify_oauth2_token(
            id_token_str,
            google_requests.Request(),
            GOOGLE_CLIENT_ID,
            clock_skew_in_seconds=10,
        )
    except Exception:
        logging.exception("Token verification failed")
        return RedirectResponse(f"{_frontend_url()}/?auth_error=invalid_token")

    email = id_info.get("email")
    if not email:
        return RedirectResponse(f"{_frontend_url()}/?auth_error=no_email")

    profile = UserProfile(
        username=email,
        email=email,
        nickname=id_info.get("name", email),
        is_guest=False,
        avatar_seed=email,
        created_at=datetime.datetime.now().isoformat(),
        token=id_info.get("sub", ""),
    )

    session_id = create_session(profile)
    response = RedirectResponse(f"{_frontend_url()}/")
    response.set_cookie(
        COOKIE_NAME, session_id,
        httponly=True, samesite="lax", max_age=COOKIE_MAX_AGE, path="/",
    )
    response.delete_cookie("relack_oauth_state", path="/")
    return response


async def claim_session(request: Request):
    token = request.query_params.get("token", "")
    session_id = redeem_claim_token(token)
    if not session_id:
        return RedirectResponse(f"{_frontend_url()}/?auth_error=invalid_claim")

    response = RedirectResponse(f"{_frontend_url()}/")
    response.set_cookie(
        COOKIE_NAME, session_id,
        httponly=True, samesite="lax", max_age=COOKIE_MAX_AGE, path="/",
    )
    return response


async def logout(request: Request):
    session_id = request.cookies.get(COOKIE_NAME)
    if session_id:
        delete_session(session_id)

    response = RedirectResponse(f"{_frontend_url()}/")
    response.delete_cookie(COOKIE_NAME, path="/")
    for legacy in ("relack_session", "relack_gtoken", "relack_grefresh"):
        response.delete_cookie(legacy, path="/")
    return response


auth_routes = Starlette(routes=[
    Route("/auth/google/login", google_login),
    Route("/auth/google/callback", google_callback),
    Route("/auth/claim", claim_session),
    Route("/auth/logout", logout),
])
