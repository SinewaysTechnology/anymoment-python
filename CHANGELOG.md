# Changelog

## [2.1.0] - 2026-10-14

### API keys

- `Client(api_key=...)` and `ANYMOMENT_API_KEY` send `Authorization: Bearer`. When a key is set, it is used instead of a saved login or `ANYMOMENT_TOKEN`.
- The CLI accepts `--api-key`. `am auth status` shows the method in use (API key, environment token, or saved login) and the key prefix. It does not print the secret and it does not call the API.
- Keys are created in AnyMoment settings. This release does not create, rotate, or revoke keys.
- Typed errors: `InvalidApiKeyError` (`invalid_api_key`), `ApiKeyRevokedError` (`api_key_revoked`), `ApiKeyExpiredError` (`api_key_expired`), `ApiKeyNotPermittedError` (`api_key_not_permitted`), and `CalendarNotAllowedError` (`calendar_not_allowed`). Each one includes a next step. HTTP 429 still raises `RateLimitError` with `retry_after` taken from `retry_after_seconds`.
- A calendar-limited key cannot call `GET /events`. Pass a calendar id. `list_events` then calls `GET /calendars/{calendar_id}/events`.

### Webhook subscriptions

- Create, read, update, delete, list deliveries, and replay a delivery at `/calendars/{calendar_id}/subscriptions`.
- `verify_webhook` checks `X-AnyMoment-Signature`. The value is hex HMAC-SHA256 over `{timestamp}.{raw body}`. `X-AnyMoment-Timestamp` is the timestamp. `X-AnyMoment-Delivery` identifies the attempt.

## [2.0.1] - 2026-10-14

### Fixed

- Top-level `create` and `update` honor `--dry-run` and `--yes`. `--dry-run` reuses the local replay check and does not call the API. On a terminal, those commands ask first unless `--yes` is set.
- `update` with no fields exits 2.
- `anymoment completion` registers both `anymoment` and `am` for bash, zsh, and fish.
- The package build produces a wheel and an sdist. The publish workflow uploads both to PyPI and attaches both to the GitHub release.

## [2.0.0] - 2026-10-14

Python 3.10 or newer. 3.8 and 3.9 are no longer supported.

### Migration

- `get_agenda` returns an `AgendaResult` with `.events` and `.failures`. It is not a list. A legacy list body is exposed as `.events` with an empty `.failures` list. Read `result.events`.
- `delete_event` and `unlink_event_from_calendar` return the response body. They no longer return `None`. Read `.message` and `.sync_warnings`.
- `update_event`, `update_event_from_text`, `toggle_event`, and `batch_remove_events_from_calendar` return an object with `.sync_warnings`.
- `link_event_to_calendar` returns an object with `.link` and `.google_export_warnings`.
- Nested documents such as `external_origin` stay dicts.
- Exceptions accept `status_code`, `code`, `user_message`, `next_step`, `retry_after`, `details`, and `raw`. `message` is the text you should show.
- New types: `EmailNotVerifiedError` (plain-text unverified sign-in), `PermissionDeniedError` (403), `ConflictError` (409), `UnprocessableError` (422), `RateLimitError` (429, `.retry_after`). HTTP 502 and other 5xx responses raise `ServerError`.
- The client treats every 2xx status as success, including 202.
- A 401 refreshes the session token only for a real AnyMoment session. Login, token extend, and CalDAV `auth_failed` do not refresh.
- CLI exit codes are 0 ok, 2 usage, 3 auth, 4 not found, 5 conflict, 6 rate limited, 7 remote or sync error. A successful call that includes `failures` or `sync_warnings` still exits 0. Those fields are in the JSON payload.
- `--json` and `--jsonl` are accepted on the subcommand. Errors with `--json` are one JSON object on stderr: `{"error": {"code", "status", "user_message", "next_step", "retry_after"}}`.

### SDK

- Resend verification, signup, change password, reset password, permanent tokens, and feedback.
- Structured event create, preview, ICS import, and batch get.
- Guests, webhooks, calendar instances, ICS export, and changes polling.
- `client.google` for accounts, sync health, quarantine, resolve, and sync status.
- `client.caldav` is experimental. Remote credential failures do not refresh the AnyMoment token.

### CLI

- Global `--json`, `--jsonl`, `--fields`, `--dry-run`, `--idempotency-key`, `--yes`, and `--profile`.
- `anymoment agenda "tomorrow 3pm"` and the shortcuts `today`, `week`, and `next`.
- `anymoment schema` and `anymoment help --json`.
- `events batch` reads JSONL from stdin.
- Login does not prompt unless stdin is a terminal. `ANYMOMENT_TOKEN` and `--email` / `--password` cover non-interactive use.
- Aliases: `am`, `a` (agenda), `ls` (calendars list), `rm` (events delete).
- Color and tables on a terminal. `NO_COLOR` or a pipe turns them off. The calendar picker runs only on a terminal.
- `anymoment completion bash|zsh|fish`.

### Not in this release

- Admin routes are not wrapped.
- There is no async client.
- `--idempotency-key` is a local cache. The API does not accept an idempotency header.
- `SubscriptionRequiredError` is not defined. The public contract used here does not pin a status code for it.
- The CalDAV push receiver (`POST /caldav/push/{account_id}`) is a server-to-server callback and is not wrapped.

## [1.0.0] - 2026-02-25

CLI updates for the API at that time, and a stable 1.0 release. Requires Python 3.8 or newer.

## [0.1.0] - 2026-02-02

First published SDK and CLI, with calendar and event commands, batch linking and sharing, and the PyPI publish workflow.

[2.1.0]: https://github.com/SinewaysTechnology/anymoment-python/compare/v2.0.1...v2.1.0
[2.0.1]: https://github.com/SinewaysTechnology/anymoment-python/compare/v2.0.0...v2.0.1
[2.0.0]: https://github.com/SinewaysTechnology/anymoment-python/compare/v1.0.0...v2.0.0
[1.0.0]: https://github.com/SinewaysTechnology/anymoment-python/compare/v0.1.0...v1.0.0
[0.1.0]: https://github.com/SinewaysTechnology/anymoment-python/releases/tag/v0.1.0
