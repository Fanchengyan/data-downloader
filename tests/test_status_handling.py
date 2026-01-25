"""Tests for HTTP status handling with DownloadAction and StatusResult."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest

from data_downloader.downloader import (
    RETRYABLE_STATUS_CODES,
    DownloadAction,
    StatusResult,
    _handle_status,
)


class MockResponse:
    """Mock HTTP response for testing (requests/httpx style with .status_code)."""

    def __init__(
        self,
        status_code: int,
        headers: dict[str, Any] | None = None,
        url: str = "https://example.com/file.txt",
    ):
        self.status_code = status_code
        self.headers = headers or {}
        self.url = url


class MockAiohttpResponse:
    """Mock aiohttp.ClientResponse (uses .status instead of .status_code)."""

    def __init__(
        self,
        status: int,
        headers: dict[str, Any] | None = None,
        url: str = "https://example.com/file.txt",
    ):
        self.status = status  # aiohttp uses .status
        self.headers = headers or {}
        self.url = url


class TestDownloadAction:
    """Test DownloadAction enum."""

    def test_enum_values(self):
        """Test DownloadAction enum has correct values."""
        assert DownloadAction.PROCEED.value == "proceed"
        assert DownloadAction.COMPLETED.value == "completed"
        assert DownloadAction.RETRY.value == "retry"
        assert DownloadAction.REDIRECT.value == "redirect"
        assert DownloadAction.FAIL.value == "fail"

    def test_enum_members(self):
        """Test DownloadAction has all expected members."""
        expected_members = {"PROCEED", "COMPLETED", "RETRY", "REDIRECT", "FAIL"}
        actual_members = {member.name for member in DownloadAction}
        assert actual_members == expected_members


class TestStatusResult:
    """Test StatusResult NamedTuple."""

    def test_status_result_completed(self):
        """Test StatusResult for completed download."""
        result = StatusResult(DownloadAction.COMPLETED)
        assert result.action == DownloadAction.COMPLETED
        assert result.extra is None

    def test_status_result_retry(self):
        """Test StatusResult for retry with status code."""
        result = StatusResult(DownloadAction.RETRY, 429)
        assert result.action == DownloadAction.RETRY
        assert result.extra == 429

    def test_status_result_redirect(self):
        """Test StatusResult for redirect with new URL."""
        new_url = "https://redirect.com/file.txt"
        result = StatusResult(DownloadAction.REDIRECT, new_url)
        assert result.action == DownloadAction.REDIRECT
        assert result.extra == new_url

    def test_status_result_proceed(self):
        """Test StatusResult for proceed action."""
        result = StatusResult(DownloadAction.PROCEED)
        assert result.action == DownloadAction.PROCEED
        assert result.extra is None

    def test_status_result_fail(self):
        """Test StatusResult for fail action."""
        result = StatusResult(DownloadAction.FAIL)
        assert result.action == DownloadAction.FAIL
        assert result.extra is None


class TestHandleStatus:
    """Test _handle_status function."""

    @pytest.fixture(autouse=True)
    def setup_globals(self):
        """Reset global variables before each test."""
        import data_downloader.downloader as dl

        dl.support_resume = False
        dl.pbar = None
        dl.remote_size = 0
        yield
        # Cleanup after test
        if dl.pbar is not None:
            dl.pbar.close()
            dl.pbar = None

    def test_handle_status_206_resume_supported(self, tmp_path):
        """Test 206 Partial Content response (resume supported)."""
        file_path = tmp_path / "test.txt"
        file_path.write_bytes(b"partial")
        local_size = file_path.stat().st_size

        response = MockResponse(
            206,
            headers={
                "Content-Range": f"bytes {local_size}-999/1000",
            },
        )

        with patch("data_downloader.downloader._new_file_from_web", return_value=False):
            result = _handle_status(
                response,
                "https://example.com/test.txt",
                local_size,
                "test.txt",
                file_path,
            )

        assert result.action == DownloadAction.PROCEED
        assert result.extra is None

        # Check global variables
        import data_downloader.downloader as dl

        assert dl.support_resume is True
        assert dl.remote_size == 1000

    def test_handle_status_206_already_complete(self, tmp_path):
        """Test 206 when local file is already complete."""
        file_path = tmp_path / "test.txt"
        file_path.write_bytes(b"x" * 1000)
        local_size = 1000

        response = MockResponse(
            206,
            headers={
                "Content-Range": "bytes 1000-1000/1000",
            },
        )

        with patch("data_downloader.downloader._new_file_from_web", return_value=False):
            result = _handle_status(
                response,
                "https://example.com/test.txt",
                local_size,
                "test.txt",
                file_path,
            )

        assert result.action == DownloadAction.COMPLETED
        assert result.extra is None

    def test_handle_status_200_fresh_download(self, tmp_path):
        """Test 200 OK for fresh download."""
        file_path = tmp_path / "test.txt"
        response = MockResponse(
            200,
            headers={
                "Content-length": "1000",
            },
        )

        result = _handle_status(
            response, "https://example.com/test.txt", 0, "test.txt", file_path
        )

        assert result.action == DownloadAction.PROCEED
        assert result.extra is None

        import data_downloader.downloader as dl

        assert dl.remote_size == 1000

    def test_handle_status_200_already_complete(self, tmp_path):
        """Test 200 when file already downloaded."""
        file_path = tmp_path / "test.txt"
        file_path.write_bytes(b"x" * 1000)
        local_size = 1000

        response = MockResponse(
            200,
            headers={
                "Content-length": "1000",
            },
        )

        with patch("data_downloader.downloader._new_file_from_web", return_value=False):
            result = _handle_status(
                response,
                "https://example.com/test.txt",
                local_size,
                "test.txt",
                file_path,
            )

        assert result.action == DownloadAction.COMPLETED
        assert result.extra is None

    def test_handle_status_200_redownload_partial(self, tmp_path):
        """Test 200 when partial file exists (server doesn't support resume)."""
        file_path = tmp_path / "test.txt"
        file_path.write_bytes(b"partial")
        local_size = len(b"partial")

        response = MockResponse(
            200,
            headers={
                "Content-length": "1000",
            },
        )

        with patch("data_downloader.downloader._new_file_from_web", return_value=False):
            result = _handle_status(
                response,
                "https://example.com/test.txt",
                local_size,
                "test.txt",
                file_path,
            )

        assert result.action == DownloadAction.PROCEED
        assert result.extra is None
        # File should be deleted for redownload
        assert not file_path.exists()

    @pytest.mark.parametrize("status_code", list(RETRYABLE_STATUS_CODES.keys()))
    def test_handle_status_retryable_codes(self, tmp_path, status_code):
        """Test all retryable status codes return RETRY action."""
        file_path = tmp_path / "test.txt"
        response = MockResponse(status_code)

        result = _handle_status(
            response, "https://example.com/test.txt", 0, "test.txt", file_path
        )

        assert result.action == DownloadAction.RETRY
        assert result.extra == status_code

    def test_handle_status_301_redirect(self, tmp_path):
        """Test 301 Moved Permanently redirect."""
        file_path = tmp_path / "test.txt"
        new_url = "https://newlocation.com/test.txt"
        response = MockResponse(
            301,
            headers={"Location": new_url},
        )

        result = _handle_status(
            response, "https://example.com/test.txt", 0, "test.txt", file_path
        )

        assert result.action == DownloadAction.REDIRECT
        assert result.extra == new_url

    def test_handle_status_302_redirect(self, tmp_path):
        """Test 302 Found redirect."""
        file_path = tmp_path / "test.txt"
        new_url = "https://newlocation.com/test.txt"
        response = MockResponse(
            302,
            headers={"Location": new_url},
        )

        result = _handle_status(
            response, "https://example.com/test.txt", 0, "test.txt", file_path
        )

        assert result.action == DownloadAction.REDIRECT
        assert result.extra == new_url

    def test_handle_status_401_unauthorized(self, tmp_path):
        """Test 401 Unauthorized."""
        file_path = tmp_path / "test.txt"
        response = MockResponse(401)

        result = _handle_status(
            response, "https://example.com/test.txt", 0, "test.txt", file_path
        )

        assert result.action == DownloadAction.FAIL
        assert result.extra is None

    def test_handle_status_403_forbidden(self, tmp_path):
        """Test 403 Forbidden."""
        file_path = tmp_path / "test.txt"
        response = MockResponse(403)

        result = _handle_status(
            response, "https://example.com/test.txt", 0, "test.txt", file_path
        )

        assert result.action == DownloadAction.FAIL
        assert result.extra is None

    def test_handle_status_404_not_found(self, tmp_path):
        """Test 404 Not Found."""
        file_path = tmp_path / "test.txt"
        response = MockResponse(404)

        result = _handle_status(
            response, "https://example.com/test.txt", 0, "test.txt", file_path
        )

        assert result.action == DownloadAction.FAIL
        assert result.extra is None

    def test_handle_status_unknown_error(self, tmp_path):
        """Test unknown status code defaults to FAIL."""
        file_path = tmp_path / "test.txt"
        response = MockResponse(418)  # I'm a teapot

        result = _handle_status(
            response, "https://example.com/test.txt", 0, "test.txt", file_path
        )

        assert result.action == DownloadAction.FAIL
        assert result.extra is None

    def test_handle_status_416_range_not_satisfiable(self, tmp_path):
        """Test 416 Range Not Satisfiable (file already complete)."""
        file_path = tmp_path / "test.txt"
        file_path.write_bytes(b"x" * 1000)
        local_size = 1000

        response = MockResponse(
            416,
            headers={
                "Content-Range": "bytes */1000",
            },
        )

        with patch("data_downloader.downloader._new_file_from_web", return_value=False):
            result = _handle_status(
                response,
                "https://example.com/test.txt",
                local_size,
                "test.txt",
                file_path,
            )

        assert result.action == DownloadAction.COMPLETED
        assert result.extra is None

        import data_downloader.downloader as dl

        assert dl.support_resume is True

    def test_handle_status_new_file_from_web(self, tmp_path):
        """Test handling when server has newer file."""
        file_path = tmp_path / "test.txt"
        file_path.write_bytes(b"old content")
        local_size = file_path.stat().st_size

        response = MockResponse(
            206,
            headers={
                "Content-Range": f"bytes {local_size}-999/1000",
            },
        )

        # Simulate newer file on server
        with patch("data_downloader.downloader._new_file_from_web", return_value=True):
            result = _handle_status(
                response,
                "https://example.com/test.txt",
                local_size,
                "test.txt",
                file_path,
            )

        # Should proceed with download but file should be deleted
        assert result.action == DownloadAction.PROCEED
        assert not file_path.exists()


class TestRetryableStatusCodes:
    """Test RETRYABLE_STATUS_CODES dictionary."""

    def test_retryable_codes_defined(self):
        """Test retryable status codes are properly defined."""
        expected_codes = {202, 408, 429, 500, 502, 503, 504}
        actual_codes = set(RETRYABLE_STATUS_CODES.keys())
        assert actual_codes == expected_codes

    def test_retryable_codes_have_descriptions(self):
        """Test all retryable codes have descriptions."""
        for code, description in RETRYABLE_STATUS_CODES.items():
            assert isinstance(code, int)
            assert isinstance(description, str)
            assert len(description) > 0

    def test_specific_retryable_codes(self):
        """Test specific retryable codes have correct descriptions."""
        assert "Accepted" in RETRYABLE_STATUS_CODES[202]
        assert "Timeout" in RETRYABLE_STATUS_CODES[408]
        assert "Too Many Requests" in RETRYABLE_STATUS_CODES[429]
        assert "Server Error" in RETRYABLE_STATUS_CODES[500]
        assert "Gateway" in RETRYABLE_STATUS_CODES[502]
        assert "Unavailable" in RETRYABLE_STATUS_CODES[503]
        assert "Timeout" in RETRYABLE_STATUS_CODES[504]


class TestAiohttpResponseHandling:
    """Test _handle_status with aiohttp.ClientResponse objects."""

    @pytest.fixture(autouse=True)
    def setup_globals(self):
        """Reset global variables before each test."""
        import data_downloader.downloader as dl

        dl.support_resume = False
        dl.pbar = None
        dl.remote_size = 0
        yield
        # Cleanup after test
        if dl.pbar is not None:
            dl.pbar.close()
            dl.pbar = None

    def test_aiohttp_200_response(self, tmp_path):
        """Test aiohttp response with 200 status."""
        file_path = tmp_path / "test.txt"
        response = MockAiohttpResponse(200, {"Content-length": "1000"})

        result = _handle_status(
            response, "https://example.com/test.txt", 0, "test.txt", file_path
        )

        assert result.action == DownloadAction.PROCEED
        assert result.extra is None

    def test_aiohttp_206_response(self, tmp_path):
        """Test aiohttp response with 206 Partial Content."""
        file_path = tmp_path / "test.txt"
        file_path.write_bytes(b"partial")
        local_size = file_path.stat().st_size

        response = MockAiohttpResponse(
            206,
            headers={
                "Content-Range": f"bytes {local_size}-999/1000",
            },
        )

        with patch("data_downloader.downloader._new_file_from_web", return_value=False):
            result = _handle_status(
                response,
                "https://example.com/test.txt",
                local_size,
                "test.txt",
                file_path,
            )

        assert result.action == DownloadAction.PROCEED
        assert result.extra is None

        # Check global variables
        import data_downloader.downloader as dl

        assert dl.support_resume is True
        assert dl.remote_size == 1000

    def test_aiohttp_429_retry(self, tmp_path):
        """Test aiohttp response with 429 Too Many Requests."""
        file_path = tmp_path / "test.txt"
        response = MockAiohttpResponse(429)

        result = _handle_status(
            response, "https://example.com/test.txt", 0, "test.txt", file_path
        )

        assert result.action == DownloadAction.RETRY
        assert result.extra == 429

    def test_aiohttp_301_redirect(self, tmp_path):
        """Test aiohttp response with 301 redirect."""
        file_path = tmp_path / "test.txt"
        new_url = "https://newlocation.com/test.txt"
        response = MockAiohttpResponse(301, headers={"Location": new_url})

        result = _handle_status(
            response, "https://example.com/test.txt", 0, "test.txt", file_path
        )

        assert result.action == DownloadAction.REDIRECT
        assert result.extra == new_url

    def test_aiohttp_401_unauthorized(self, tmp_path):
        """Test aiohttp response with 401 Unauthorized."""
        file_path = tmp_path / "test.txt"
        response = MockAiohttpResponse(401)

        result = _handle_status(
            response, "https://example.com/test.txt", 0, "test.txt", file_path
        )

        assert result.action == DownloadAction.FAIL
        assert result.extra is None

    def test_aiohttp_403_forbidden(self, tmp_path):
        """Test aiohttp response with 403 Forbidden."""
        file_path = tmp_path / "test.txt"
        response = MockAiohttpResponse(403)

        result = _handle_status(
            response, "https://example.com/test.txt", 0, "test.txt", file_path
        )

        assert result.action == DownloadAction.FAIL
        assert result.extra is None

    @pytest.mark.parametrize("status_code", list(RETRYABLE_STATUS_CODES.keys()))
    def test_aiohttp_retryable_codes(self, tmp_path, status_code):
        """Test aiohttp responses with all retryable status codes."""
        file_path = tmp_path / "test.txt"
        response = MockAiohttpResponse(status_code)

        result = _handle_status(
            response, "https://example.com/test.txt", 0, "test.txt", file_path
        )

        assert result.action == DownloadAction.RETRY
        assert result.extra == status_code

    def test_invalid_response_object(self, tmp_path):
        """Test _handle_status with invalid response object (no status attribute)."""
        file_path = tmp_path / "test.txt"

        # Create object with neither .status_code nor .status
        invalid_response = Mock(spec=[])  # Empty spec, no attributes

        result = _handle_status(
            invalid_response, "https://example.com/test.txt", 0, "test.txt", file_path
        )

        # Should fail gracefully
        assert result.action == DownloadAction.FAIL
        assert result.extra is None


class TestMixedResponseTypes:
    """Test that _handle_status works with all three HTTP library response types."""

    @pytest.fixture(autouse=True)
    def setup_globals(self):
        """Reset global variables before each test."""
        import data_downloader.downloader as dl

        dl.support_resume = False
        dl.pbar = None
        dl.remote_size = 0
        yield
        if dl.pbar is not None:
            dl.pbar.close()
            dl.pbar = None

    def test_requests_style_response(self, tmp_path):
        """Test with requests-style response (.status_code)."""
        file_path = tmp_path / "test.txt"
        response = MockResponse(200, {"Content-length": "1000"})

        result = _handle_status(
            response, "https://example.com/test.txt", 0, "test.txt", file_path
        )

        assert result.action == DownloadAction.PROCEED

    def test_aiohttp_style_response(self, tmp_path):
        """Test with aiohttp-style response (.status)."""
        file_path = tmp_path / "test.txt"
        response = MockAiohttpResponse(200, {"Content-length": "1000"})

        result = _handle_status(
            response, "https://example.com/test.txt", 0, "test.txt", file_path
        )

        assert result.action == DownloadAction.PROCEED

    def test_both_response_types_same_behavior(self, tmp_path):
        """Test that both response types produce identical results."""
        file_path1 = tmp_path / "test1.txt"
        file_path2 = tmp_path / "test2.txt"

        # Same status code, same headers
        requests_response = MockResponse(429, {"Retry-After": "60"})
        aiohttp_response = MockAiohttpResponse(429, {"Retry-After": "60"})

        result1 = _handle_status(
            requests_response,
            "https://example.com/test.txt",
            0,
            "test1.txt",
            file_path1,
        )

        result2 = _handle_status(
            aiohttp_response, "https://example.com/test.txt", 0, "test2.txt", file_path2
        )

        # Both should produce identical results
        assert result1.action == result2.action == DownloadAction.RETRY
        assert result1.extra == result2.extra == 429
