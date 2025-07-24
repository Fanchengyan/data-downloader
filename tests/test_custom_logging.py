"""Tests for data_downloader logging module without dependencies."""

import io
import logging
import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

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


def test_success_level():
    """Test SUCCESS log level is properly defined."""
    assert SUCCESS == 25
    assert logging.INFO < SUCCESS < logging.WARNING
    assert logging.getLevelName(SUCCESS) == "SUCCESS"


def test_enhanced_logger():
    """Test EnhancedLogger class and success method."""
    logger = EnhancedLogger("test_enhanced")
    logger.setLevel(logging.DEBUG)
    
    # Capture log output
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    
    # Test success method
    logger.success("Success message")
    
    output = stream.getvalue()
    assert "SUCCESS" in output
    assert "Success message" in output


def test_formatters():
    """Test all formatters."""
    # Test standard formatter
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

    # Test color formatter
    formatted = color_formatter.format(record)
    assert "INFO" in formatted
    assert "test" in formatted
    assert "Test message" in formatted

    # Test file formatter
    formatted = file_formatter.format(record)
    assert "INFO" in formatted
    assert "test.py:10" in formatted
    assert "Test message" in formatted


def test_tqdm_handler():
    """Test tqdm logging handler."""
    # Create mock tqdm class
    mock_tqdm = Mock()
    handler = _TqdmLoggingHandler(tqdm_class=mock_tqdm)
    
    # Test with record
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Test message",
        args=(),
        exc_info=None,
    )
    
    handler.setFormatter(formatter)
    handler.emit(record)
    
    # Verify write was called
    mock_tqdm.write.assert_called_once()


def test_file_logging():
    """Test logging to file."""
    # Create temporary file
    with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
        log_file = tmp_file.name
    
    try:
        # Setup logger with file
        logger = setup_logger("test_file_logger", log_file=log_file)
        
        # Should have two handlers (stream + file)
        assert len(logger.handlers) == 2
        assert isinstance(logger.handlers[1], logging.FileHandler)
        
        # Test logging
        test_message = "Test log message"
        logger.info(test_message)
        
        # Check file content
        with open(log_file, "r") as f:
            content = f.read()
            assert test_message in content
    finally:
        # Clean up
        if os.path.exists(log_file):
            os.unlink(log_file)


def test_log_level_control():
    """Test log level control."""
    # Create logger with INFO level
    logger = setup_logger("test_level_logger", level=logging.INFO)
    assert logger.level == logging.INFO
    
    # Capture output
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(formatter)
    
    # Replace handlers
    logger.handlers = [handler]
    
    # DEBUG shouldn't be logged
    logger.debug("Debug message")
    assert stream.getvalue() == ""
    
    # INFO should be logged
    logger.info("Info message")
    assert "Info message" in stream.getvalue()


def test_setup_logger_returns_enhanced_logger():
    """Test that setup_logger returns EnhancedLogger."""
    logger = setup_logger("test_enhanced_logger")
    assert isinstance(logger, EnhancedLogger)
    assert hasattr(logger, "success")


def test_date_format():
    """Test date format in formatters."""
    # Check formatter datefmt attribute directly
    assert formatter.datefmt == "%Y-%m-%d %H:%M:%S"
    assert color_formatter.datefmt == "%Y-%m-%d %H:%M:%S" 
    assert file_formatter.datefmt == "%Y-%m-%d %H:%M:%S"
    
    # Verify format uses month instead of day in second position
    # This catches the bug where %Y-%d-%d was used instead of %Y-%m-%d
    format_string = formatter.datefmt
    assert format_string.split('-')[1] == "%m"  # Second part should be month
    assert format_string.split('-')[2].startswith("%d")  # Third part should start with day 