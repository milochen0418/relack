"""URL detection and Open Graph link previews for chat messages."""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
import re
import socket
import time
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

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

_TIMEOUT_SECONDS = 4.0
_MAX_BYTES = 512 * 1024
_MAX_REDIRECTS = 3
_CACHE_TTL_SECONDS = 600
_cache: dict[str, tuple[float, dict[str, str] | None]] = {}


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
    if _ALLOW_PRIVATE:
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


async def _fetch_html(url: str) -> tuple[str, str] | None:
    """Fetch up to _MAX_BYTES of an HTML page, re-checking every redirect hop."""
    headers = {"User-Agent": "RelackBot/1.0 (link preview)", "Accept": "text/html"}
    async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS, follow_redirects=False) as client:
        for _ in range(_MAX_REDIRECTS + 1):
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https") or not parsed.hostname:
                return None
            if not await _is_public_host(parsed.hostname):
                return None
            async with client.stream("GET", url, headers=headers) as resp:
                if resp.is_redirect and "location" in resp.headers:
                    url = urljoin(url, resp.headers["location"])
                    continue
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
        fetched = await _fetch_html(_fetch_target(url))
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
    except (httpx.HTTPError, UnicodeError, ValueError) as exc:
        logger.info("link preview failed for %s: %s", url, exc)

    _cache[url] = (now, preview)
    if len(_cache) > 500:
        _cache.pop(next(iter(_cache)))
    return preview
