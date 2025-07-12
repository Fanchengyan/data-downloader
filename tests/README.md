# Tests for data_downloader

This directory contains pytest tests for the data_downloader package.

## Setup

Install test dependencies:

```bash
pip install pytest pytest-cov pytest-mock
```

Or install from the requirements file:

```bash
pip install -r tests/requirements.txt
```

## Running Tests

### Run all tests
```bash
pytest tests/
```

### Run specific test file
```bash
pytest tests/test_logging.py
```

### Run with verbose output
```bash
pytest tests/test_logging.py -v
```

### Run with coverage report
```bash
pytest tests/test_logging.py --cov=data_downloader.logging --cov-report=term-missing
```

### Run with HTML coverage report
```bash
pytest tests/test_logging.py --cov=data_downloader.logging --cov-report=html
```

## Test Structure

- `test_logging.py` - Tests for the logging module
- `conftest.py` - Pytest configuration and shared fixtures
- `requirements.txt` - Test dependencies

## Test Coverage

The current test suite for `data_downloader.logging` achieves 95% code coverage, testing:

- Custom SUCCESS log level
- All formatters (basic, color, file)
- TqdmLoggingHandler functionality
- EnhancedLogger with success method
- setup_logger function with various configurations
- Error handling and edge cases

## Adding New Tests

When adding new tests:

1. Follow the existing naming convention (`test_*.py`)
2. Use descriptive test method names
3. Group related tests in classes
4. Add docstrings to test methods
5. Use appropriate fixtures from `conftest.py`
6. Ensure good test coverage for new functionality
