"""Pytest configuration and fixtures for data_downloader tests."""

import logging
import pytest


@pytest.fixture(autouse=True)
def reset_logging():
    """Reset logging configuration before each test."""
    # Store original logger class
    original_class = logging.getLoggerClass()
    
    yield
    
    # Clean up all loggers
    for name in list(logging.Logger.manager.loggerDict.keys()):
        if name.startswith('test_') or name.startswith('data_downloader'):
            logger = logging.getLogger(name)
            # Remove all handlers
            for handler in logger.handlers[:]:
                logger.removeHandler(handler)
            # Reset level
            logger.setLevel(logging.NOTSET)
    
    # Restore original logger class
    logging.setLoggerClass(original_class)


@pytest.fixture
def temp_log_file(tmp_path):
    """Create a temporary log file for testing."""
    log_file = tmp_path / "test.log"
    return str(log_file)
