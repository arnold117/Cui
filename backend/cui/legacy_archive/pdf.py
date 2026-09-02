"""v4 PDF download/hash helpers — ported from LitScribe ``services/pdf.py``.

Cherry-picked pure logic only (plan T6 item 2, ``docs/plan-v5-slice0.md`` §T6
「pdf.py(下载/哈希,无 MinerU 依赖部分)」):

- ``download_pdf`` — fetch PDF bytes from a URL over httpx, following redirects,
  with a 25 s default timeout (Cui network-adapter convention, cf. arxiv.py;
  v4 hard-coded 60 s).
- ``content_hash`` — md5 content hash truncated to 16 hex chars, the v4 rule
  for cache keys and content-addressed file names.
- ``pdf_file_name`` — deterministic content-addressed ``{hash}.pdf`` name so
  identical bytes dedupe on disk. v4 cached parsed results as ``{hash}.json``
  and composed cache names from the local file stem; here the artifact is the
  raw PDF and the untrusted stem is deliberately dropped.

解析部分未搬,见 plan T6: the pymupdf4llm markdown conversion, section/table
extraction and the parsed-result JSON cache were left in v4 — they pull in a
parse engine (MinerU-class dependency) that Cui's native pipeline has no
consumer for. Ported surface has no domain/llm/store imports and no
module-global mutable state: only stdlib ``hashlib`` + ``httpx``.
"""

from __future__ import annotations

import hashlib

import httpx

# Default download timeout (seconds). Cui network-adapter convention.
DOWNLOAD_TIMEOUT_SECONDS = 25.0

# Number of leading md5 hex chars used as the content fingerprint.
_HASH_LENGTH = 16


def content_hash(data: bytes) -> str:
    """Fingerprint PDF bytes: md5 truncated to 16 lowercase hex chars.

    This is the exact v4 rule (``hashlib.md5(pdf_bytes).hexdigest()[:16]``)
    that keyed the download cache, so hashes produced here stay compatible
    with any content-addressed artifact named under the old scheme.

    Raises:
        TypeError: *data* is not ``bytes`` (deliberately strict — a ``str``
            would silently hash a different encoding and a different PDF).
    """
    if not isinstance(data, bytes):
        raise TypeError(f"data must be bytes, got {type(data).__name__}")
    return hashlib.md5(data).hexdigest()[: _HASH_LENGTH]


def pdf_file_name(data: bytes) -> str:
    """Content-addressed file name for a downloaded PDF: ``{hash}.pdf``.

    The name is fully derived from the bytes (``content_hash``), so it is
    deterministic, collision-free for differing content, portable across
    platforms (lowercase hex + ``.pdf``) and free of any untrusted URL or
    paper-title component.

    Raises:
        TypeError: *data* is not ``bytes`` (see :func:`content_hash`).
    """
    return f"{content_hash(data)}.pdf"


def _validate_url(url: str) -> None:
    """Reject non-URLs before any client or network work happens."""
    if not isinstance(url, str):
        raise TypeError(f"url must be a str, got {type(url).__name__}")
    if not url.strip():
        raise ValueError("url must be a non-empty http(s) URL")


def _validate_timeout(timeout: float) -> None:
    """Reject non-numeric or non-positive timeout values."""
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
        raise TypeError(f"timeout must be a number of seconds, got {type(timeout).__name__}")
    if timeout <= 0:
        raise ValueError("timeout must be positive (seconds)")


async def download_pdf(
    url: str,
    *,
    timeout: float = DOWNLOAD_TIMEOUT_SECONDS,
    follow_redirects: bool = True,
    transport: httpx.AsyncBaseTransport | None = None,
) -> bytes:
    """Download PDF bytes from *url* (port of v4 ``PDFService._download``).

    A fresh ``httpx.AsyncClient`` is created per call (no module-global
    client). Redirects are followed and the response is checked via
    ``raise_for_status``, so HTTP errors surface as ``httpx.HTTPStatusError``
    and transport failures as ``httpx.RequestError``.

    Args:
        url: http(s) URL of the PDF.
        timeout: per-request timeout in seconds (default 25 s). Must be > 0.
        follow_redirects: follow 3xx redirects (default True).
        transport: test seam only (e.g. ``httpx.MockTransport``); production
            callers leave it ``None`` so a real connection pool is used.

    Returns:
        Raw PDF bytes.

    Raises:
        TypeError: *url* not a str, or *timeout* not a number.
        ValueError: blank *url* or non-positive *timeout*.
        httpx.HTTPStatusError: response status >= 400.
        httpx.RequestError: connection/timeout-level failure.
    """
    _validate_url(url)
    _validate_timeout(timeout)
    async with httpx.AsyncClient(
        follow_redirects=follow_redirects,
        timeout=timeout,
        transport=transport,
    ) as client:
        return await _fetch(client, url)


async def _fetch(client: httpx.AsyncClient, url: str) -> bytes:
    """GET *url* on an existing client, raising on HTTP errors.

    Kept separate so tests can drive the real request path with an injected
    client (``httpx.AsyncClient(transport=httpx.MockTransport(...))``) —
    never a real network call.
    """
    resp = await client.get(url)
    resp.raise_for_status()
    return resp.content
