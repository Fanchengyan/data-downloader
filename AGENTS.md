# Developer Guide for data-downloader

This document provides essential information for AI agents and developers working on the `data-downloader` repository.

## Project Overview
`data-downloader` is a Python library designed to simplify the process of downloading scientific data from various sources (ASF, NASA, etc.). It supports multiple backends (requests, httpx, aiohttp) and provides both synchronous and asynchronous interfaces.

## Commands

### Build & Dependencies
This project uses `uv` for dependency management and `setuptools` as the build backend.
- **Install dependencies:** `uv sync`
- **Build package:** `uv build`
- **Clean build artifacts:** `rm -rf build/ dist/ *.egg-info`

### Linting & Formatting
We use `ruff` for both linting and formatting. It is configured with a wide range of rules including isort, flake8, and pylint.
- **Check linting:** `ruff check .`
- **Fix linting issues:** `ruff check --fix .`
- **Format code:** `ruff format .`
- **Type checking:** We recommend using `pyright` or `mypy` via `uv`.
  - `uv run pyright`
  - `uv run mypy .`

### Testing
We use `pytest` for testing.
- **Run all tests:** `pytest`
- **Run a single test file:** `pytest tests/test_logging.py`
- **Run a specific test:** `pytest tests/test_logging.py::test_setup_logger`
- **Run with coverage:** `pytest --cov=data_downloader`
- **Run slow tests:** `pytest -m slow`

## Code Style Guidelines

### Python Version & Types
- **Minimum Python:** 3.9, but aim for 3.10+ compatibility.
- **Type Hints:** ALWAYS use type hints for function signatures and public members.
- **Modern Syntax:** Use Python 3.10+ type hint features:
  - Use `str | None` instead of `Optional[str]`.
  - Use built-in generics: `list[str]` instead of `List[str]`, `dict[str, int]` instead of `Dict[str, int]`.
- **Compatibility:** Use `from __future__ import annotations` at the top of every module.
- **Typing Extensions:** Import `Self`, `Literal`, `TypedDict`, `Protocol`, and `TypeAlias` from `typing_extensions` to maintain backward compatibility.

### Imports
- **Ordering:** Standard library -> Third-party libraries -> Local modules.
- **Sorting:** Use `ruff` to sort imports (isort rules).
- **Style:** Prefer absolute imports for clarity. Avoid `from module import *`.

### Formatting
- **Line Length:** 88 characters.
- **Quotes:** Use double quotes `"` for strings unless the string contains double quotes.
- **Indent:** 4 spaces.
- **Docstring Formatting:** `ruff format` is configured to format code blocks inside docstrings.

### Naming Conventions
- **Modules/Packages:** `snake_case` (e.g., `data_downloader.utils`)
- **Classes:** `PascalCase` (e.g., `Netrc`, `ChunkedDownloadMetadata`)
- **Functions/Variables:** `snake_case` (e.g., `download_data`, `file_path`)
- **Constants:** `UPPER_SNAKE_CASE` (e.g., `RETRYABLE_STATUS_CODES`)
- **Private members:** Prefix with a single underscore `_private_function`.

### Documentation
- **Style:** NumPy-style docstrings.
- **Required Sections:** 
  - `Parameters`: List all arguments with types and descriptions.
  - `Returns`: Describe return value and type.
  - `Raises`: List exceptions that might be raised.
  - `Examples`: Provide usage examples in doctest format.
- **Completeness:** Every public function and class must have a docstring.

### Error Handling & Logging
- **Logging:** Use the project's internal logger created via `data_downloader.logging.setup_logger`.
- **Pre-error Logging:** ALWAYS log relevant information using `logger.error` or `logger.exception` BEFORE raising an exception or returning a failure status. This is crucial for debugging in agentic environments.
- **Warnings:** Use `logger.warning` instead of the standard `warnings` module.
- **Exception Context:** When catching exceptions, use `logger.exception("Contextual message")` to capture the traceback.
- **Safe Repr:** Use `data_downloader.utils.tools.safe_repr` when logging complex objects to avoid recursion or excessive output.

### Performance & Concurrency
- The library provides both sync and async versions of download functions.
- The `download_data` function acts as a unified entry point, dispatching to `requests` (sync), `httpx` (sync/async), or `aiohttp` (async) based on the `engine` parameter.
- Parallel chunked downloads are supported in the `httpx` and `aiohttp` engines.

## Project Structure & Patterns
- `data_downloader/downloader.py`: Main entry point for single and bulk downloads.
- `data_downloader/services/`: Directory for service-specific implementations (e.g., ASF, NASA Earthaccess).
- `data_downloader/utils/`: Utility functions for file handling, checksums, and metadata.
- **Async Pattern:** If you add an async function, ensure there is a corresponding sync wrapper or ensure it fits into the `download_data` dispatch logic.
- **Resume Support:** Most downloaders should support resuming from a breakpoint using `Range` headers.

## Best Practices for Agents
1. **Analyze First:** Use `grep` and `read` to understand how a service is implemented before adding a new one.
2. **Mimic Patterns:** Follow the established pattern of handling HTTP status codes and retries in `_handle_status` and `_get_retry_wait_time`.
3. **Test Proactively:** After making changes, run the relevant tests in `tests/`. If adding a feature, add a corresponding test.
4. **Safety:** Do not commit `.netrc` files or any files containing credentials. Use placeholders for testing.
5. **Verbosity:** Ensure your logs are informative enough for another agent (or yourself) to understand why a failure occurred.
