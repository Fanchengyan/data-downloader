"""Tests for retry logic with _max_retries parameter."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest
import requests

from data_downloader.downloader import (
    DownloadAction,
    StatusResult,
    _download_data_requests,
)


class MockResponse:
    """Mock HTTP response for testing."""

    def __init__(
        self,
        status_code: int,
        headers: dict[str, Any] | None = None,
        url: str = "https://example.com/file.txt",
        content: bytes = b"test content",
    ):
        self.status_code = status_code
        self.headers = headers or {}
        self.url = url
        self.content = content
        self._content_iter = iter([content])

    def close(self):
        """Mock close method."""
        pass

    def iter_content(self, chunk_size: int = 1024):
        """Mock iter_content for streaming."""
        return self._content_iter

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class TestMaxRetriesParameter:
    """Test _max_retries internal parameter tracking."""

    @patch("data_downloader.downloader._get_cookiejar")
    @patch("data_downloader.downloader._handle_status")
    @patch("data_downloader.downloader._parse_file_name")
    def test_max_retries_initialized_on_first_call(
        self, mock_parse_name, mock_handle_status, mock_cookiejar, tmp_path
    ):
        """Test _max_retries is set to retry value on first call."""
        mock_cookiejar.return_value = None
        mock_parse_name.return_value = "test.txt"

        # Mock successful download
        mock_handle_status.return_value = StatusResult(DownloadAction.COMPLETED)

        # Create mock session
        mock_session = Mock()
        mock_response = MockResponse(200, {"Content-length": "100"})
        mock_session.get.return_value = mock_response

        # Call with retry=5
        result = _download_data_requests(
            "https://example.com/test.txt",
            folder=str(tmp_path),
            client=mock_session,
            retry=5,
        )

        # Verify _handle_status was called
        assert mock_handle_status.called
        assert result is True

    @patch("data_downloader.downloader._get_cookiejar")
    @patch("data_downloader.downloader._handle_status")
    @patch("data_downloader.downloader._parse_file_name")
    @patch("data_downloader.downloader.time.sleep")  # Skip actual sleep
    def test_retry_preserves_max_retries(
        self, mock_sleep, mock_parse_name, mock_handle_status, mock_cookiejar, tmp_path
    ):
        """Test _max_retries is preserved across retry attempts."""
        mock_cookiejar.return_value = None
        mock_parse_name.return_value = "test.txt"
        mock_sleep.return_value = None

        # Track call count
        call_count = 0

        def handle_status_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                # First 2 calls: retry
                return StatusResult(DownloadAction.RETRY, 429)
            # Third call: success
            return StatusResult(DownloadAction.COMPLETED)

        mock_handle_status.side_effect = handle_status_side_effect

        mock_session = Mock()
        mock_response = MockResponse(429)
        mock_session.get.return_value = mock_response

        # Call with retry=5
        result = _download_data_requests(
            "https://example.com/test.txt",
            folder=str(tmp_path),
            client=mock_session,
            retry=5,
        )

        assert result is True
        # Should be called 3 times (2 retries + 1 success)
        assert call_count == 3

    @patch("data_downloader.downloader._get_cookiejar")
    @patch("data_downloader.downloader._handle_status")
    @patch("data_downloader.downloader._parse_file_name")
    @patch("data_downloader.downloader.time.sleep")
    def test_retry_count_decrements_correctly(
        self, mock_sleep, mock_parse_name, mock_handle_status, mock_cookiejar, tmp_path
    ):
        """Test retry count decrements on each retry."""
        mock_cookiejar.return_value = None
        mock_parse_name.return_value = "test.txt"
        mock_sleep.return_value = None

        # Always return RETRY status
        mock_handle_status.return_value = StatusResult(DownloadAction.RETRY, 503)

        mock_session = Mock()
        mock_response = MockResponse(503)
        mock_session.get.return_value = mock_response

        # Call with retry=3 (should fail after 3 attempts)
        result = _download_data_requests(
            "https://example.com/test.txt",
            folder=str(tmp_path),
            client=mock_session,
            retry=3,
        )

        assert result is False
        # Should be called 4 times (initial + 3 retries, all fail)
        assert mock_handle_status.call_count == 4

    @patch("data_downloader.downloader._get_cookiejar")
    @patch("data_downloader.downloader._handle_status")
    @patch("data_downloader.downloader._parse_file_name")
    @patch("data_downloader.downloader.time.sleep")
    @patch("data_downloader.downloader.logger")
    def test_retry_logging_shows_correct_attempt_numbers(
        self,
        mock_logger,
        mock_sleep,
        mock_parse_name,
        mock_handle_status,
        mock_cookiejar,
        tmp_path,
    ):
        """Test retry logging shows correct attempt X/Y format."""
        mock_cookiejar.return_value = None
        mock_parse_name.return_value = "test.txt"
        mock_sleep.return_value = None

        call_count = 0

        def handle_status_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # First 4 calls return RETRY, 5th returns COMPLETED
            # This means: initial call + 3 retries, then success
            if call_count <= 4:
                return StatusResult(DownloadAction.RETRY, 429)
            return StatusResult(DownloadAction.COMPLETED)

        mock_handle_status.side_effect = handle_status_side_effect

        mock_session = Mock()
        mock_response = MockResponse(429, {"Retry-After": "1"})
        mock_session.get.return_value = mock_response

        # Call with retry=5
        _download_data_requests(
            "https://example.com/test.txt",
            folder=str(tmp_path),
            client=mock_session,
            retry=5,
        )

        # Check that logger.info and logger.warning were called with correct attempt numbers
        info_calls = [call for call in mock_logger.info.call_args_list]
        warning_calls = [call for call in mock_logger.warning.call_args_list]
        all_calls = info_calls + warning_calls

        # Find retry log messages (from both info and warning)
        retry_logs = [
            call
            for call in all_calls
            if "Retrying" in str(call)
            and ("attempt" in str(call) or "remaining" in str(call))
        ]

        # Should have at least 3 retry logs
        assert len(retry_logs) >= 3

        # Verify the format includes "/5" or "5" in the messages
        retry_messages = [str(call) for call in retry_logs]
        # Should see "/5" or "5" in the messages (max_retries=5)
        assert any("/5" in msg or "5)" in msg for msg in retry_messages)

    @patch("data_downloader.downloader._get_cookiejar")
    @patch("data_downloader.downloader._handle_status")
    @patch("data_downloader.downloader._parse_file_name")
    @patch("data_downloader.downloader.time.sleep")
    @patch("data_downloader.downloader.logger")
    def test_max_retries_not_hardcoded_to_10(
        self,
        mock_logger,
        mock_sleep,
        mock_parse_name,
        mock_handle_status,
        mock_cookiejar,
        tmp_path,
    ):
        """Test max retries uses actual retry parameter, not hardcoded 10."""
        mock_cookiejar.return_value = None
        mock_parse_name.return_value = "test.txt"
        mock_sleep.return_value = None

        # Always return RETRY
        mock_handle_status.return_value = StatusResult(DownloadAction.RETRY, 503)

        mock_session = Mock()
        mock_response = MockResponse(503)
        mock_session.get.return_value = mock_response

        # Test with retry=20 (not 10)
        _download_data_requests(
            "https://example.com/test.txt",
            folder=str(tmp_path),
            client=mock_session,
            retry=20,
        )

        # Check error log for max retries message
        error_calls = [call for call in mock_logger.error.call_args_list]

        # Find the "Max retries exceeded" message
        max_retry_msgs = [
            call
            for call in error_calls
            if "Max retries" in str(call) and "exceeded" in str(call)
        ]

        assert len(max_retry_msgs) > 0

        # Verify it says "20" not "10"
        max_retry_str = str(max_retry_msgs[0])
        assert "20" in max_retry_str
        # Make sure it's not hardcoded to 10
        # (Note: there might be "10" in other parts like line numbers, so check context)
        # The key is that the retry count in the message should be 20

    @patch("data_downloader.downloader._get_cookiejar")
    @patch("data_downloader.downloader._handle_status")
    @patch("data_downloader.downloader._parse_file_name")
    @patch("data_downloader.downloader.time.sleep")
    def test_redirect_preserves_max_retries(
        self, mock_sleep, mock_parse_name, mock_handle_status, mock_cookiejar, tmp_path
    ):
        """Test _max_retries is preserved through redirects."""
        mock_cookiejar.return_value = None
        mock_parse_name.return_value = "test.txt"
        mock_sleep.return_value = None

        call_count = 0

        def handle_status_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call: redirect
                return StatusResult(
                    DownloadAction.REDIRECT, "https://redirect.com/test.txt"
                )
            if call_count == 2:
                # Second call (after redirect): retry
                return StatusResult(DownloadAction.RETRY, 429)
            # Third call: success
            return StatusResult(DownloadAction.COMPLETED)

        mock_handle_status.side_effect = handle_status_side_effect

        mock_session = Mock()
        mock_response = MockResponse(301, {"Location": "https://redirect.com/test.txt"})
        mock_session.get.return_value = mock_response

        # Call with retry=7
        result = _download_data_requests(
            "https://example.com/test.txt",
            folder=str(tmp_path),
            client=mock_session,
            retry=7,
        )

        assert result is True
        assert call_count == 3

    @patch("data_downloader.downloader._get_cookiejar")
    @patch("data_downloader.downloader._handle_status")
    @patch("data_downloader.downloader._parse_file_name")
    @patch("data_downloader.downloader.time.sleep")
    @patch("data_downloader.downloader.logger")
    def test_warning_when_few_retries_remaining(
        self,
        mock_logger,
        mock_sleep,
        mock_parse_name,
        mock_handle_status,
        mock_cookiejar,
        tmp_path,
    ):
        """Test warning is logged when 3 or fewer retries remaining."""
        mock_cookiejar.return_value = None
        mock_parse_name.return_value = "test.txt"
        mock_sleep.return_value = None

        call_count = 0

        def handle_status_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return StatusResult(DownloadAction.RETRY, 503)
            return StatusResult(DownloadAction.COMPLETED)

        mock_handle_status.side_effect = handle_status_side_effect

        mock_session = Mock()
        mock_response = MockResponse(503)
        mock_session.get.return_value = mock_response

        # Call with retry=3, so by second retry we're at "1 attempt remaining"
        _download_data_requests(
            "https://example.com/test.txt",
            folder=str(tmp_path),
            client=mock_session,
            retry=3,
        )

        # Check for warning logs
        warning_calls = [call for call in mock_logger.warning.call_args_list]

        # Should have warning about remaining attempts
        retry_warnings = [
            call for call in warning_calls if "remaining" in str(call).lower()
        ]

        # At least one warning should be present
        assert len(retry_warnings) > 0


class TestRetryWaitTime:
    """Test retry wait time calculation."""

    @patch("data_downloader.downloader._get_cookiejar")
    @patch("data_downloader.downloader._handle_status")
    @patch("data_downloader.downloader._parse_file_name")
    @patch("data_downloader.downloader.time.sleep")
    def test_retry_waits_before_retrying(
        self, mock_sleep, mock_parse_name, mock_handle_status, mock_cookiejar, tmp_path
    ):
        """Test that retry logic calls time.sleep."""
        mock_cookiejar.return_value = None
        mock_parse_name.return_value = "test.txt"

        call_count = 0

        def handle_status_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return StatusResult(DownloadAction.RETRY, 503)
            return StatusResult(DownloadAction.COMPLETED)

        mock_handle_status.side_effect = handle_status_side_effect

        mock_session = Mock()
        mock_response = MockResponse(503)
        mock_session.get.return_value = mock_response

        _download_data_requests(
            "https://example.com/test.txt",
            folder=str(tmp_path),
            client=mock_session,
            retry=5,
        )

        # time.sleep should be called at least once for the retry
        assert mock_sleep.call_count >= 1

    @patch("data_downloader.downloader._get_cookiejar")
    @patch("data_downloader.downloader._handle_status")
    @patch("data_downloader.downloader._parse_file_name")
    @patch("data_downloader.downloader.time.sleep")
    @patch("data_downloader.downloader._get_retry_wait_time")
    def test_retry_uses_custom_wait_time(
        self,
        mock_get_wait,
        mock_sleep,
        mock_parse_name,
        mock_handle_status,
        mock_cookiejar,
        tmp_path,
    ):
        """Test that retry uses wait time from _get_retry_wait_time."""
        mock_cookiejar.return_value = None
        mock_parse_name.return_value = "test.txt"
        mock_get_wait.return_value = 2.5

        call_count = 0

        def handle_status_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return StatusResult(DownloadAction.RETRY, 429)
            return StatusResult(DownloadAction.COMPLETED)

        mock_handle_status.side_effect = handle_status_side_effect

        mock_session = Mock()
        mock_response = MockResponse(429, {"Retry-After": "5"})
        mock_session.get.return_value = mock_response

        _download_data_requests(
            "https://example.com/test.txt",
            folder=str(tmp_path),
            client=mock_session,
            retry=5,
        )

        # _get_retry_wait_time should be called
        assert mock_get_wait.called

        # time.sleep should be called with the returned wait time
        mock_sleep.assert_called_with(2.5)
