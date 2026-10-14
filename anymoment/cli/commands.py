"""CLI commands for AnyMoment."""

import builtins
import json
import os
import sys
import uuid
from datetime import date, datetime, time
from typing import Any, Optional

import click
from dateutil import tz as dateutil_tz

from anymoment import __version__
from anymoment.cli.exitcodes import EXIT_AUTH, EXIT_CODE_NAMES, EXIT_USAGE
from anymoment.cli.group import AgendaGroup, AnyMomentGroup
from anymoment.cli.human import paint, render_table
from anymoment.cli.idempotency import lookup as lookup_idempotency
from anymoment.cli.idempotency import store as store_idempotency
from anymoment.cli.state import (
    confirmed,
    dry_run,
    emit,
    fail,
    idempotency_key,
    machine,
)
from anymoment.client import Client
from anymoment.config import (
    get_api_url,
    get_config,
    get_default_calendar_id,
    get_default_timezone,
    set_config,
)
from anymoment.dates import DateParseError, resolve_window
from anymoment.exceptions import AuthenticationError
from anymoment.token_manager import (
    clear_all_tokens,
    delete_token,
    get_token,
    list_tokens,
)


def get_client(host=None, require_auth=True):
    """Get a configured client instance."""
    api_url = host or get_api_url()
    token = os.environ.get("ANYMOMENT_TOKEN") or get_token(api_url)
    client = Client(api_url=api_url, token=token)

    if require_auth and not token:
        fail(
            AuthenticationError(
                "Not authenticated. Run 'anymoment auth login' or set ANYMOMENT_TOKEN.",
                user_message="Not authenticated.",
                next_step="Run 'anymoment auth login' or set ANYMOMENT_TOKEN.",
            )
        )

    return client


def resolve_calendar_id(client, calendar_ref: Optional[str]):
    """Resolve calendar by name or ID. Returns calendar ID or None if no ref and no default. Exits on error if ref given but not found or ambiguous."""
    if calendar_ref is None or calendar_ref.strip() == "":
        return get_default_calendar_id()
    ref = calendar_ref.strip()
    # Treat as UUID if it looks like one (hex + optional hyphens)
    try:
        uuid.UUID(ref)
        return ref
    except (ValueError, AttributeError, TypeError):
        pass
    # Resolve by name (case-insensitive exact match)
    calendars = client.list_calendars()
    name_lower = ref.lower()
    matches = [c for c in calendars if (c.get("name") or "").strip().lower() == name_lower]
    if not matches:
        click.echo(f"[ERROR] No calendar found with name '{ref}'. Use 'anymoment calendars list' to see calendars.", err=True)
        sys.exit(1)
    if len(matches) > 1:
        if sys.stdin.isatty() and not machine():
            labels = [f"{cal.get('name')} ({cal.get('id')})" for cal in matches]
            choice = click.prompt("Which calendar?", type=click.Choice(labels), show_choices=True)
            return matches[labels.index(choice)].get("id")
        click.echo(
            f"[ERROR] Multiple calendars match '{ref}'. Use the calendar ID. "
            "A picker is available on a terminal.",
            err=True,
        )
        sys.exit(EXIT_USAGE)
    return matches[0].get("id")


def resolve_calendar_ids(client, calendar_ref: Optional[str]):
    """Resolve comma-separated calendar names/IDs to a list of calendar IDs. Returns None if ref is empty."""
    if not calendar_ref or not calendar_ref.strip():
        return None
    return [resolve_calendar_id(client, c.strip()) for c in calendar_ref.split(",")]


def handle_api_error(e, context="Operation"):
    """Handle API errors with a stable exit code and a stderr payload."""
    fail(e, context)


def _agenda_parts(items):
    """Accept an AgendaResult, a {events, failures} dict, or a legacy list."""
    # `list` is a Click command in this module, so the builtin is explicit.
    items_type = builtins.list
    if isinstance(items, dict) and "events" in items:
        return items_type(items.get("events") or []), items_type(items.get("failures") or [])
    if isinstance(items, items_type):
        return items, []
    events = getattr(items, "events", None)
    failures = getattr(items, "failures", None)
    if events is not None:
        return items_type(events or []), items_type(failures or [])
    return [], []


def _warnings_of(result):
    if isinstance(result, dict):
        return result.get("sync_warnings") or result.get("google_export_warnings") or []
    return getattr(result, "sync_warnings", None) or getattr(result, "google_export_warnings", None) or []


def _finish_mutation(result, ok_text: str):
    """Print a mutation. Machine output is the body. A repeat key replays it."""
    if machine():
        text = emit(result)
    else:
        click.echo(ok_text)
        for warning in _warnings_of(result):
            message = warning.get("user_message") if isinstance(warning, dict) else getattr(warning, "user_message", "")
            step = warning.get("next_step") if isinstance(warning, dict) else getattr(warning, "next_step", "")
            if message:
                click.echo(message)
            if step:
                click.echo(step)
        text = ok_text
    store_idempotency(idempotency_key(), text)


def _replay_or_dry_run(op: str, target: str) -> bool:
    """Stop when this call is a dry run or a replay of a previous key."""
    if dry_run():
        if machine():
            emit({"dry_run": True, "op": op, "target": target})
        else:
            click.echo(f"dry-run {op} {target}")
        return True
    cached = lookup_idempotency(idempotency_key())
    if cached is not None:
        click.echo(cached)
        return True
    return False


def format_output(data, raw=False, pipe=False):
    """Format and output data with improved UX."""
    if machine() and not pipe:
        emit(data)
        return
    # Import built-in types to avoid shadowing issues
    import builtins
    list_type = builtins.list
    dict_type = builtins.dict
    
    if pipe:
        # Output only IDs for piping/chaining
        if isinstance(data, list_type):
            for item in data:
                if isinstance(item, dict_type):
                    # Agenda/search items have nested "event"
                    if "event" in item and isinstance(item.get("event"), dict_type):
                        click.echo(item["event"].get("id", ""))
                    else:
                        click.echo(item.get("id", ""))
                else:
                    click.echo(str(item))
        elif isinstance(data, dict_type):
            click.echo(data.get("id", ""))
        else:
            click.echo(str(data))
    elif raw:
        # Output full JSON
        click.echo(json.dumps(data, indent=2, default=str))
    else:
        # Human-readable format with better formatting
        if isinstance(data, list_type):
            if not data:
                click.echo("No results found.")
                return
            
            # Agenda/search items: event + instances (and optional score)
            first = data[0] if data else None
            if isinstance(first, dict_type) and "event" in first and isinstance(first.get("event"), dict_type):
                for item in data:
                    ev = item["event"]
                    name = ev.get("display_name") or ev.get("name") or ev.get("id", "N/A")
                    if "is_active" in ev:
                        status = "[OK]" if ev["is_active"] else "[X]"
                        name = f"{status} {name}"
                    score = item.get("score")
                    if score is not None:
                        name = f"{name} (score: {score:.2f})"
                    click.echo(f"  {paint(name, bold=True)}")
                    origin = ev.get("external_origin") or {}
                    if ev.get("google_origin") or (isinstance(origin, dict) and origin.get("read_only")):
                        click.echo("    read-only")
                    for inst in item.get("instances") or []:
                        start_ts = inst.get("start") or ""
                        end_ts = inst.get("end") or ""
                        all_day = inst.get("is_all_day", False)
                        suffix = " [all day]" if all_day else ""
                        click.echo(f"    {start_ts} – {end_ts}{suffix}")
                return
            if data and all(isinstance(item, dict_type) for item in data) and render_table(data):
                return
            # Format as table for better readability
            for idx, item in enumerate(data, 1):
                if isinstance(item, dict_type):
                    name = item.get("name", item.get("id", "N/A"))
                    # Add status indicators
                    if "is_active" in item:
                        status = "[OK]" if item["is_active"] else "[X]"
                        name = f"{status} {name}"
                    # Add additional info if available
                    if "event_count" in item:
                        count = item["event_count"]
                        click.echo(f"  {name} ({count} events)")
                    elif "timezone" in item:
                        tz = item.get("timezone", "UTC")
                        click.echo(f"  {name} [{tz}]")
                    else:
                        click.echo(f"  {name}")
                else:
                    click.echo(f"  {item}")
        elif isinstance(data, dict_type):
            # Pretty print dictionary with better formatting
            for key, value in data.items():
                if key == "id":
                    continue  # Skip ID in detailed view
                # Check if value is dict or list - check each type separately for compatibility
                if isinstance(value, dict_type) or isinstance(value, list_type):
                    if value:  # Only show non-empty collections
                        click.echo(f"\n{key.replace('_', ' ').title()}:")
                        format_output(value, raw=False, pipe=False)
                elif value is not None:
                    # Format key nicely
                    display_key = key.replace('_', ' ').title()
                    # Check bool type safely
                    if type(value) == bool:
                        display_value = "Yes" if value else "No"
                    elif isinstance(value, str) and len(value) > 60:
                        display_value = value[:57] + "..."
                    else:
                        display_value = str(value)
                    click.echo(f"  {display_key}: {display_value}")
        else:
            click.echo(str(data))


@click.group(cls=AnyMomentGroup)
@click.version_option(version=__version__)
def cli():
    """AnyMoment CLI - Manage calendars and events."""
    pass


@cli.group()
def auth():
    """Authentication commands."""
    pass


@auth.command()
@click.option("--email", default=None, help="Account email. Required when stdin is not a terminal.")
@click.option("--password", default=None, help="Account password. Required when stdin is not a terminal.")
@click.option("--host", "-h", default=None, help="API host URL")
def login(email, password, host):
    """Log in. Prompts only on a terminal. ANYMOMENT_TOKEN skips the prompt."""
    api_url = host or get_api_url()
    env_token = os.environ.get("ANYMOMENT_TOKEN")
    if env_token and not email and not password:
        client = Client(api_url=api_url, token=env_token)
        client._set_token(env_token)
        if machine():
            emit({"status": "saved", "host": api_url})
        else:
            click.echo("[OK] Login successful!")
            click.echo(f"  Token saved for {api_url}")
        return

    if not email or not password:
        if not sys.stdin.isatty():
            fail(
                AuthenticationError(
                    "Email and password are required when stdin is not a terminal.",
                    user_message="Not authenticated.",
                    next_step="Pass --email and --password, or set ANYMOMENT_TOKEN.",
                )
            )
        email = email or click.prompt("Email", type=str)
        password = password or click.prompt("Password", type=str, hide_input=True)

    try:
        client = Client(api_url=api_url)
        client.login(email, password)
        if machine():
            emit({"status": "saved", "host": api_url})
        else:
            click.echo("[OK] Login successful!")
            click.echo(f"  Token saved for {api_url}")
    except Exception as e:
        handle_api_error(e, "Login")


@auth.command("resend-verification")
@click.option("--host", "-h", default=None, help="API host URL")
def resend_verification(host):
    """Send the verification email again."""
    try:
        client = get_client(host)
        result = client.resend_verification()
        if machine():
            emit(result)
            return
        status = result.get("status") if isinstance(result, dict) else getattr(result, "status", "sent")
        click.echo(status or "sent")
    except Exception as e:
        handle_api_error(e, "Resend verification")


@auth.command()
@click.option("--host", "-h", default=None, help="API host URL")
def logout(host):
    """Clear cached token for host."""
    api_url = host or get_api_url()
    delete_token(api_url)
    click.echo(f"[OK] Logged out from {api_url}")


@cli.group()
def tokens():
    """Token management."""
    pass


@tokens.command()
def list():
    """Show all cached tokens with expiry status."""
    tokens = list_tokens()
    if not tokens:
        click.echo("No tokens found.")
        click.echo("  Run 'anymoment auth login' to authenticate.")
        return
    
    click.echo("Cached tokens:\n")
    for host_url, info in tokens.items():
        if info.get("invalid"):
            status_icon = "[X]"
            status_text = "invalid (not a valid JWT token)"
        elif info["expired"]:
            status_icon = "[X]"
            status_text = "expired"
        else:
            status_icon = "[OK]"
            status_text = "valid"
        
        expires = info["expires_at"] or "never"
        click.echo(f"  {status_icon} {host_url}")
        click.echo(f"    Status: {status_text}")
        click.echo(f"    Expires: {expires}")
        
        if info.get("invalid"):
            click.echo(f"    Note: Token appears to be invalid. Please login again.")
        click.echo()


@tokens.command()
def clear():
    """Clear all cached tokens."""
    clear_all_tokens()
    click.echo("[OK] All tokens cleared")


@cli.group()
def config():
    """Configuration management."""
    pass


@config.command()
@click.argument("url")
def set_url(url: str):
    """Set default API URL."""
    set_config("default_api_url", url)
    click.echo(f"[OK] Default API URL set to {url}")
    click.echo("  This will be used for all commands unless --host is specified.")


@config.command()
@click.argument("timezone")
def set_timezone(timezone: str):
    """Set default timezone (IANA format, e.g., America/New_York)."""
    set_config("default_timezone", timezone)
    click.echo(f"[OK] Default timezone set to {timezone}")
    click.echo("  This will be used for event creation unless --timezone is specified.")


@config.command()
@click.argument("calendar_id")
def set_calendar(calendar_id: str):
    """Set default calendar ID."""
    set_config("default_calendar_id", calendar_id)
    click.echo(f"[OK] Default calendar ID set to {calendar_id}")
    click.echo("  This will be used for event creation unless --calendar is specified.")


@config.command()
def show():
    """Display current configuration."""
    config = {
        "default_api_url": get_config("default_api_url") or "https://api.anymoment.sineways.tech",
        "default_timezone": get_config("default_timezone") or "UTC",
        "default_calendar_id": get_config("default_calendar_id") or "(not set)",
    }
    click.echo("Current configuration:\n")
    format_output(config)


@cli.command()
@click.argument("text")
@click.option("--calendar", "-c", default=None, help="Calendar name or ID (defaults to config default)")
@click.option("--context", default=None, help="Optional context about the text source")
@click.option("--timezone", "-z", default=None, help="Timezone for extracted events (defaults to config or UTC)")
@click.option("--model", default="high", type=click.Choice(["high", "low", "mega"]), help="Model: high, low, mega")
@click.option("--host", "-h", help="API host URL")
@click.option("--raw", is_flag=True, help="Output full JSON response")
def create(text, calendar, context, timezone, model, host, raw):
    """Create events from free-form text (extract + create in one step)."""
    try:
        client = get_client(host)
        cal_id = resolve_calendar_id(client, calendar)
        tz = timezone or get_default_timezone()
        result = client.extract_and_create_events(
            text=text,
            context=context,
            timezone=tz,
            model=model,
            calendar_id=cal_id,
        )
        if raw:
            format_output(result, raw=True)
            return
        summary = result.get("summary") or {}
        total = summary.get("total_extracted", 0)
        created = summary.get("successfully_created", 0)
        failed = summary.get("failed_to_create", 0)
        click.echo(f"[OK] Extracted {total} event(s), created {created}, failed {failed}.")
        for cr in result.get("created_events") or []:
            ev = (cr.get("extracted_event") or {}).get("name", "?")
            eid = cr.get("event_id")
            if cr.get("success") and eid:
                click.echo(f"  Created: {ev} ({eid})")
            else:
                click.echo(f"  Failed:  {ev} — {cr.get('error_message', 'unknown')}")
    except Exception as e:
        handle_api_error(e, "Create events")


@cli.command()
@click.argument("event_id")
@click.option("--when", "-w", default=None, help="New recurrence/schedule (natural language)")
@click.option("--title", "-t", default=None, help="New event title/name")
@click.option("--description", "-d", default=None, help="New event description")
@click.option("--timezone", "-z", default=None, help="Timezone for recurrence (defaults to config or UTC)")
@click.option("--model", default="high", type=click.Choice(["high", "low", "mega"]), help="Model for --when parsing")
@click.option("--host", "-h", help="API host URL")
@click.option("--raw", is_flag=True, help="Output full JSON")
def update(event_id, when, title, description, timezone, model, host, raw):
    """Update an event (schedule, title, and/or description). At least one of --when, --title, --description required."""
    if not any([when, title, description]):
        click.echo("[ERROR] Provide at least one of: --when, --title, --description", err=True)
        sys.exit(1)
    try:
        client = get_client(host)
        tz = timezone or get_default_timezone()
        if when is not None:
            ev = client.get_event(event_id)
            current_name = ev.get("name") or ev.get("display_name") or "Event"
            current_desc = ev.get("description")
            event = client.update_event_from_text(
                event_id=event_id,
                recurrence_text=when,
                name=title if title is not None else current_name,
                description=description if description is not None else current_desc,
                timezone=tz,
                model=model,
            )
        else:
            event = client.update_event(
                event_id=event_id,
                name=title,
                description=description,
            )
        if not machine() and not raw:
            click.echo("[OK] Event updated successfully!\n")
        format_output(event, raw=raw)
    except Exception as e:
        handle_api_error(e, "Update event")


@cli.group()
def calendars():
    """Calendar management."""
    pass


@calendars.command()
@click.option("--active/--inactive", default=None, help="Filter by active status")
@click.option("--limit", "-l", type=int, help="Maximum number of results")
@click.option("--offset", "-s", type=int, help="Number of results to skip")
@click.option("--host", "-h", help="API host URL")
@click.option("--raw", is_flag=True, help="Output full JSON")
@click.option("--pipe", is_flag=True, help="Output only IDs")
def list(active, limit, offset, host, raw, pipe):
    """List calendars."""
    try:
        client = get_client(host)
        calendars = client.list_calendars(
            is_active=active,
            limit=limit,
            offset=offset,
        )
        if not machine() and not raw and not pipe and calendars:
            click.echo(f"Found {len(calendars)} calendar(s):\n")
        format_output(calendars, raw=raw, pipe=pipe)
    except Exception as e:
        handle_api_error(e, "List calendars")


@calendars.command()
@click.argument("name")
@click.option("--description", help="Calendar description")
@click.option("--timezone", "-z", default=None, help="Calendar timezone (defaults to config or UTC)")
@click.option("--color", help="Calendar color")
@click.option("--host", "-h", help="API host URL")
@click.option("--raw", is_flag=True, help="Output full JSON")
def create(name, description, timezone, color, host, raw):
    """Create a new calendar."""
    try:
        client = get_client(host)
        # Use default timezone from config if not provided
        tz = timezone or get_default_timezone()
        calendar = client.create_calendar(
            name=name,
            description=description,
            timezone=tz,
            color=color,
        )
        if not machine() and not raw:
            click.echo("[OK] Calendar created successfully!\n")
        format_output(calendar, raw=raw)
        if not machine() and not raw:
            click.echo(f"\n  Calendar ID: {calendar.get('id', 'N/A')}")
    except Exception as e:
        handle_api_error(e, "Create calendar")


@calendars.command()
@click.argument("calendar_id")
@click.option("--host", "-h", help="API host URL")
@click.option("--raw", is_flag=True, help="Output full JSON")
def get(calendar_id, host, raw):
    """Get calendar details."""
    try:
        client = get_client(host)
        calendar = client.get_calendar(calendar_id)
        format_output(calendar, raw=raw)
    except Exception as e:
        handle_api_error(e, "Get calendar")


@calendars.command()
@click.argument("calendar_id")
@click.option("--name", help="Calendar name")
@click.option("--description", help="Calendar description")
@click.option("--timezone", "-z", help="Calendar timezone")
@click.option("--color", help="Calendar color")
@click.option("--active/--inactive", default=None, help="Active status")
@click.option("--host", "-h", help="API host URL")
@click.option("--raw", is_flag=True, help="Output full JSON")
def update(calendar_id, name, description, timezone, color, active, host, raw):
    """Update a calendar."""
    try:
        client = get_client(host)
        calendar = client.update_calendar(
            calendar_id=calendar_id,
            name=name,
            description=description,
            timezone=timezone,
            color=color,
            is_active=active,
        )
        if not machine() and not raw:
            click.echo("[OK] Calendar updated successfully!\n")
        format_output(calendar, raw=raw)
    except Exception as e:
        handle_api_error(e, "Update calendar")


@calendars.command()
@click.argument("calendar_id")
@click.option("--host", "-h", help="API host URL")
def delete(calendar_id, host):
    """Delete a calendar."""
    try:
        client = get_client(host)
        client.delete_calendar(calendar_id)
        click.echo("[OK] Calendar deleted successfully")
    except Exception as e:
        handle_api_error(e, "Delete calendar")


@calendars.command()
@click.argument("calendar_id")
@click.argument("user_id")
@click.option("--role", default="viewer", help="Role: owner, editor, viewer")
@click.option("--host", "-h", help="API host URL")
@click.option("--raw", is_flag=True, help="Output full JSON")
def share(calendar_id, user_id, role, host, raw):
    """Share a calendar with another user."""
    try:
        client = get_client(host)
        result = client.share_calendar(calendar_id, user_id, role)
        if not machine() and not raw:
            click.echo(f"[OK] Calendar shared with user {user_id} as {role}\n")
        format_output(result, raw=raw)
    except Exception as e:
        handle_api_error(e, "Share calendar")


@calendars.command()
@click.argument("calendar_id")
@click.option("--host", "-h", help="API host URL")
@click.option("--raw", is_flag=True, help="Output full JSON")
def webhook_url(calendar_id, host, raw):
    """Generate webhook URL for a calendar."""
    try:
        client = get_client(host)
        result = client.get_calendar_webhook_url(calendar_id)
        if not machine() and not raw:
            webhook_url = result.get("webhook_url", "N/A")
            click.echo(f"[OK] Webhook URL generated:\n  {webhook_url}\n")
        format_output(result, raw=raw)
    except Exception as e:
        handle_api_error(e, "Get webhook URL")


@calendars.command("add-event")
@click.argument("calendar_id")
@click.argument("event_id")
@click.option("--display-order", type=int, help="Display order")
@click.option("--color", help="Color override")
@click.option("--host", "-h", help="API host URL")
@click.option("--raw", is_flag=True, help="Output full JSON")
def add_event(calendar_id, event_id, display_order, color, host, raw):
    """Add an event to a calendar (link)."""
    try:
        client = get_client(host)
        result = client.link_event_to_calendar(
            calendar_id=calendar_id,
            event_id=event_id,
            display_order=display_order,
            color_override=color,
        )
        if not machine() and not raw:
            click.echo("[OK] Event added to calendar.\n")
        format_output(result, raw=raw)
    except Exception as e:
        handle_api_error(e, "Add event to calendar")


@calendars.command("remove-event")
@click.argument("calendar_id")
@click.argument("event_id")
@click.option("--host", "-h", help="API host URL")
def remove_event(calendar_id, event_id, host):
    """Remove an event from a calendar (unlink; event is not deleted)."""
    try:
        client = get_client(host)
        client.unlink_event_from_calendar(calendar_id=calendar_id, event_id=event_id)
        click.echo("[OK] Event removed from calendar.")
    except Exception as e:
        handle_api_error(e, "Remove event from calendar")


@calendars.command("batch-add-events")
@click.argument("calendar_id")
@click.argument("event_ids", nargs=-1, required=True)
@click.option("--display-order", type=int, help="Display order for all")
@click.option("--color", help="Color override for all")
@click.option("--host", "-h", help="API host URL")
@click.option("--raw", is_flag=True, help="Output full JSON")
def batch_add_events(calendar_id, event_ids, display_order, color, host, raw):
    """Add multiple events to a calendar in one request."""
    try:
        client = get_client(host)
        result = client.batch_add_events_to_calendar(
            calendar_id=calendar_id,
            event_ids=list(event_ids),
            display_order=display_order,
            color_override=color,
        )
        if not machine() and not raw:
            click.echo(f"[OK] Added {len(result)} event(s) to calendar.\n")
        format_output(result, raw=raw)
    except Exception as e:
        handle_api_error(e, "Batch add events to calendar")


@calendars.command("batch-remove-events")
@click.argument("calendar_id")
@click.argument("event_ids", nargs=-1, required=True)
@click.option("--host", "-h", help="API host URL")
def batch_remove_events(calendar_id, event_ids, host):
    """Remove multiple events from a calendar (unlink only)."""
    try:
        client = get_client(host)
        result = client.batch_remove_events_from_calendar(
            calendar_id=calendar_id,
            event_ids=list(event_ids),
        )
        if result:
            count = result.get("count", len(event_ids))
            click.echo(f"[OK] Removed {count} event(s) from calendar.")
    except Exception as e:
        handle_api_error(e, "Batch remove events from calendar")


@calendars.command("update-share")
@click.argument("calendar_id")
@click.argument("user_id")
@click.option("--role", required=True, help="New role: owner, editor, viewer")
@click.option("--host", "-h", help="API host URL")
@click.option("--raw", is_flag=True, help="Output full JSON")
def update_share(calendar_id, user_id, role, host, raw):
    """Update a shared user's role for a calendar."""
    try:
        client = get_client(host)
        result = client.update_calendar_share_role(calendar_id=calendar_id, user_id=user_id, role=role)
        if not machine() and not raw:
            click.echo(f"[OK] Share role updated to {role}.\n")
        format_output(result, raw=raw)
    except Exception as e:
        handle_api_error(e, "Update share role")


@calendars.command()
@click.argument("calendar_id")
@click.argument("user_id")
@click.option("--host", "-h", help="API host URL")
@click.option("--raw", is_flag=True, help="Output full JSON")
def unshare(calendar_id, user_id, host, raw):
    """Remove an AnyMoment share for a calendar (user loses access unless linked via Google)."""
    try:
        client = get_client(host)
        result = client.unshare_calendar(calendar_id=calendar_id, user_id=user_id)
        if not machine() and not raw:
            click.echo("[OK] Calendar unshared from user.\n")
        format_output(result, raw=raw)
    except Exception as e:
        handle_api_error(e, "Unshare calendar")


def _default_agenda_start_iso() -> str:
    """Default agenda window start: today 00:00 in default timezone, as UTC ISO."""
    tz_str = get_default_timezone()
    tz_obj = dateutil_tz.gettz(tz_str) or dateutil_tz.UTC
    start = datetime.combine(date.today(), time.min, tzinfo=tz_obj)
    utc = start.astimezone(dateutil_tz.UTC)
    return utc.strftime("%Y-%m-%dT%H:%M:%S") + "Z"


def _default_agenda_end_iso() -> str:
    """Default agenda window end: today 23:59:59 in default timezone, as UTC ISO."""
    tz_str = get_default_timezone()
    tz_obj = dateutil_tz.gettz(tz_str) or dateutil_tz.UTC
    end = datetime.combine(date.today(), time(23, 59, 59), tzinfo=tz_obj)
    utc = end.astimezone(dateutil_tz.UTC)
    return utc.strftime("%Y-%m-%dT%H:%M:%S") + "Z"


@cli.group(cls=AgendaGroup)
def agenda():
    """Agenda and search (time window and fuzzy search)."""
    pass


def _print_agenda(events, failures, raw, pipe):
    if machine():
        emit({"events": events, "failures": failures})
        return
    if not machine() and not raw and not pipe and events:
        click.echo(f"Found {len(events)} event(s) in window:\n")
    format_output(events, raw=raw, pipe=pipe)
    for failure in failures:
        name = failure.get("event_name") if isinstance(failure, dict) else getattr(failure, "event_name", "")
        message = failure.get("message") if isinstance(failure, dict) else getattr(failure, "message", "")
        click.echo(f"Failed: {name} {message}".strip(), err=True)


@agenda.command("show")
@click.argument("window", required=False, default="today")
@click.option("--calendar", "-c", default=None, help="Restrict to calendar name(s) or ID(s)")
@click.option("--host", "-h", help="API host URL")
@click.option("--raw", is_flag=True, help="Output full JSON")
@click.option("--pipe", is_flag=True, help="Output only event IDs")
def agenda_show(window, calendar, host, raw, pipe):
    """One-call agenda. Example: anymoment agenda \"next week\"."""
    _show_window(window, calendar, host, raw, pipe)


def _show_window(window, calendar, host, raw, pipe):
    try:
        start_iso, end_iso = resolve_window(window or "today", get_default_timezone())
    except DateParseError as exc:
        click.echo(str(exc), err=True)
        sys.exit(EXIT_USAGE)
    try:
        client = get_client(host)
        calendar_ids = resolve_calendar_ids(client, calendar)
        events, failures = _agenda_parts(
            client.get_agenda(start=start_iso, end=end_iso, calendar_ids=calendar_ids)
        )
        if machine():
            emit({"events": events, "failures": failures, "start": start_iso, "end": end_iso, "window": window})
            return
        click.echo(f"{start_iso} .. {end_iso}")
        _print_agenda(events, failures, raw, pipe)
    except Exception as e:
        handle_api_error(e, "Agenda")


@agenda.command("list")
@click.option("--start", "-s", default=None, help="Start of window (ISO 8601, e.g. 2025-02-03T00:00:00Z)")
@click.option("--end", "-e", default=None, help="End of window (ISO 8601)")
@click.option("--calendar", "-c", default=None, help="Restrict to calendar name(s) or ID(s); comma-separated for multiple")
@click.option("--no-cache", is_flag=True, help="Do not use instance cache")
@click.option("--webhooks", is_flag=True, help="Include webhooks in event payloads")
@click.option("--host", "-h", help="API host URL")
@click.option("--raw", is_flag=True, help="Output full JSON")
@click.option("--pipe", is_flag=True, help="Output only event IDs")
def agenda_list(start, end, calendar, no_cache, webhooks, host, raw, pipe):
    """List events and instances in a time window (agenda)."""
    try:
        start_iso = start if start is not None else _default_agenda_start_iso()
        end_iso = end if end is not None else _default_agenda_end_iso()
        client = get_client(host)
        calendar_ids = resolve_calendar_ids(client, calendar)
        events, failures = _agenda_parts(
            client.get_agenda(
                start=start_iso,
                end=end_iso,
                calendar_ids=calendar_ids,
                use_cache=not no_cache,
                include_webhooks=webhooks,
            )
        )
        _print_agenda(events, failures, raw, pipe)
    except Exception as e:
        handle_api_error(e, "Agenda list")


@agenda.command("search")
@click.argument("query")
@click.option("--start", "-s", default=None, help="Only events with instance on or after this time (ISO 8601)")
@click.option("--end", "-e", default=None, help="Only events with instance on or before this time (ISO 8601)")
@click.option("--calendar", "-c", default=None, help="Restrict to calendar name(s) or ID(s); comma-separated for multiple")
@click.option("--active/--inactive", default=None, help="Filter by active status")
@click.option("--limit", "-l", type=int, default=50, help="Max results (1-100)")
@click.option("--offset", type=int, default=0, help="Skip this many results")
@click.option("--no-instances", is_flag=True, help="Do not include instances in response when using --start/--end")
@click.option("--host", "-h", help="API host URL")
@click.option("--raw", is_flag=True, help="Output full JSON")
@click.option("--pipe", is_flag=True, help="Output only event IDs")
def agenda_search(query, start, end, calendar, active, limit, offset, no_instances, host, raw, pipe):
    """Fuzzy search events by name (optional time window and filters)."""
    try:
        client = get_client(host)
        calendar_ids = resolve_calendar_ids(client, calendar)
        items = client.search_events(
            q=query,
            start=start,
            end=end,
            calendar_ids=calendar_ids,
            is_active=active,
            limit=limit,
            offset=offset,
            include_instances=not no_instances,
        )
        if not machine() and not raw and not pipe and items:
            click.echo(f"Found {len(items)} event(s):\n")
        format_output(items, raw=raw, pipe=pipe)
    except Exception as e:
        handle_api_error(e, "Agenda search")


@cli.group()
def events():
    """Event management."""
    pass


@events.command()
@click.argument("text")
@click.option("--name", help="Event name hint (extracted from text if not provided)")
@click.option("--description", help="Event description hint")
@click.option("--timezone", "-z", default=None, help="Event timezone (defaults to config or UTC)")
@click.option("--calendar", "-c", default=None, help="Calendar name or ID (defaults to config default)")
@click.option("--model", default="high", type=click.Choice(["high", "low", "mega"]), help="Model: high, low, mega")
@click.option("--host", "-h", help="API host URL")
@click.option("--raw", is_flag=True, help="Output full JSON")
def create(
    text, name, description, timezone, calendar, model, host, raw
):
    """Create events from free-form text (extract + create; same as top-level 'anymoment create')."""
    try:
        client = get_client(host)
        cal_id = resolve_calendar_id(client, calendar)
        tz = timezone or get_default_timezone()
        context = None
        if name or description:
            parts = []
            if name:
                parts.append(f"Name: {name}")
            if description:
                parts.append(f"Description: {description}")
            context = "\n".join(parts)
        if dry_run():
            preview = client.preview_event_from_text(
                name=name or "Event",
                recurrence_text=text,
                start=_default_agenda_start_iso(),
                end=_default_agenda_end_iso(),
                description=description,
                timezone=tz,
                model=model if model in {"high", "low"} else "high",
            )
            if machine():
                emit({"dry_run": True, "op": "create", "preview": preview})
            else:
                click.echo("dry-run create")
                format_output(preview, raw=True)
            return
        if _replay_or_dry_run("create", text):
            return
        result = client.extract_and_create_events(
            text=text,
            context=context,
            timezone=tz,
            model=model,
            calendar_id=cal_id,
        )
        if raw:
            format_output(result, raw=True)
            return
        summary = result.get("summary") or {}
        total = summary.get("total_extracted", 0)
        created = summary.get("successfully_created", 0)
        failed = summary.get("failed_to_create", 0)
        click.echo(f"[OK] Extracted {total} event(s), created {created}, failed {failed}.")
        for cr in result.get("created_events") or []:
            ev = (cr.get("extracted_event") or {}).get("name", "?")
            eid = cr.get("event_id")
            if cr.get("success") and eid:
                click.echo(f"  Created: {ev} ({eid})")
            else:
                click.echo(f"  Failed:  {ev} — {cr.get('error_message', 'unknown')}")
    except Exception as e:
        handle_api_error(e, "Create event")


@events.command()
@click.option("--calendar", "-c", default=None, help="Calendar name or ID (defaults to config default)")
@click.option("--active/--inactive", default=None, help="Filter by active status")
@click.option("--limit", "-l", type=int, help="Maximum number of results")
@click.option("--offset", "-s", type=int, help="Number of results to skip")
@click.option("--minimal", is_flag=True, help="Return minimal event data")
@click.option("--host", "-h", help="API host URL")
@click.option("--raw", is_flag=True, help="Output full JSON")
@click.option("--pipe", is_flag=True, help="Output only IDs")
def list(calendar, active, limit, offset, minimal, host, raw, pipe):
    """List events."""
    try:
        client = get_client(host)
        cal_id = resolve_calendar_id(client, calendar)
        events = client.list_events(
            calendar_id=cal_id,
            is_active=active,
            limit=limit,
            offset=offset,
            minimal=minimal,
        )
        if not machine() and not raw and not pipe and events:
            click.echo(f"Found {len(events)} event(s):\n")
        format_output(events, raw=raw, pipe=pipe)
    except Exception as e:
        handle_api_error(e, "List events")


@events.command()
@click.argument("event_id")
@click.option("--host", "-h", help="API host URL")
@click.option("--raw", is_flag=True, help="Output full JSON")
def get(event_id, host, raw):
    """Get event details."""
    try:
        client = get_client(host)
        event = client.get_event(event_id)
        format_output(event, raw=raw)
    except Exception as e:
        handle_api_error(e, "Get event")


@events.command()
@click.argument("event_id")
@click.option("--when", "-w", default=None, help="New recurrence/schedule (natural language)")
@click.option("--title", "-t", default=None, help="New event title/name")
@click.option("--name", default=None, help="New event name (same as --title)")
@click.option("--description", "-d", default=None, help="New event description")
@click.option("--timezone", "-z", default=None, help="Timezone for recurrence (defaults to config or UTC)")
@click.option("--model", default="high", type=click.Choice(["high", "low", "mega"]), help="Model for --when parsing")
@click.option("--host", "-h", help="API host URL")
@click.option("--raw", is_flag=True, help="Output full JSON")
def update(event_id, when, title, name, description, timezone, model, host, raw):
    """Update an event (schedule, title, and/or description). Same as top-level 'anymoment update'."""
    title_or_name = title if title is not None else name
    if not any([when, title_or_name, description]):
        click.echo("[ERROR] Provide at least one of: --when, --title/--name, --description", err=True)
        sys.exit(1)
    try:
        client = get_client(host)
        tz = timezone or get_default_timezone()
        if when is not None:
            ev = client.get_event(event_id)
            current_name = ev.get("name") or ev.get("display_name") or "Event"
            current_desc = ev.get("description")
            event = client.update_event_from_text(
                event_id=event_id,
                recurrence_text=when,
                name=title_or_name if title_or_name is not None else current_name,
                description=description if description is not None else current_desc,
                timezone=tz,
                model=model,
            )
        else:
            event = client.update_event(
                event_id=event_id,
                name=title_or_name,
                description=description,
            )
        if not machine() and not raw:
            click.echo("[OK] Event updated successfully!\n")
        format_output(event, raw=raw)
    except Exception as e:
        handle_api_error(e, "Update event")


@events.command()
@click.argument("event_id")
@click.option("--host", "-h", help="API host URL")
def delete(event_id, host):
    """Delete an event. On a terminal, asks first unless --yes is set."""
    try:
        if sys.stdin.isatty() and not confirmed() and not dry_run():
            click.confirm(f"Delete event {event_id}?", abort=True)
        if _replay_or_dry_run("delete", event_id):
            return
        client = get_client(host)
        result = client.delete_event(event_id)
        _finish_mutation(result, "[OK] Event deleted successfully")
    except click.Abort:
        sys.exit(EXIT_USAGE)
    except Exception as e:
        handle_api_error(e, "Delete event")


@events.command()
@click.argument("event_id")
@click.option("--host", "-h", help="API host URL")
@click.option("--raw", is_flag=True, help="Output full JSON")
def toggle(event_id, host, raw):
    """Toggle event active status."""
    try:
        client = get_client(host)
        event = client.toggle_event(event_id)
        status = "activated" if event.get("is_active") else "deactivated"
        if not machine() and not raw:
            click.echo(f"[OK] Event {status} successfully!\n")
        format_output(event, raw=raw)
    except Exception as e:
        handle_api_error(e, "Toggle event")


@events.command()
@click.argument("event_id")
@click.option("--from", "from_date", help="Start date")
@click.option("--to", "to_date", help="End date")
@click.option("--optimized", is_flag=True, help="Return optimized format")
@click.option("--host", "-h", help="API host URL")
@click.option("--raw", is_flag=True, help="Output full JSON")
def instances(event_id, from_date, to_date, optimized, host, raw):
    """Get event instances for a date range."""
    try:
        client = get_client(host)
        instances = client.get_event_instances(
            event_id=event_id,
            from_date=from_date,
            to_date=to_date,
            optimized=optimized,
        )
        if not machine() and not raw and instances:
            click.echo(f"Found {len(instances)} instance(s):\n")
        format_output(instances, raw=raw)
    except Exception as e:
        handle_api_error(e, "Get event instances")


@events.command()
@click.argument("event_id")
@click.option("--host", "-h", help="API host URL")
@click.option("--raw", is_flag=True, help="Output full JSON")
def next(event_id, host, raw):
    """Get the next instance of an event."""
    try:
        client = get_client(host)
        instance = client.get_next_event_instance(event_id)
        if not machine() and not raw and instance:
            start = instance.get("start", "N/A")
            click.echo(f"Next occurrence: {start}\n")
        format_output(instance, raw=raw)
    except Exception as e:
        handle_api_error(e, "Get next instance")


@events.command()
@click.argument("event_id")
@click.option("--format", "format_type", type=click.Choice(["ics", "csv"]), default="ics", help="Export format")
@click.option("--from", "from_date", help="Start date")
@click.option("--to", "to_date", help="End date")
@click.option("--out", "output_file", help="Output file path")
@click.option("--host", "-h", help="API host URL")
def export(event_id, format_type, from_date, to_date, output_file, host):
    """Export event instances (ICS/CSV formats)."""
    try:
        client = get_client(host)
        instances = client.get_event_instances(
            event_id=event_id,
            from_date=from_date,
            to_date=to_date,
        )
        
        # For now, just output JSON - full ICS/CSV export can be added later
        if output_file:
            with open(output_file, "w") as f:
                json.dump(instances, f, indent=2, default=str)
            click.echo(f"[OK] Exported {len(instances)} instance(s) to {output_file}")
        else:
            format_output(instances, raw=True)
    except Exception as e:
        handle_api_error(e, "Export events")


@cli.group()
def users():
    """User management."""
    pass


@users.command()
@click.option("--host", "-h", help="API host URL")
@click.option("--raw", is_flag=True, help="Output full JSON")
def me(host, raw):
    """Show current user info."""
    try:
        client = get_client(host)
        user = client.get_user_info()
        if machine():
            emit(user)
            return
        if not machine() and not raw:
            email = user.get("email", "N/A") if isinstance(user, dict) else getattr(user, "email", "N/A")
            click.echo(f"Logged in as: {email}\n")
        format_output(user, raw=raw)
    except Exception as e:
        handle_api_error(e, "Get user info")


def _schema_document():
    def walk(group, prefix):
        found = []
        for name, cmd in group.commands.items():
            path = f"{prefix} {name}".strip()
            if isinstance(cmd, click.Group):
                found.extend(walk(cmd, path))
            else:
                found.append(path)
        return found

    return {
        "v": 1,
        "commands": walk(cli, ""),
        "exit_codes": {name: code for code, name in EXIT_CODE_NAMES.items()},
        "aliases": {
            "a": "agenda",
            "am": "anymoment",
            "ls": "calendars list",
            "rm": "events delete",
            "today": "agenda today",
            "week": "agenda this week",
            "next": "agenda next week",
        },
        "flags": [
            "--json",
            "--jsonl",
            "--fields",
            "--yes",
            "--dry-run",
            "--idempotency-key",
            "--profile",
        ],
    }


def _echo_schema():
    click.echo(json.dumps(_schema_document(), separators=(",", ":"), sort_keys=True))


@cli.command("schema")
def schema():
    """Print the command list and exit codes as JSON."""
    _echo_schema()


@cli.command("help")
@click.argument("topic", required=False)
def help_command(topic):
    """Show help. With --json, print the same document as `anymoment schema`."""
    if machine():
        _echo_schema()
        return
    click.echo(cli.get_help(click.Context(cli)))


def _window_options(func):
    func = click.option("--pipe", is_flag=True, help="Output only event IDs")(func)
    func = click.option("--raw", is_flag=True, help="Output full JSON")(func)
    func = click.option("--host", "-h", default=None, help="API host URL")(func)
    func = click.option("--calendar", "-c", default=None, help="Calendar name or ID")(func)
    return func


@cli.command("today")
@_window_options
def today(calendar, host, raw, pipe):
    """Show today's agenda."""
    _show_window("today", calendar, host, raw, pipe)


@cli.command("week")
@_window_options
def week(calendar, host, raw, pipe):
    """Show this week's agenda."""
    _show_window("this week", calendar, host, raw, pipe)


@cli.command("next")
@_window_options
def next_window(calendar, host, raw, pipe):
    """Show next week's agenda."""
    _show_window("next week", calendar, host, raw, pipe)


@cli.command("completion")
@click.argument("shell", type=click.Choice(["bash", "zsh", "fish"]))
def completion(shell):
    """Print a shell completion snippet for bash, zsh, or fish."""
    variable = "_ANYMOMENT_COMPLETE"
    if shell == "fish":
        click.echo(f"{variable}=fish_source anymoment | source")
        return
    click.echo(f'eval "$({variable}={shell}_source anymoment)"')


@events.command("batch")
@click.option("--host", "-h", default=None, help="API host URL")
def batch(host):
    """Apply create, update, delete, and link operations from JSONL on stdin."""
    raw_input = sys.stdin.read()
    if not raw_input.strip():
        click.echo("Expected JSONL operations on stdin.", err=True)
        sys.exit(EXIT_USAGE)
    try:
        client = get_client(host)
        results = []
        for line in raw_input.splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            op = item.get("op")
            if op == "create":
                results.append(
                    client.extract_and_create_events(
                        text=item.get("text") or item.get("recurrence_text") or ""
                    )
                )
            elif op == "update":
                results.append(
                    client.update_event(
                        item["id"],
                        name=item.get("name"),
                        description=item.get("description"),
                    )
                )
            elif op == "delete":
                results.append(client.delete_event(item["id"]))
            elif op == "link":
                results.append(
                    client.link_event_to_calendar(item["calendar_id"], item["event_id"])
                )
            else:
                click.echo(f"Unknown batch op: {op}", err=True)
                sys.exit(EXIT_USAGE)
        if machine():
            emit(results)
        else:
            click.echo(f"Applied {len(results)} operation(s).")
    except Exception as e:
        handle_api_error(e, "Batch")
