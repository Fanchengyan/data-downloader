"""Logging utilities for data_downloader."""

from __future__ import annotations

import functools
import logging
from typing import Any

import colorlog
from tqdm import tqdm

# Add SUCCESS log level
SUCCESS = 25  # between INFO and WARNING
logging.addLevelName(SUCCESS, "SUCCESS")

__all__ = [
    "color_formatter",
    "formatter",
    "setup_logger",
    "stream_handler",
    "tqdm_handler",
    "SUCCESS",
    "file_formatter",
    "EnhancedLogger",
]

# formatters
formatter = logging.Formatter(
    "%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
color_formatter = colorlog.ColoredFormatter(
    "%(log_color)s%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    log_colors={
        "DEBUG": "cyan",
        "INFO": "white",
        "SUCCESS": "green",
        "WARNING": "yellow",
        "ERROR": "red",
        "CRITICAL": "red,bg_white",
    },
)

# File-specific formatter (without colors)
file_formatter = logging.Formatter(
    "%(asctime)s | %(levelname)s | %(name)s | %(filename)s:%(lineno)d | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# handlers
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(color_formatter)


class _TqdmLoggingHandler(logging.StreamHandler):
    """A logging handler that works with tqdm."""

    def __init__(self, tqdm_class: type[tqdm] = tqdm) -> None:
        """Initialize the tqdm logging handler."""
        super().__init__()
        self.tqdm_class = tqdm_class

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record."""
        try:
            msg = self.format(record)
            self.tqdm_class.write(msg, file=self.stream)
            self.flush()
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            self.handleError(record)


tqdm_handler = _TqdmLoggingHandler()
tqdm_handler.setLevel(logging.INFO)
tqdm_handler.setFormatter(color_formatter)


# Add success method to Logger class
def _success_method(self: logging.Logger, msg: str, *args: Any, **kwargs: Any) -> None:
    """Log 'msg % args' with severity 'SUCCESS'."""
    if self.isEnabledFor(SUCCESS):
        self._log(SUCCESS, msg, args, **kwargs)


# Enhanced Logger class with success method
class EnhancedLogger(logging.Logger):
    """Logger class with additional success method."""

    def success(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log 'msg % args' with severity 'SUCCESS'."""
        if self.isEnabledFor(SUCCESS):
            self._log(SUCCESS, msg, args, **kwargs)


# Register the enhanced logger class
logging.setLoggerClass(EnhancedLogger)


def setup_logger(
    name: str = "data_downloader",
    handler: logging.Handler | list[logging.Handler] = stream_handler,
    log_file: str | None = None,
    level: int = logging.DEBUG,
) -> EnhancedLogger:
    """Set up logging for the data_downloader module.

    Examples
    --------
    Default setup (terminal output only):

    >>> from data_downloader.logging import setup_logger
    >>> logger = setup_logger(__name__)

    Output to both file and terminal:

    >>> from data_downloader.logging import setup_logger
    >>> logger = setup_logger(__name__, log_file="download.log")

    Set log level:

    >>> from data_downloader.logging import setup_logger
    >>> import logging
    >>> logger = setup_logger(__name__, level=logging.INFO)

    Use custom SUCCESS log level:

    >>> from data_downloader.logging import setup_logger, SUCCESS
    >>> logger = setup_logger(__name__)
    >>> logger.log(SUCCESS, "Operation completed successfully!")
    >>> # Or using the convenience method:
    >>> logger.success("Operation completed successfully!")

    Working with tqdm:

    >>> from data_downloader.logging import setup_logger, tqdm_handler
    >>> logger = setup_logger(__name__, handler=tqdm_handler)

    Parameters
    ----------
    name : str, optional
        Name of the logger, by default "data_downloader"
    handler : logging.Handler, optional
        Logging handler to use, by default stream_handler
    log_file : str, optional
        Log file path. If provided, logs will be written to both the file and terminal, by default None
    level : int, optional
        Log level, by default logging.DEBUG

    Returns
    -------
    EnhancedLogger
        Configured logger instance.

    """
    logger: EnhancedLogger = logging.getLogger(name)  # type: ignore
    logger.setLevel(level)

    handlers_to_add = []

    # Handle the existing handler parameter
    if isinstance(handler, list):
        handlers_to_add.extend(handler)
    else:
        handlers_to_add.append(handler)

    # If log file is specified, add file handler
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(file_formatter)  # Use file formatter
        file_handler.setLevel(level)
        handlers_to_add.append(file_handler)

    # Add all handlers
    for h in handlers_to_add:
        logger.addHandler(h)

    # For backward compatibility with loggers created before setting logger class
    if not hasattr(logger, "success"):
        setattr(logger, "success", functools.partial(_success_method, logger))

    return logger
