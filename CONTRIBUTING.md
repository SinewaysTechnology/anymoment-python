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

`tests/test_contract_client.py` and `tests/test_cli_contract.py` encode the 2.0 client and CLI behavior. The HTTP client is `requests`, so those tests mock with `responses`. `tests/test_http_replay.py` replays the same JSON fixtures through `respx` for the httpx transport.

Behavior the 1.0 SDK does not implement yet is marked `pytest.mark.xfail(strict=True)` with a `2.0:` reason. Strict mode means an unexpected pass fails CI. When you implement that row, delete the marker in the same change. `pytest -ra` prints the remaining reasons. That list is the checklist.

Target CLI exit codes:

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 2 | Usage |
| 3 | Auth, needs login |
| 4 | Not found |
| 5 | Validation |
| 6 | Permission or read-only |
| 7 | Rate limited |
| 8 | Partial success (failures or warnings) |
| 9 | Upstream or server |
| 10 | Network |

`--json` prints one JSON object on stdout with `"v": 1`. Agenda includes `events` and `failures`. Errors with `--json` go to stderr as `{"error": {"code", "status", "user_message", "next_step", "retry_after"}}`.

### Lint, types, and the package build

```bash
ruff check .
mypy
python -m build
twine check dist/*
```

Ruff runs Pyflakes and syntax checks. Click command functions reuse names on purpose, so `F811` is ignored in `anymoment/cli/commands.py` only. Mypy ignores the Click redefinitions and the too-narrow query dicts in `anymoment/client.py`. Tighten those annotations in the 2.0 rewrite instead of widening this ignore.

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
