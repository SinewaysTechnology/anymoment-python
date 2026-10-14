# Changelog

## 2.0.0

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
