# Test Safety Review & Improvements

## Summary
All tests have been reviewed and updated to ensure they:
1. **Never hit real APIs** - All API calls are mocked
2. **Never modify real user data** - All file operations use temporary directories
3. **Clean up after themselves** - Tests use pytest fixtures that auto-cleanup
4. **Are isolated** - Each test runs in its own temporary environment

## Issues Found & Fixed

### 1. Token File Safety ✅ FIXED
**Problem**: Some tests could write to the real token file (`~/.anymoment/tokens.json`)

**Root Cause**: 
- `test_login_success` in `test_client.py` called `client.login()` which internally calls `save_token()`
- The test didn't use `mock_token_file` fixture, so it wrote to the real token file
- This is why you found `"test-token-123"` in your real token file!

**Fix**:
- Added `@patch("anymoment.client.save_token")` to `test_login_success` and `test_login_failure`
- Added `mock_token_file` fixture to all CLI tests that interact with tokens
- Enhanced `mock_token_file` fixture to ensure files are cleaned up

### 2. Config File Safety ✅ FIXED
**Problem**: Some tests could read/write real config files

**Fix**:
- Added `mock_config_file` fixture to all tests that interact with config
- Enhanced fixture to ensure cleanup

### 3. API Call Safety ✅ VERIFIED
**Status**: Already safe - all API calls are mocked

**Verification**:
- All `test_client.py` tests use `@patch("anymoment.client.requests.Session")`
- All `test_cli.py` tests use `mock_client` fixture which mocks `get_client()`
- No tests make real HTTP requests

### 4. Test Isolation ✅ IMPROVED
**Improvements**:
- Enhanced fixtures with better documentation
- Added cleanup logic to ensure files don't persist
- All tests now explicitly use isolation fixtures

## Test Fixtures

### `mock_token_file`
- Creates temporary directory for token storage
- Patches `TOKEN_DIR` and `TOKEN_FILE` at module level
- Automatically cleaned up by pytest's `tmp_path`
- **Prevents**: Reading/writing real user tokens

### `mock_config_file`
- Creates temporary directory for config storage
- Patches `CONFIG_DIR` and `CONFIG_FILE` at module level
- Automatically cleaned up by pytest's `tmp_path`
- **Prevents**: Reading/writing real user config

### `mock_api_response`
- Creates mock HTTP responses
- Used with `@patch("anymoment.client.requests.Session")`
- **Prevents**: Real API calls

### `mock_client`
- Mocks `get_client()` function
- Returns a MagicMock client instance
- **Prevents**: Real API calls and token lookups

## Safety Checklist

- [x] All token operations use `mock_token_file`
- [x] All config operations use `mock_config_file`
- [x] All API calls are mocked
- [x] No real HTTP requests
- [x] No real file I/O (except temporary test files)
- [x] Tests clean up after themselves
- [x] Tests are isolated from each other
- [x] Tests don't require network access
- [x] Tests don't require authentication

## Running Tests Safely

Tests can now be run safely without any risk to:
- Real user tokens
- Real user configuration
- Real API endpoints
- Real customer data

```bash
# Run all tests safely
pytest tests/

# Run specific test file
pytest tests/test_client.py

# Run with coverage
pytest tests/ --cov=anymoment
```

## Recommendations

1. **Always use fixtures** - Never write tests that directly access real files or APIs
2. **Run tests in CI/CD** - Automated testing ensures safety
3. **Review test changes** - When adding new tests, ensure they use proper fixtures
4. **Monitor test output** - Watch for any warnings about real API calls or file access

## What to Do If You Find Real Data in Tests

If you ever find real tokens/config in your test files:

1. **Delete the test data**:
   ```bash
   # Check for test tokens
   anymoment tokens list
   
   # Delete if found
   anymoment auth logout
   ```

2. **Verify tests are using fixtures**:
   ```bash
   # Run tests and check for file access
   pytest tests/ -v
   ```

3. **Report the issue** - If tests are writing to real files, it's a bug that needs fixing
