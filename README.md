# AnyMoment Python SDK & CLI

Python SDK and command-line interface for the [AnyMoment API](https://api.anymoment.sineways.tech) - Create and manage recurring calendar events with natural language.

**📖 [Full documentation (Python SDK & CLI)](https://anymoment.sineways.tech/anymoment-python/docs)**: installation, quick start, all CLI commands, and Library API reference.

## Features

- 🎯 **Natural Language Event Creation** - Create complex recurring events from simple text
- 📅 **Full Calendar Management** - Create, update, delete, and share calendars
- 🔐 **Secure Token Management** - Encrypted token storage with automatic refresh
- 🚀 **Both Library & CLI** - Use programmatically or from the command line
- ⚡ **Fast & Reliable** - Built on requests with proper error handling

## Installation

### Library Only

```bash
pip install "anymoment"
```

### With CLI

```bash
pip install "anymoment[cli]"
```

## Quick Start

```bash
pip install "anymoment[cli]"
am auth login
am today
am today --json --fields events,failures
```

### CLI Usage

```bash
# Login
anymoment auth login

# Create a calendar
anymoment calendars create "Work Calendar" --timezone "America/New_York"

# Create an event from natural language
anymoment events create "Weekly team meeting every Monday at 10 AM" \
    --calendar <calendar-id>

# List events
anymoment events list --calendar <calendar-id>

# Get event instances for a date range
anymoment events instances <event-id> --from "2026-01-01" --to "2026-03-31"
```

### Library Usage

```python
from anymoment import Client

# Initialize client
client = Client(api_url="https://api.anymoment.sineways.tech")

# Login
client.login(email="user@example.com", password="secret")

# Create calendar
calendar = client.create_calendar(
    name="Work Calendar",
    timezone="America/New_York"
)

# Create event from natural language
event = client.create_event_from_text(
    recurrence_text="Weekly team meeting every Monday at 10 AM",
    calendar_id=calendar["id"]
)

# Get event instances for a date range
instances = client.get_event_instances(
    event_id=event["id"],
    from_date="2026-01-01",
    to_date="2026-03-31"
)
```

## Version 2.1

2.1.0 is the current release. It requires Python 3.10 or newer. Migration notes are in [CHANGELOG.md](CHANGELOG.md).

Create an API key in AnyMoment settings. The SDK and CLI do not create, rotate, or revoke keys. A key looks like `am_live_`, eight hex characters, an underscore, and a secret. Send it as `Authorization: Bearer`, pass `api_key=` to `Client`, or set `ANYMOMENT_API_KEY`. `--api-key` does the same thing in the CLI. When a key is set, it is used instead of a saved login or `ANYMOMENT_TOKEN`.

```python
from anymoment import Client

client = Client(api_key="am_live_0123abcd_secret")
calendars = client.list_calendars()
```

```bash
export ANYMOMENT_API_KEY="am_live_0123abcd_secret"
am auth status
am calendars list --json
am events list --calendar <calendar-id> --json
```

`am auth status` shows whether the command is using an API key, `ANYMOMENT_TOKEN`, or a saved login. It prints the key prefix (`am_live_` plus the eight hex characters) and never prints the secret.

Keys can allow `events:read`, `events:write`, `calendars:read`, and `webhooks:manage`. A key can also be limited to specific calendars. A calendar-limited key cannot call `GET /events`. Pass a calendar id and the client calls `GET /calendars/{calendar_id}/events`. Each item is the event plus its link.

| Status | Code | What to do |
| --- | --- | --- |
| 401 | `invalid_api_key` | Check the full key from AnyMoment settings. |
| 401 | `api_key_revoked` | The key was revoked. Create a new one in settings. |
| 401 | `api_key_expired` | The key has expired. Create a new one in settings. |
| 403 | `api_key_not_permitted` | API keys cannot call sign-in, account, or key-management routes. Use `am auth login` for those. |
| 403 | `calendar_not_allowed` | The key cannot access that calendar. |
| 429 | | Wait `retry_after` seconds, then retry. |

Webhook subscriptions live on a calendar: create, read, update, delete, list deliveries, and replay one delivery. A generated signing secret is returned once, on create. Store it. Later responses do not include it.

AnyMoment signs each delivery with hex HMAC-SHA256 over `{timestamp}.{raw body}`. The headers are `X-AnyMoment-Signature`, `X-AnyMoment-Timestamp`, and `X-AnyMoment-Delivery`. Pass the raw body bytes to `verify_webhook`. Re-encoding the JSON will not match.

```python
from anymoment import verify_webhook

def endpoint(raw_body: bytes, headers: dict) -> None:
    if not verify_webhook(raw_body, headers, secret):
        raise ValueError("signature did not match")
```

```bash
am calendars subscriptions create <calendar-id> \
  --url https://example.com/hooks/anymoment \
  --event-type event.updated
am calendars subscriptions deliveries <calendar-id> <subscription-id> --json
am calendars subscriptions replay <calendar-id> <subscription-id> <delivery-id>
```

## Version 2.0

2.0 requires Python 3.10 or newer. The migration notes, including 2.0.1, 1.0.0, and 0.1.0, are in [CHANGELOG.md](CHANGELOG.md).

`get_agenda` returns an object with `.events` and `.failures`. It is not a list. Delete, unlink, update, toggle, and link return their warning fields (`.message`, `.sync_warnings`, or `.google_export_warnings`) instead of dropping the response body.

Errors expose `.message`, `.next_step`, and `.retry_after`, plus `code` and `user_message`. New types cover unverified email, permission denied (403), conflict (409), unprocessable input (422), and rate limits (429, `.retry_after`). A 401 refreshes the session token only for a real AnyMoment session. Login and CalDAV `auth_failed` do not refresh.

The CLI accepts `--json`, `--jsonl`, `--fields`, `--dry-run`, `--yes`, `--idempotency-key`, and `--profile` on the subcommand. Top-level `create` and `update` write events. `--dry-run` prints the action and does not call the API. On a terminal those writes ask first unless you pass `--yes`. `update` with no fields exits 2.

`anymoment` and `am` are the same command. `a` is agenda, `ls` lists calendars, and `rm` deletes an event. `anymoment completion bash` (also `zsh` and `fish`) registers both `anymoment` and `am`.

Exit codes: 0 ok, 2 usage, 3 auth, 4 not found, 5 conflict, 6 rate limited, 7 remote or sync error. A successful payload that includes `failures` or `sync_warnings` still exits 0.

```bash
anymoment agenda "next week" --json
anymoment create "Lunch tomorrow at noon" --dry-run
anymoment update <event-id> --title "Lunch" --yes
anymoment auth login --email you@example.com --password "$ANYMOMENT_PASSWORD"
# or skip the prompt with ANYMOMENT_TOKEN
anymoment schema
anymoment completion bash
```

## Configuration

### Environment Variables

- `ANYMOMENT_BASE_URL` - Default API base URL (default: `https://api.anymoment.sineways.tech`)
- `ANYMOMENT_DEFAULT_CALENDAR` - Default calendar ID
- `ANYMOMENT_DEFAULT_TIMEZONE` - Default timezone
- `ANYMOMENT_TOKEN` - Session token for non-interactive use. No login prompt.
- `ANYMOMENT_API_KEY` - API key. Used instead of a saved login or `ANYMOMENT_TOKEN` when set.
- `ANYMOMENT_PROFILE` - Config profile name (`--profile` sets the same value)
- `NO_COLOR` - Disable terminal color

### Config File

Configuration is stored in `~/.anymoment/config.json`. You can manage it via CLI:

```bash
# Set default API URL
anymoment config set-url https://api.anymoment.sineways.tech

# Set default timezone
anymoment config set-timezone America/New_York

# Set default calendar
anymoment config set-calendar <calendar-id>

# Show current config
anymoment config show
```

## CLI Commands

### Create and update

```bash
# Top-level create. --dry-run makes no API call. On a terminal, confirm unless --yes.
anymoment create "Lunch tomorrow at noon" [--calendar ID] [--timezone TZ] [--context TEXT] [--dry-run] [--yes]

# Top-level update. Exits 2 when none of --when, --title, or --description is set.
anymoment update <event-id> [--when TEXT] [--title TEXT] [--description TEXT] [--dry-run] [--yes]
```

### Authentication

```bash
# Login interactively
anymoment auth login [--host URL]

# Logout (clear token)
anymoment auth logout [--host URL]

# Non-interactive login
anymoment auth login --email you@example.com --password "$ANYMOMENT_PASSWORD"
# or export ANYMOMENT_TOKEN

# Send the verification email again
anymoment auth resend-verification --json

# Show whether this command is using an API key, ANYMOMENT_TOKEN, or a saved login.
# Prints the key prefix only. Does not call the API.
anymoment auth status

# Or pass the key once. Same precedence as ANYMOMENT_API_KEY.
anymoment calendars list --api-key "$ANYMOMENT_API_KEY"

# List all tokens
anymoment tokens list

# Clear all tokens
anymoment tokens clear
```

### Calendars

```bash
# List calendars
anymoment calendars list [--active/--inactive] [--limit N] [--offset N]

# Create calendar
anymoment calendars create <name> [--description TEXT] [--timezone TZ] [--color COLOR]

# Get calendar details
anymoment calendars get <id>

# Update calendar
anymoment calendars update <id> [--name NAME] [--description TEXT] [--timezone TZ] [--color COLOR] [--active/--inactive]

# Delete calendar
anymoment calendars delete <id>

# Share calendar with another user (set role: owner, editor, viewer)
anymoment calendars share <id> <user-id> [--role ROLE]

# Update a shared user's role
anymoment calendars update-share <id> <user-id> --role ROLE

# Remove share (user loses access unless linked via Google)
anymoment calendars unshare <id> <user-id>

# Add / remove events to or from a calendar (link or unlink)
anymoment calendars add-event <calendar-id> <event-id> [--display-order N] [--color COLOR]
anymoment calendars remove-event <calendar-id> <event-id>

# Batch add or remove events to or from a calendar
anymoment calendars batch-add-events <calendar-id> <event-id> [<event-id> ...] [--display-order N] [--color COLOR]
anymoment calendars batch-remove-events <calendar-id> <event-id> [<event-id> ...]

# Get webhook URL
anymoment calendars webhook-url <id>
```

### Calendar subscriptions

Outgoing webhook subscriptions for one calendar. Create the signing secret in this response and store it. `am auth status` is separate: that command never prints an API key secret.

```bash
anymoment calendars subscriptions list <calendar-id>
anymoment calendars subscriptions create <calendar-id> --url https://example.com/hooks/anymoment --event-type event.updated [--secret SECRET] [--offset-seconds N]
anymoment calendars subscriptions get <calendar-id> <subscription-id>
anymoment calendars subscriptions update <calendar-id> <subscription-id> [--url URL] [--event-type TYPE] [--secret SECRET] [--offset-seconds N] [--active/--inactive]
anymoment calendars subscriptions delete <calendar-id> <subscription-id>
anymoment calendars subscriptions deliveries <calendar-id> <subscription-id> [--limit N]
anymoment calendars subscriptions replay <calendar-id> <subscription-id> <delivery-id>
```

### Events

```bash
# Create event from natural language
anymoment events create "TEXT" [--name NAME] [--description TEXT] [--timezone TZ] [--calendar ID] [--model MODEL]

# List events
anymoment events list [--calendar ID] [--active/--inactive] [--limit N] [--offset N] [--minimal]

Note: To filter events by date range, use `events instances` instead.

# Get event details
anymoment events get <id>

# Update event
anymoment events update <id> [--name NAME] [--description TEXT]

# Delete event
anymoment events delete <id>

# Toggle event active status
anymoment events toggle <id>

# Get event instances
anymoment events instances <id> [--from DATE] [--to DATE] [--optimized]

# Get next instance
anymoment events next <id>

# Export instances
anymoment events export <id> [--format ics|csv] [--from DATE] [--to DATE] [--out FILE]
```

### Agenda & Search

```bash
# One call. Prints the resolved UTC window, then the events.
anymoment agenda "tomorrow 3pm"
anymoment agenda "next fri" --json
anymoment today
anymoment week
anymoment next

# List events and instances in a time window (agenda)
anymoment agenda list [--start ISO] [--end ISO] [--calendar ID] [--no-cache] [--webhooks]

# Fuzzy search events by name (optional time window and filters)
anymoment agenda search <query> [--start ISO] [--end ISO] [--calendar ID] [--active/--inactive] [--limit N] [--offset N] [--no-instances]
```

### Users

```bash
# Show current user info
anymoment users me
```

### Common Options

- `--host, -h URL` - Override API host URL (env: `ANYMOMENT_BASE_URL`)
- `--raw` - Output full JSON response
- `--pipe` - Output only IDs (for piping/chaining)
- `--json` - One compact JSON object on stdout (`"v": 1`)
- `--jsonl` - One compact JSON object per line
- `--fields a,b` - Keep these JSON fields, plus `v`. Example: `am today --json --fields events,failures`
- `--dry-run` - Show a mutation without sending it. Top-level `create` and `update` make no API call. `events create` uses the preview endpoint.
- `--yes` - Skip the confirmation prompt. Top-level `create` and `update`, and `events delete`, ask on a terminal unless this is set.
- `--idempotency-key KEY` - Local replay cache. The API has no idempotency header.
- `--profile NAME` - Use `~/.anymoment/config.NAME.json`
- `--api-key KEY` - API key for this command. Overrides a saved login and `ANYMOMENT_TOKEN`. Env: `ANYMOMENT_API_KEY`.
- `--timezone, -z TZ` - Override timezone for this command
- `--calendar, -c ID` - Specify calendar ID or name (or use default from config)

Machine-readable errors go to stderr when `--json` or `--jsonl` is set. `anymoment schema` lists commands and exit codes. `anymoment completion bash|zsh|fish` prints a snippet that registers `anymoment` and `am`.

Exit codes: 0 ok, 2 usage, 3 auth, 4 not found, 5 conflict, 6 rate limited, 7 remote or sync error.

## Library API Reference

### Client Class

```python
from anymoment import Client

client = Client(
    api_url="https://api.anymoment.sineways.tech",
    token="optional-token",
    api_key="optional-api-key",
)
```

`api_key` and `ANYMOMENT_API_KEY` win over `token` and the saved login. API keys are not written to the token file and are not refreshed.

#### Authentication

- `client.login(email, password)` - Authenticate and get token
- `client.refresh_token()` - Refresh current token
- `client.get_user_info()` - Get current user information
- `client.resend_verification()` - Send the verification email again
- `client.signup(email, password, ...)` - Create an account
- `client.google` - Google accounts, sync health, quarantine, and sync status
- `client.caldav` - Experimental CalDAV. Remote auth failures do not refresh the session token.

#### Calendars

- `client.list_calendars(is_active=None, limit=None, offset=None)` - List calendars
- `client.get_calendar(calendar_id)` - Get calendar by ID
- `client.create_calendar(name, description=None, timezone="UTC", color=None)` - Create calendar
- `client.update_calendar(calendar_id, name=None, description=None, timezone=None, color=None, is_active=None)` - Update calendar
- `client.delete_calendar(calendar_id)` - Delete calendar
- `client.share_calendar(calendar_id, user_id, role="viewer")` - Share calendar with a user (set permissions)
- `client.update_calendar_share_role(calendar_id, user_id, role)` - Update a shared user's role (owner, editor, viewer)
- `client.unshare_calendar(calendar_id, user_id)` - Remove an AnyMoment share for a calendar
- `client.get_calendar_webhook_url(calendar_id)` - Get webhook URL

#### Events

- `client.list_events(calendar_id=None, is_active=None, limit=None, offset=None, minimal=False)` - List events. With an API key and a calendar id, calls `GET /calendars/{id}/events`.
- `client.list_calendar_events(calendar_id, is_active=None, limit=None, offset=None)` - Events on one calendar, each item `{event, link}`
- `client.get_event(event_id)` - Get event by ID
- `client.create_event_from_text(recurrence_text, name=None, description=None, timezone="UTC", calendar_id=None, model="high")` - Create event from natural language
- `client.update_event(event_id, name=None, description=None)` - Update event
- `client.delete_event(event_id)` - Delete event
- `client.toggle_event(event_id)` - Toggle event active status
- `client.get_event_instances(event_id, from_date=None, to_date=None, optimized=False)` - Get event instances
- `client.get_next_event_instance(event_id)` - Get next instance

#### Agenda & Search

- `client.get_agenda(start, end, calendar_ids=None, use_cache=True, include_webhooks=False)` - Get events and their instances within a time window (agenda)
- `client.search_events(q, start=None, end=None, calendar_ids=None, is_active=None, limit=50, offset=0, include_instances=True)` - Fuzzy search events by name (optional time window and filters)

#### Calendar-Event Links (add / remove events to or from calendars)

- `client.link_event_to_calendar(calendar_id, event_id, display_order=None, color_override=None)` - Add one event to a calendar
- `client.unlink_event_from_calendar(calendar_id, event_id)` - Remove one event from a calendar (unlink only; event is not deleted)
- `client.batch_add_events_to_calendar(calendar_id, event_ids, display_order=None, color_override=None)` - Add multiple events to a calendar in one request
- `client.batch_remove_events_from_calendar(calendar_id, event_ids)` - Remove multiple events from a calendar (unlink only)

#### Accounts, passwords, and tokens

- `client.change_password(new_password, old_password=None)` - Change the signed-in user's password
- `client.reset_password(user, new_password)` - Reset a password. `user` is an email or a user object
- `client.create_permanent_token(email, ...)` - Create a permanent token
- `client.list_permanent_tokens()` - List permanent tokens
- `client.delete_permanent_token(token)` - Revoke one permanent token
- `client.create_feedback(message, rating=None, title=None)` - Send product feedback

#### Structured events, preview, import, guests, and webhooks

- `client.create_event(name, components, description=None)` - Create an event from recurrence components
- `client.get_events_batch(event_ids, ...)` - Fetch many events by id
- `client.preview_event_from_text(name, recurrence_text, start, end, ...)` - Preview natural language without saving
- `client.create_event_from_ics(ics_content, ...)` - Create an event from ICS text
- `client.list_event_feedback(...)` / `client.create_event_feedback(value, event_data, message=None)` - Event feedback
- `client.list_guests(event_id)` / `client.add_guest(event_id, **fields)` / `client.update_guest(...)` / `client.delete_guest(...)` - Event guests
- `client.list_webhooks(event_id)` / `client.create_webhook(...)` / `client.get_webhook(...)` / `client.update_webhook(...)` / `client.delete_webhook(...)` / `client.list_webhook_runs(...)` - Event webhooks
- `client.list_subscriptions(calendar_id)` / `client.create_subscription(calendar_id, url, event_types, secret=None, occurrence_offset_seconds=None)` / `client.get_subscription(...)` / `client.update_subscription(...)` / `client.delete_subscription(...)` - Calendar webhook subscriptions
- `client.list_subscription_deliveries(calendar_id, subscription_id, limit=None)` / `client.replay_subscription_delivery(...)` - Delivery log and replay
- `verify_webhook(payload, headers, secret)` / `verify_signature(...)` / `webhook_signature(...)` - Check `X-AnyMoment-Signature` (HMAC-SHA256 over `{timestamp}.{raw body}`)

#### Instances, export, and changes

- `client.get_calendar_instances(calendar_id, start, end, ...)` - Instances on one calendar
- `client.get_loose_event_instances(start, end, ...)` - Instances that are not on a calendar
- `client.export_calendar(calendar_id, start, end)` - Download a window as ICS text
- `client.get_changes(since)` - Poll changes across calendars
- `client.get_calendar_changes(calendar_id, since)` - Poll changes for one calendar

#### Google and CalDAV

- `client.google.accounts()` / `delete_account(account_id)` - Connected Google accounts
- `client.google.sync_health(export_id=None)` / `quarantine(...)` / `resolve_quarantine(quarantine_id, resolution)` / `sync_status(job_id)` - Google sync
- `client.caldav` - Experimental. `capabilities`, `discover`, `test_connection`, account create/list/get/update, `refresh_calendars`, login flow, links, destinations, `refresh`, `sync_health`, quarantine, `enable_push`, `fetch_certificate`, disconnect, and reconnect. Remote credential failures do not refresh the AnyMoment token.

## Examples

### Natural Language Event Creation

```python
# Simple weekly event
event = client.create_event_from_text(recurrence_text="Every Monday at 10 AM")

# Complex recurring pattern
event = client.create_event_from_text(
    recurrence_text="Weekdays from 9 to 5, except the 13th of every month",
    name="Work Hours",
    timezone="America/New_York"
)

# Multiple time windows
event = client.create_event_from_text(
    recurrence_text="Every Monday and Wednesday, from 9:00 to 12:00 and 13:00 to 17:00"
)
```

### Working with Calendars

```python
# Create and configure calendar
calendar = client.create_calendar(
    name="Personal",
    description="Personal events",
    timezone="America/New_York",
    color="#FF5733"
)

# Share with another user
client.share_calendar(
    calendar_id=calendar["id"],
    user_id="other-user-id",
    role="viewer"
)

# Get webhook URL for automation
webhook = client.get_calendar_webhook_url(calendar["id"])
print(f"Webhook URL: {webhook['webhook_url']}")
```

### Getting Event Instances

```python
# Get instances for a date range
instances = client.get_event_instances(
    event_id=event["id"],
    from_date="2026-01-01",
    to_date="2026-03-31"
)

# Get next instance
next_instance = client.get_next_event_instance(event["id"])
print(f"Next occurrence: {next_instance}")
```

### Agenda & Search

```python
# Get events and instances in a time window (agenda)
result = client.get_agenda(
    start="2026-01-01T00:00:00Z",
    end="2026-01-31T23:59:59Z",
    calendar_ids=[calendar["id"]],
    use_cache=True,
)
for item in result.events:
    print(item["event"]["name"], item["instances"])
for failure in result.failures:
    print(failure.get("user_message"), failure.get("next_step"))

# Fuzzy search events by name
results = client.search_events(
    q="team meeting",
    start="2026-01-01T00:00:00Z",
    end="2026-03-31T23:59:59Z",
    limit=20,
    include_instances=True,
)
for item in results:
    print(item["event"]["name"], item.get("score"), item.get("instances"))
```

## Error Handling

The SDK raises specific exceptions for different error types:

```python
from anymoment import (
    ApiKeyExpiredError,
    ApiKeyNotPermittedError,
    ApiKeyRevokedError,
    AuthenticationError,
    CalendarNotAllowedError,
    ConflictError,
    EmailNotVerifiedError,
    InvalidApiKeyError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    ServerError,
    UnprocessableError,
    ValidationError,
)

try:
    calendar = client.get_calendar("invalid-id")
except NotFoundError as exc:
    print(exc.message, exc.next_step)
except EmailNotVerifiedError as exc:
    print(exc.message, exc.next_step)
except RateLimitError as exc:
    print(exc.message, exc.retry_after)
except InvalidApiKeyError as exc:
    print(exc.message, exc.next_step)
except (ApiKeyRevokedError, ApiKeyExpiredError, ApiKeyNotPermittedError, CalendarNotAllowedError) as exc:
    print(exc.code, exc.message, exc.next_step)
except (AuthenticationError, PermissionDeniedError, ConflictError, ValidationError, UnprocessableError, ServerError) as exc:
    print(exc.message, exc.next_step)
```

Every SDK error has `.message` (the text to show), `.next_step`, and `.retry_after`. `.retry_after` is set on HTTP 429 and is `None` otherwise. `EmailNotVerifiedError` is the plain-text unverified sign-in. `PermissionDeniedError` is 403, `ConflictError` is 409, `UnprocessableError` is 422, and `RateLimitError` is 429.

## Token Management

Tokens are automatically stored encrypted in `~/.anymoment/tokens.json` using machine-specific encryption. The SDK handles:

- Automatic token refresh on expiration
- Multi-host token storage
- Secure encryption using Fernet

## Development

Tests, lint, types, and the package build are documented in [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Support

- **Python SDK & CLI docs**: [https://anymoment.sineways.tech/anymoment-python/docs](https://anymoment.sineways.tech/anymoment-python/docs)
- **API Base URL**: https://api.anymoment.sineways.tech
- **Issues**: https://github.com/SinewaysTechnology/anymoment-python/issues

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
