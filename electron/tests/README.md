# Unit Tests for Doc to Markdown Converter v2.0

This directory contains unit tests for the Electron v2.0 Flask backend and conversion logic.

## Test Files

- `test_web_app.py` - Tests for Flask API endpoints (config, converted files, supported formats, token count)
- `test_token_stats.py` - Tests for token statistics calculation
- `test_config.py` - Tests for configuration file management
- `test_google_drive.py` - Tests for Google Drive URL extraction and download

## Running Tests

### Install test dependencies:
```bash
cd tests
pip install -r requirements.txt
```

### Run all tests:
```bash
cd ..
pytest
```

### Run specific test file:
```bash
pytest tests/test_web_app.py
```

### Run with coverage:
```bash
pytest --cov=python --cov-report=html
```

## Test Coverage

The tests cover:
- Flask API endpoints
- Configuration persistence
- Token counting algorithms
- File size calculations
- Google Drive URL parsing
- Error handling

## Notes

- Some tests may fail in certain environments due to missing dependencies (e.g., tiktoken)
- Google Drive tests are mocked since actual Google Drive access requires browser automation
- Tests use temporary files and directories that are cleaned up automatically
