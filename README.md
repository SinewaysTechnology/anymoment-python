# AnyMoment Python SDK & CLI

Python SDK and command-line interface for the [AnyMoment API](https://api.anymoment.sineways.tech) - Create and manage recurring calendar events with natural language.

## Features

- 🎯 **Natural Language Event Creation** - Create complex recurring events from simple text
- 📅 **Full Calendar Management** - Create, update, delete, and share calendars
- 🔐 **Secure Token Management** - Encrypted token storage with automatic refresh
- 🚀 **Both Library & CLI** - Use programmatically or from the command line
- ⚡ **Fast & Reliable** - Built on requests with proper error handling

## Installation

### Library Only

```bash
pip install anymoment
```

### With CLI

```bash
pip install anymoment[cli]
```

## Quick Start

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

## Configuration

### Environment Variables

- `ANYMOMENT_BASE_URL` - Default API base URL (default: `https://api.anymoment.sineways.tech`)
- `ANYMOMENT_DEFAULT_CALENDAR` - Default calendar ID
- `ANYMOMENT_DEFAULT_TIMEZONE` - Default timezone

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

### Authentication

```bash
# Login interactively
anymoment auth login [--host URL]

# Logout (clear token)
anymoment auth logout [--host URL]

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

# Share calendar
anymoment calendars share <id> <user-id> [--role ROLE]

# Get webhook URL
anymoment calendars webhook-url <id>
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

### Users

```bash
# Show current user info
anymoment users me
```

### Common Options

- `--host, -h URL` - Override API host URL (env: `ANYMOMENT_BASE_URL`)
- `--raw` - Output full JSON response
- `--pipe` - Output only IDs (for piping/chaining)
- `--timezone, -z TZ` - Override timezone for this command
- `--calendar, -c ID` - Specify calendar ID (or use default from config)

## Library API Reference

### Client Class

```python
from anymoment import Client

client = Client(api_url="https://api.anymoment.sineways.tech", token="optional-token")
```

#### Authentication

- `client.login(email, password)` - Authenticate and get token
- `client.refresh_token()` - Refresh current token
- `client.get_user_info()` - Get current user information

#### Calendars

- `client.list_calendars(is_active=None, limit=None, offset=None)` - List calendars
- `client.get_calendar(calendar_id)` - Get calendar by ID
- `client.create_calendar(name, description=None, timezone="UTC", color=None)` - Create calendar
- `client.update_calendar(calendar_id, name=None, description=None, timezone=None, color=None, is_active=None)` - Update calendar
- `client.delete_calendar(calendar_id)` - Delete calendar
- `client.share_calendar(calendar_id, user_id, role="viewer")` - Share calendar
- `client.get_calendar_webhook_url(calendar_id)` - Get webhook URL

#### Events

- `client.list_events(calendar_id=None, is_active=None, limit=None, offset=None, minimal=False)` - List events
- `client.get_event(event_id)` - Get event by ID
- `client.create_event_from_text(recurrence_text, name=None, description=None, timezone="UTC", calendar_id=None, model="high")` - Create event from natural language
- `client.update_event(event_id, name=None, description=None)` - Update event
- `client.delete_event(event_id)` - Delete event
- `client.toggle_event(event_id)` - Toggle event active status
- `client.get_event_instances(event_id, from_date=None, to_date=None, optimized=False)` - Get event instances
- `client.get_next_event_instance(event_id)` - Get next instance

#### Calendar-Event Links

- `client.link_event_to_calendar(calendar_id, event_id, display_order=None, color_override=None)` - Link event to calendar
- `client.unlink_event_from_calendar(calendar_id, event_id)` - Unlink event from calendar

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

## Error Handling

The SDK raises specific exceptions for different error types:

```python
from anymoment import (
    AuthenticationError,
    NotFoundError,
    ValidationError,
    ServerError,
)

try:
    calendar = client.get_calendar("invalid-id")
except NotFoundError:
    print("Calendar not found")
except AuthenticationError:
    print("Authentication failed - please login again")
except ValidationError as e:
    print(f"Validation error: {e.message}")
except ServerError as e:
    print(f"Server error: {e.message}")
```

## Token Management

Tokens are automatically stored encrypted in `~/.anymoment/tokens.json` using machine-specific encryption. The SDK handles:

- Automatic token refresh on expiration
- Multi-host token storage
- Secure encryption using Fernet

## Development

### Running Tests

```bash
# Install development dependencies
pip install -e ".[cli]"
pip install pytest pytest-mock pytest-cov build twine

# Run tests
pytest

# Run with coverage
pytest --cov=anymoment --cov-report=html
```

### Building Distribution

```bash
# Install build tools
pip install build twine

# Build distributions
python -m build

# Check distributions
twine check dist/*
```

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Support

- **Documentation**: https://docs.anymoment.ai
- **API Base URL**: https://api.anymoment.sineways.tech
- **Issues**: https://github.com/sineways/anymoment-python/issues

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
