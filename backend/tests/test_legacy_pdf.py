"""Unit tests for ``cui.legacy_archive.pdf`` (plan T6 item 2 port).

Pure-logic coverage only — no real network requests, ever: the httpx download
paths run against an in-process ``httpx.MockTransport``, and every other test
never builds an HTTP client at all.

Hash vectors are the standard md5 prefixes (md5(b"") = d41d8cd…, etc.),
independently checkable.
"""

from __future__ import annotations

import httpx
import pytest

from cui.legacy_archive.pdf import (
    DOWNLOAD_TIMEOUT_SECONDS,
    content_hash,
    download_pdf,
    pdf_file_name,
)

PDF_BYTES = b"%PDF-1.4\n"
OTHER_PDF_BYTES = b"%PDF-1.7\n%%EOF\n"

# hashlib.md5(...).hexdigest()[:16], precomputed
_EMPTY_HASH = "d41d8cd98f00b204"  # md5(b"")
_HELLO_HASH = "5d41402abc4b2a76"  # md5(b"hello")
_PDF_HASH = "6446a98080f5e51a"  # md5(b"%PDF-1.4\n")
_OTHER_PDF_HASH = "088240631be74d56"  # md5(b"%PDF-1.7\n%%EOF\n")


class TestContentHash:
    def test_known_vectors(self):
        assert content_hash(b"") == _EMPTY_HASH
        assert content_hash(b"hello") == _HELLO_HASH
        assert content_hash(PDF_BYTES) == _PDF_HASH
        assert content_hash(OTHER_PDF_BYTES) == _OTHER_PDF_HASH

    def test_returns_16_lowercase_hex_chars(self):
        h = content_hash(PDF_BYTES)
        assert len(h) == 16
        assert all(c in "0123456789abcdef" for c in h)

    def test_deterministic(self):
        assert content_hash(PDF_BYTES) == content_hash(PDF_BYTES)

    def test_single_byte_difference_changes_hash(self):
        assert content_hash(b"%PDF-1.4\n") != content_hash(b"%PDF-1.5\n")

    def test_rejects_non_bytes(self):
        for bad in ("%PDF-1.4\n", None, 42, ["%PDF"], {"b": b"%PDF"}):
            with pytest.raises(TypeError):
                content_hash(bad)  # type: ignore[arg-type]


class TestPdfFileName:
    def test_name_is_hash_plus_pdf_suffix(self):
        assert pdf_file_name(PDF_BYTES) == f"{_PDF_HASH}.pdf"
        assert pdf_file_name(b"") == f"{_EMPTY_HASH}.pdf"

    def test_name_shape_is_portable(self):
        name = pdf_file_name(PDF_BYTES)
        # lowercase hex + ".pdf" → no path separators, no case ambiguity
        assert name == name.lower()
        assert "/" not in name and "\\" not in name
        assert name.endswith(".pdf")
        assert len(name) == len(_PDF_HASH) + len(".pdf")

    def test_content_addressed_dedupes(self):
        # identical bytes → identical name; differing bytes → differing name
        assert pdf_file_name(PDF_BYTES) == pdf_file_name(PDF_BYTES)
        assert pdf_file_name(PDF_BYTES) != pdf_file_name(OTHER_PDF_BYTES)

    def test_rejects_non_bytes(self):
        with pytest.raises(TypeError):
            pdf_file_name("not bytes")  # type: ignore[arg-type]


class TestDownloadDefaults:
    def test_default_timeout_is_25s(self):
        # Contract fixed by the port (v4 used 60 s; Cui convention is 25 s).
        assert DOWNLOAD_TIMEOUT_SECONDS == 25.0


class TestDownloadPdfValidation:
    """Boundary checks — all raise before any client/network work happens."""

    @pytest.mark.parametrize("bad_url", ["", "   ", "\t\n"])
    async def test_blank_url_rejected(self, bad_url):
        with pytest.raises(ValueError, match="non-empty"):
            await download_pdf(bad_url)

    @pytest.mark.parametrize("bad_url", [None, 42, ["https://example.org/a.pdf"]])
    async def test_non_str_url_rejected(self, bad_url):
        with pytest.raises(TypeError):
            await download_pdf(bad_url)  # type: ignore[arg-type]

    @pytest.mark.parametrize("bad_timeout", [0, -1, -0.5])
    async def test_non_positive_timeout_rejected(self, bad_timeout):
        with pytest.raises(ValueError, match="positive"):
            await download_pdf("https://example.org/a.pdf", timeout=bad_timeout)

    @pytest.mark.parametrize("bad_timeout", [True, "25", None, [25]])
    async def test_non_numeric_timeout_rejected(self, bad_timeout):
        with pytest.raises(TypeError):
            await download_pdf("https://example.org/a.pdf", timeout=bad_timeout)  # type: ignore[arg-type]


class TestDownloadPdfViaMockTransport:
    """End-to-end request path against httpx.MockTransport — zero network."""

    @staticmethod
    def _transport(handler) -> httpx.MockTransport:
        return httpx.MockTransport(handler)

    async def test_success_returns_pdf_bytes(self):
        seen = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request.url)
            return httpx.Response(200, content=PDF_BYTES)

        result = await download_pdf(
            "https://example.org/a.pdf",
            transport=self._transport(handler),
        )
        assert result == PDF_BYTES
        assert seen == ["https://example.org/a.pdf"]

    async def test_redirects_are_followed_by_default(self):
        seen = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request.url)
            if request.url.path == "/a.pdf":
                return httpx.Response(302, headers={"location": "/b.pdf"})
            return httpx.Response(200, content=PDF_BYTES)

        result = await download_pdf(
            "https://example.org/a.pdf",
            transport=self._transport(handler),
        )
        assert result == PDF_BYTES
        assert seen == ["https://example.org/a.pdf", "https://example.org/b.pdf"]

    async def test_redirect_can_be_disabled(self):
        seen = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request.url)
            return httpx.Response(302, headers={"location": "/b.pdf"})

        # httpx.raise_for_status treats an unfollowed 3xx as an error, so a
        # disabled redirect surfaces as HTTPStatusError — never a silent body.
        with pytest.raises(httpx.HTTPStatusError) as exc:
            await download_pdf(
                "https://example.org/a.pdf",
                follow_redirects=False,
                transport=self._transport(handler),
            )
        assert exc.value.response.status_code == 302
        assert seen == ["https://example.org/a.pdf"]

    @pytest.mark.parametrize("status", [404, 500, 503])
    async def test_http_error_raises_http_status_error(self, status):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status, text=f"boom {status}")

        with pytest.raises(httpx.HTTPStatusError) as exc:
            await download_pdf(
                "https://example.org/missing.pdf",
                transport=self._transport(handler),
            )
        assert exc.value.response.status_code == status
        assert "missing.pdf" in str(exc.value)
