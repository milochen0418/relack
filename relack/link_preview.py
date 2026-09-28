"""URL detection and Open Graph link previews for chat messages."""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
import re
import socket
import ssl
import time
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import certifi
import httpx

from relack.models import MessagePart

logger = logging.getLogger(__name__)

URL_RE = re.compile(r"https?://[^\s<>\"'`]+", re.IGNORECASE)
_TRAILING_PUNCT = ".,;:!?)]}>'\"。，！？）」』"

# CoDoc in MD serves the SPA shell at /doc/<id>; per-document Open Graph tags
# live on the backend at /__og/doc/<id>.
_CODOC_HOSTS = {
    h.strip().lower()
    for h in os.environ.get("RELACK_CODOC_HOSTS", "md.reflex-ddns.com").split(",")
    if h.strip()
}
_CODOC_DOC_RE = re.compile(r"^/doc/([A-Za-z0-9_-]+)/?$")

# Local dev only: allow previews of localhost / LAN URLs.
_ALLOW_PRIVATE = os.environ.get("RELACK_PREVIEW_ALLOW_PRIVATE", "") == "1"

# Self-hosted sibling services (and their subdomains) may resolve to a LAN IP
# behind the same DDNS; they are exempt from the private-IP check.
_TRUSTED_DOMAINS = {
    d.strip().lower().lstrip(".")
    for d in os.environ.get("RELACK_PREVIEW_TRUSTED_DOMAINS", "reflex-ddns.com").split(",")
    if d.strip()
}


def _is_trusted_host(host: str) -> bool:
    host = host.lower().rstrip(".")
    return any(host == d or host.endswith("." + d) for d in _TRUSTED_DOMAINS)


# Trusted hosts use certs signed by the Re-DDNS Local CA. Load it from
# RELACK_PREVIEW_CA_FILE, or from the re-ddns API available to app containers.
_CA_FILE = os.environ.get("RELACK_PREVIEW_CA_FILE", "")
_RE_DDNS_API_URL = os.environ.get("RE_DDNS_API_URL", "").rstrip("/")
_trusted_ssl: ssl.SSLContext | None = None


async def _trusted_ssl_context() -> ssl.SSLContext | bool:
    global _trusted_ssl
    if _trusted_ssl is not None:
        return _trusted_ssl
    ca_pem = ""
    try:
        if _CA_FILE:
            with open(_CA_FILE, encoding="ascii") as f:
                ca_pem = f.read()
        elif _RE_DDNS_API_URL:
            async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
                resp = await client.get(f"{_RE_DDNS_API_URL}/api/ca.pem")
                if resp.status_code == 200:
                    ca_pem = resp.text
    except (OSError, httpx.HTTPError) as exc:
        logger.info("could not load Re-DDNS CA: %s", exc)
    if not ca_pem:
        return True  # default verification
    ctx = ssl.create_default_context(cafile=certifi.where())
    try:
        ctx.load_verify_locations(cadata=ca_pem)
    except ssl.SSLError as exc:
        logger.info("invalid Re-DDNS CA: %s", exc)
        return True
    _trusted_ssl = ctx
    return ctx


_TIMEOUT_SECONDS = 4.0
_MAX_BYTES = 512 * 1024
_MAX_REDIRECTS = 3
_CACHE_TTL_SECONDS = 600
_cache: dict[str, tuple[float, dict[str, str] | None]] = {}

_USER_AGENT = "RelackBot/1.0 (link preview)"
# Some sites (e.g. Medium) 403 unknown bots but allow well-known link expanders.
_FALLBACK_USER_AGENT = "Slackbot-LinkExpanding 1.0 (+https://api.slack.com/robots)"


class _Forbidden(Exception):
    pass


def _strip_trailing(url: str) -> str:
    while url and url[-1] in _TRAILING_PUNCT:
        # Keep a closing paren when the URL itself contains an opening one.
        if url[-1] == ")" and url.count("(") >= url.count(")"):
            break
        url = url[:-1]
    return url


def split_message(text: str) -> list[MessagePart]:
    """Split text into plain-text and link parts."""
    parts: list[MessagePart] = []
    pos = 0
    for m in URL_RE.finditer(text):
        url = _strip_trailing(m.group(0))
        if not url:
            continue
        if m.start() > pos:
            parts.append(MessagePart(text=text[pos : m.start()]))
        parts.append(MessagePart(text=url, href=url))
        pos = m.start() + len(url)
    if pos < len(text):
        parts.append(MessagePart(text=text[pos:]))
    return parts


def first_url(parts: list[MessagePart]) -> str:
    return next((p.href for p in parts if p.href), "")


class _MetaParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "meta":
            key = (a.get("property") or a.get("name") or "").lower()
            if key and "content" in a and key not in self.meta:
                self.meta[key] = a["content"].strip()
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data


async def _is_public_host(host: str) -> bool:
    if _ALLOW_PRIVATE or _is_trusted_host(host):
        return True
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError:
        return False
    return all(ipaddress.ip_address(info[4][0]).is_global for info in infos)


def _fetch_target(url: str) -> str:
    """Rewrite known SPA URLs to an endpoint that serves real meta tags."""
    parsed = urlparse(url)
    if (parsed.hostname or "").lower() in _CODOC_HOSTS:
        m = _CODOC_DOC_RE.match(parsed.path)
        if m:
            return f"{parsed.scheme}://{parsed.netloc}/__og/doc/{m.group(1)}"
    return url


async def _fetch_html(url: str, user_agent: str = _USER_AGENT) -> tuple[str, str] | None:
    """Fetch up to _MAX_BYTES of an HTML page, re-checking every redirect hop."""
    headers = {"User-Agent": user_agent, "Accept": "text/html"}
    for _ in range(_MAX_REDIRECTS + 1):
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return None
        if not await _is_public_host(parsed.hostname):
            return None
        # One client per hop so only trusted hosts get the Re-DDNS CA.
        verify = await _trusted_ssl_context() if _is_trusted_host(parsed.hostname) else True
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS, follow_redirects=False, verify=verify) as client:
            async with client.stream("GET", url, headers=headers) as resp:
                if resp.is_redirect and "location" in resp.headers:
                    url = urljoin(url, resp.headers["location"])
                    continue
                if resp.status_code == 403:
                    raise _Forbidden(url)
                if resp.status_code != 200 or "html" not in resp.headers.get("content-type", ""):
                    return None
                chunks, size = [], 0
                async for chunk in resp.aiter_bytes():
                    chunks.append(chunk)
                    size += len(chunk)
                    if size >= _MAX_BYTES:
                        break
                encoding = resp.encoding or "utf-8"
                return url, b"".join(chunks).decode(encoding, errors="replace")
    return None


async def fetch_preview(url: str) -> dict[str, str] | None:
    """Return {url,title,description,image,site} for a URL, or None."""
    now = time.monotonic()
    cached = _cache.get(url)
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    preview: dict[str, str] | None = None
    try:
        target = _fetch_target(url)
        try:
            fetched = await _fetch_html(target)
        except _Forbidden:
            fetched = await _fetch_html(target, _FALLBACK_USER_AGENT)
        if fetched:
            final_url, page = fetched
            parser = _MetaParser()
            parser.feed(page)
            meta = parser.meta
            title = meta.get("og:title") or meta.get("twitter:title") or parser.title.strip()
            if title:
                image = meta.get("og:image") or meta.get("twitter:image") or ""
                preview = {
                    "url": url,
                    "title": title[:200],
                    "description": (
                        meta.get("og:description") or meta.get("twitter:description") or meta.get("description") or ""
                    )[:300],
                    "image": urljoin(final_url, image) if image else "",
                    "site": meta.get("og:site_name") or (urlparse(url).hostname or ""),
                }
    except (httpx.HTTPError, UnicodeError, ValueError, _Forbidden) as exc:
        logger.info("link preview failed for %s: %s", url, exc)

    _cache[url] = (now, preview)
    if len(_cache) > 500:
        _cache.pop(next(iter(_cache)))
    return preview
