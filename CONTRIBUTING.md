# Contributing

## Testing

Install the package with the CLI extra and the dev tools:

```bash
python -m pip install -e ".[cli]" -r requirements-dev.txt
```

### Unit tests and the 2.0 checklist

```bash
pytest
```

That runs the existing unit tests plus the contract tests. It does not call the network. Live smoke is marked `live` and is excluded by default.

`tests/fixtures/` holds the API response shapes:

- `recorded_invalid_token_401.json` and `recorded_agenda_422.json` are bodies captured from the public API (unauthenticated, no writes).
- `agenda_batch.json`, `link_event.json`, and the event fields follow the public OpenAPI models (`AdvancedEventInstanceBatchResponse`, `EventInstanceFailure`, `AdvancedRecurrentEventOutput`, `CalendarEventLinkOutputWithWarnings`, `GoogleExportWarning`).
- Resend-verification status bodies, CalDAV `{code, message, next_step}` errors, and `sync_warnings` items are the shapes from the API source. The published schema leaves those bodies open (`additionalProperties` or an empty schema).

`tests/test_contract_client.py` and `tests/test_cli_contract.py` encode the 2.0 client and CLI behavior. The HTTP client is `requests`, so those tests mock with `responses`. `tests/test_http_replay.py` replays the same JSON fixtures with `respx` and `httpx` to check that the bodies stay valid. The SDK does not use httpx.

The 2.0 contract tests in `tests/test_contract_client.py` and `tests/test_cli_contract.py` are expected to pass. `pending()` is still `pytest.mark.xfail(strict=True)`. Use it only for a behavior that is intentionally not built yet, and delete the marker in the same change that implements it. An unexpected pass fails CI.

CLI exit codes:

| Code | Meaning |
| --- | --- |
| 0 | Success, including a payload that contains `failures` or `sync_warnings` |
| 2 | Usage, including HTTP 400 and 422 |
| 3 | Auth: HTTP 401, unverified email, or a missing token |
| 4 | Not found |
| 5 | Conflict |
| 6 | Rate limited |
| 7 | Remote or sync error: HTTP 403, 5xx, network, and CalDAV failures |

`--json` prints one compact JSON object on stdout with `"v": 1`. `--jsonl` prints one object per line. `--fields` keeps the named keys. Agenda includes `events` and `failures`. Errors with `--json` go to stderr as `{"error": {"code", "status", "user_message", "next_step", "retry_after"}}`.

### Lint, types, and the package build

```bash
ruff check .
mypy
python -m build
twine check dist/*
```

Ruff runs Pyflakes and syntax checks. Click command functions reuse names on purpose, so `F811` is ignored in `anymoment/cli/commands.py` only. Mypy ignores the Click redefinitions and the too-narrow query dicts in `anymoment/client.py`.

### Live smoke

Read-only. It calls `GET /auth/me` and `GET /agenda` for the current UTC day. It skips when either variable is missing.

```bash
export ANYMOMENT_BASE_URL="https://api.example.test"
export ANYMOMENT_TEST_TOKEN="..."
pytest -m live --override-ini="addopts="
```

Do not point this at a token that can do more than read, and do not add writes here.

### Continuous integration

`.github/workflows/ci.yml` runs on pull requests and on pushes to `main`:

- lint (`ruff`)
- types (`mypy`)
- unit tests on Python 3.10, 3.11, 3.12, and 3.13
- `python -m build` and `twine check`

Each job times out after 10 minutes.

`.github/workflows/smoke.yml` is `workflow_dispatch` plus a nightly run. It skips cleanly when `ANYMOMENT_BASE_URL` or `ANYMOMENT_TEST_TOKEN` is unset. It is not required for publish.

`.github/workflows/workflow.yml` still publishes on a `v*` tag. It calls the CI workflow first and publishes only after those jobs pass.

## Admin routes

Admin endpoints (`/auth/admin/*`, `/google/admin/*`, `/admin/*`) are out of scope for this public SDK and CLI. Do not add them. `tests/test_public_surface.py` fails if a package path or a fixture mentions them.
