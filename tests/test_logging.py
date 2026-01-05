"""Tests for data_downloader.logging module."""

import io
import logging
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from tqdm import tqdm

from data_downloader.logging import (
    SUCCESS,
    EnhancedLogger,
    _TqdmLoggingHandler,
    color_formatter,
    file_formatter,
    formatter,
    setup_logger,
    stream_handler,
    tqdm_handler,
)


class TestConstants:
    """Test logging constants."""

    def test_success_level(self):
        """Test SUCCESS log level is properly defined."""
        assert SUCCESS == 25
        assert logging.getLevelName(SUCCESS) == "SUCCESS"


class TestFormatters:
    """Test logging formatters."""

    def test_formatter(self):
        """Test basic formatter."""
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        formatted = formatter.format(record)
        assert "INFO" in formatted
        assert "test.py:10" in formatted
        assert "Test message" in formatted

    def test_color_formatter(self):
        """Test color formatter."""
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        formatted = color_formatter.format(record)
        assert "INFO" in formatted
        assert "test" in formatted
        assert "Test message" in formatted

    def test_file_formatter(self):
        """Test file formatter."""
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        formatted = file_formatter.format(record)
        assert "INFO" in formatted
        assert "test" in formatted
        assert "test.py:10" in formatted
        assert "Test message" in formatted


class TestTqdmLoggingHandler:
    """Test _TqdmLoggingHandler class."""

    def test_init_default(self):
        """Test handler initialization with default tqdm class."""
        handler = _TqdmLoggingHandler()
        assert handler.tqdm_class == tqdm

    def test_init_custom_tqdm(self):
        """Test handler initialization with custom tqdm class."""
        mock_tqdm = Mock()
        handler = _TqdmLoggingHandler(tqdm_class=mock_tqdm)
        assert handler.tqdm_class == mock_tqdm

    def test_emit_success(self):
        """Test successful log emission."""
        mock_tqdm = Mock()
        handler = _TqdmLoggingHandler(tqdm_class=mock_tqdm)
        handler.setFormatter(formatter)
        
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        
        handler.emit(record)
        mock_tqdm.write.assert_called_once()

    def test_emit_keyboard_interrupt(self):
        """Test that KeyboardInterrupt is re-raised."""
        mock_tqdm = Mock()
        mock_tqdm.write.side_effect = KeyboardInterrupt()
        handler = _TqdmLoggingHandler(tqdm_class=mock_tqdm)
        
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        
        with pytest.raises(KeyboardInterrupt):
            handler.emit(record)

    def test_emit_system_exit(self):
        """Test that SystemExit is re-raised."""
        mock_tqdm = Mock()
        mock_tqdm.write.side_effect = SystemExit()
        handler = _TqdmLoggingHandler(tqdm_class=mock_tqdm)
        
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        
        with pytest.raises(SystemExit):
            handler.emit(record)

    def test_emit_exception_handling(self):
        """Test exception handling in emit method."""
        mock_tqdm = Mock()
        mock_tqdm.write.side_effect = Exception("Test error")
        handler = _TqdmLoggingHandler(tqdm_class=mock_tqdm)
        
        with patch.object(handler, 'handleError') as mock_handle_error:
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="test.py",
                lineno=10,
                msg="Test message",
                args=(),
                exc_info=None,
            )
            
            handler.emit(record)
            mock_handle_error.assert_called_once_with(record)


class TestEnhancedLogger:
    """Test EnhancedLogger class."""

    def test_success_method(self):
        """Test success method."""
        logger = EnhancedLogger("test")
        logger.setLevel(logging.DEBUG)
        
        # Capture log output
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
        logger.success("Success message")
        
        output = stream.getvalue()
        assert "SUCCESS" in output
        assert "Success message" in output

    def test_success_method_with_args(self):
        """Test success method with arguments."""
        logger = EnhancedLogger("test")
        logger.setLevel(logging.DEBUG)
        
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
        logger.success("Success %s", "test")
        
        output = stream.getvalue()
        assert "SUCCESS" in output
        assert "Success test" in output

    def test_success_method_level_check(self):
        """Test success method respects log level."""
        logger = EnhancedLogger("test")
        logger.setLevel(logging.ERROR)  # Higher than SUCCESS
        
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
        logger.success("Success message")
        
        output = stream.getvalue()
        assert output == ""  # No output because level is too high


class TestHandlers:
    """Test predefined handlers."""

    def test_stream_handler(self):
        """Test stream handler configuration."""
        assert isinstance(stream_handler, logging.StreamHandler)
        assert stream_handler.formatter == color_formatter

    def test_tqdm_handler(self):
        """Test tqdm handler configuration."""
        assert isinstance(tqdm_handler, _TqdmLoggingHandler)
        assert tqdm_handler.level == logging.INFO
        assert tqdm_handler.formatter == color_formatter


class TestSetupLogger:
    """Test setup_logger function."""

    def teardown_method(self):
        """Clean up loggers after each test."""
        # Remove all handlers from loggers to avoid interference
        for name in list(logging.Logger.manager.loggerDict.keys()):
            logger = logging.getLogger(name)
            for handler in logger.handlers[:]:
                logger.removeHandler(handler)

    def test_default_setup(self):
        """Test default logger setup."""
        logger = setup_logger("test_logger")
        
        assert isinstance(logger, EnhancedLogger)
        assert logger.name == "test_logger"
        assert logger.level == logging.DEBUG
        assert len(logger.handlers) == 1
        assert hasattr(logger, "success")

    def test_custom_name(self):
        """Test logger setup with custom name."""
        logger = setup_logger("custom_name")
        assert logger.name == "custom_name"

    def test_custom_level(self):
        """Test logger setup with custom level."""
        logger = setup_logger("test_logger", level=logging.INFO)
        assert logger.level == logging.INFO

    def test_single_handler(self):
        """Test logger setup with single handler."""
        custom_handler = logging.StreamHandler()
        logger = setup_logger("test_logger", handler=custom_handler)
        
        assert custom_handler in logger.handlers

    def test_multiple_handlers(self):
        """Test logger setup with multiple handlers."""
        handler1 = logging.StreamHandler()
        handler2 = logging.StreamHandler()
        logger = setup_logger("test_logger", handler=[handler1, handler2])
        
        assert handler1 in logger.handlers
        assert handler2 in logger.handlers

    def test_log_file(self):
        """Test logger setup with log file."""
        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            log_file = tmp_file.name
        
        try:
            logger = setup_logger("test_logger", log_file=log_file)
            
            # Should have both stream handler and file handler
            assert len(logger.handlers) == 2
            
            # Test that logging works
            logger.info("Test message")
            
            # Check file content
            with open(log_file, 'r') as f:
                content = f.read()
                assert "Test message" in content
                assert "INFO" in content
        finally:
            Path(log_file).unlink(missing_ok=True)

    def test_backward_compatibility(self):
        """Test backward compatibility for loggers without success method."""
        # Create a regular logger first
        regular_logger = logging.getLogger("backward_compat_test")
        
        # Now setup with our function
        logger = setup_logger("backward_compat_test")
        
        # Should have success method
        assert hasattr(logger, "success")
        assert callable(logger.success)

    def test_success_method_functionality(self):
        """Test that the success method works correctly."""
        logger = setup_logger("test_success")
        
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(formatter)
        logger.handlers.clear()  # Remove default handlers
        logger.addHandler(handler)
        
        logger.success("Test success message")
        
        output = stream.getvalue()
        assert "SUCCESS" in output
        assert "Test success message" in output
