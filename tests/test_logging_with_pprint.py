import logging
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from data_downloader.downloader import (
    _download_data_httpx,
    _get_cookiejar,
    _new_file_from_web,
    async_download_datas,
    download_datas,
    logger,
    mp_download_datas,
)


class TestLoggingWithPprint:
    """Test logging with pprint"""

    @pytest.fixture
    def mock_logger(self):
        """Create mock logger"""
        with (
            patch.object(logger, "debug") as mock_debug,
            patch.object(logger, "info") as mock_info,
            patch.object(logger, "error") as mock_error,
        ):
            yield {"debug": mock_debug, "info": mock_info, "error": mock_error}

    def test_new_file_from_web_logging(self, mock_logger):
        """Test logging in _new_file_from_web function"""
        # Mock exception scenario
        r = MagicMock()
        r.headers.get.side_effect = ValueError("Test exception")

        # Call function
        result = _new_file_from_web(r, "test_file.txt")

        # Verify log recording
        mock_logger["debug"].assert_called_once()
        log_msg = mock_logger["debug"].call_args[0][0]

        # Verify pformat formatting
        assert "message" in log_msg
        assert "url" in log_msg
        assert "error" in log_msg
        assert "Test exception" in log_msg
        assert result is False

    def test_get_cookiejar_logging(self, mock_logger):
        """Test logging in _get_cookiejar function"""
        # Import module, ensure import path is correct
        with patch(
            "browser_cookie3.load", side_effect=Exception("Failed to load cookie")
        ):
            result = _get_cookiejar(True)

            # Verify log recording
            mock_logger["error"].assert_called_once()
            log_msg = mock_logger["error"].call_args[0][0]

            # Verify pformat formatting
            assert "message" in log_msg
            assert "error" in log_msg
            assert "info" in log_msg
            assert "Failed to load cookie" in log_msg
            assert result is None

    def test_download_data_httpx_logging(self, mock_logger):
        """Test logging in _download_data_httpx function"""
        # Mock client
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_client.get.return_value = mock_response

        # Mock breakpoint handling
        mock_response.status_code = 401  # Make the function return directly

        # Use Path object as parameter
        folder = Path("~/test_folder")

        # Mock _handle_status to return a value indicating "downloaded entirely"
        handle_status_patcher = patch("data_downloader.downloader._handle_status")
        mock_handle_status = handle_status_patcher.start()
        mock_handle_status.return_value = (True, "")  # 模拟 "downloaded entirely"

        try:
            # Call function
            result = _download_data_httpx(
                "http://example.com/test.txt",
                folder=folder,
                client=mock_client,
                authorize_from_browser=False,
            )

            # Verify function return value
            assert result is True

            # Verify log recording
            mock_logger["debug"].assert_called()
            log_msg = mock_logger["debug"].call_args[0][0]

            # Verify Path object has been safely converted
            assert "PosixPath" not in log_msg
            assert "WindowsPath" not in log_msg
            assert str(folder) in log_msg
        finally:
            handle_status_patcher.stop()

    @patch("data_downloader.downloader.requests")
    def test_download_datas_logging(self, mock_requests, mock_logger):
        """Test logging in download_datas function"""
        # Prepare test data
        urls = ["http://example.com/test1.txt", "http://example.com/test2.txt"]
        folder = Path("~/test_downloads")

        # Mock request session
        mock_session = MagicMock()
        mock_requests.Session.return_value = mock_session

        # Mock download data function to avoid actual calls
        with patch("data_downloader.downloader.download_data") as mock_download_data:
            download_datas(urls, folder)

            # Verify log recording
            mock_logger["info"].assert_called()
            log_msg = mock_logger["info"].call_args[0][0]

            # Verify pformat formatting
            assert "message" in log_msg
            assert "urls" in log_msg
            assert str(folder) in log_msg

            # Ensure URLs in list are correctly recorded
            assert "http://example.com/test1.txt" in log_msg
            assert "http://example.com/test2.txt" in log_msg

    @patch("data_downloader.downloader.mp")
    def test_mp_download_datas_logging(self, mock_mp, mock_logger):
        """Test logging in mp_download_datas function"""
        # Prepare test data
        urls = ["http://example.com/test1.txt", "http://example.com/test2.txt"]
        folder = Path("~/test_downloads")

        # Mock multiprocess pool
        mock_pool = MagicMock()
        mock_mp.Pool.return_value.__enter__.return_value = mock_pool

        # Mock progress bar
        with patch("data_downloader.downloader.tqdm") as mock_tqdm:
            # Call function
            mp_download_datas(urls, folder)

            # Verify log recording
            mock_logger["info"].assert_called()
            log_msg = mock_logger["info"].call_args_list[0][0][
                0
            ]  # First parameter of first call

            # Verify pformat formatting
            assert "message" in log_msg
            assert "urls" in log_msg
            assert str(folder) in log_msg

            # Ensure URLs in list are correctly recorded
            assert "http://example.com/test1.txt" in log_msg
            assert "http://example.com/test2.txt" in log_msg

    @patch("data_downloader.downloader.selectors")
    @patch("data_downloader.downloader.asyncio")
    def test_async_download_datas_logging(
        self, mock_asyncio, mock_selectors, mock_logger
    ):
        """Test logging in async_download_datas function"""
        # Prepare test data
        urls = ["http://example.com/test1.txt", "http://example.com/test2.txt"]
        folder = Path("~/test_downloads")

        # Mock event loop
        mock_loop = MagicMock()
        mock_asyncio.SelectorEventLoop.return_value = mock_loop

        # Call function
        async_download_datas(urls, folder)

        # Verify log recording
        mock_logger["info"].assert_called_once()
        log_msg = mock_logger["info"].call_args[0][0]

        # Verify pformat formatting
        assert "message" in log_msg
        assert "urls" in log_msg
        assert str(folder) in log_msg

        # Ensure URLs in list are correctly recorded
        assert "http://example.com/test1.txt" in log_msg
        assert "http://example.com/test2.txt" in log_msg

    def test_real_output_format(self):
        """Test actual output format"""
        # get original handlers
        original_handlers = list(logger.handlers)

        try:
            # temporarily clear all original handlers to avoid interference
            for handler in original_handlers:
                logger.removeHandler(handler)

            # set new handler to capture output
            captured_output = StringIO()
            handler = logging.StreamHandler(captured_output)
            handler.setFormatter(logging.Formatter("%(message)s"))  # only output message
            logger.addHandler(handler)

            # Ensure logger level is set correctly
            original_level = logger.level
            logger.setLevel(logging.INFO)

            # prepare test data
            urls = ["http://example.com/test1.txt", "http://example.com/test2.txt"]
            folder = Path("~/test_downloads")

            # Log directly
            params = {
                "message": "Testing pprint formatting",
                "urls": urls,
                "folder": folder,
            }
            from data_downloader.downloader import pformat, safe_repr

            logger.info(pformat(safe_repr(params), indent=4))

            # get output
            output = captured_output.getvalue()

            # verify output (output should only contain message content)
            assert "Testing pprint formatting" in output
            assert "urls" in output
            assert "folder" in output
            assert str(folder) in output
            assert "http://example.com/test1.txt" in output
            assert "http://example.com/test2.txt" in output

            # ensure output does not contain Path object class names
            assert "PosixPath" not in output
            assert "WindowsPath" not in output

        finally:
            # restore original settings
            logger.removeHandler(handler)
            logger.setLevel(original_level)

            # restore original handlers
            for h in original_handlers:
                logger.addHandler(h)
