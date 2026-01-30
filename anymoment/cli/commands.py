"""CLI commands for AnyMoment."""

import json
import sys
from datetime import date, datetime, time
from typing import Any, Optional

import click
from dateutil import tz as dateutil_tz

from anymoment.client import Client
from anymoment.config import (
    get_api_url,
    get_config,
    get_default_calendar_id,
    get_default_timezone,
    set_config,
)
from anymoment.exceptions import AuthenticationError, AnyMomentException
from anymoment.token_manager import (
    clear_all_tokens,
    delete_token,
    get_token,
    list_tokens,
)


def get_client(host=None, require_auth=True):
    """Get a configured client instance."""
    api_url = host or get_api_url()
    client = Client(api_url=api_url)
    
    if require_auth:
        token = get_token(api_url)
        if not token:
            click.echo("[ERROR] Not authenticated. Please run 'anymoment auth login' first.", err=True)
            sys.exit(2)
    
    return client


def handle_api_error(e, context="Operation"):
    """Handle API errors with helpful messages."""
    # Check exception type safely
    try:
        if isinstance(e, AuthenticationError):
            click.echo(f"[ERROR] Authentication failed: {e.message}", err=True)
            click.echo("   Run 'anymoment auth login' to authenticate.", err=True)
            sys.exit(2)
        elif isinstance(e, AnyMomentException):
            click.echo(f"[ERROR] {context} failed: {e.message}", err=True)
            if hasattr(e, 'details') and e.details:
                for key, value in e.details.items():
                    click.echo(f"   {key}: {value}", err=True)
            sys.exit(1)
        else:
            click.echo(f"[ERROR] {context} failed: {str(e)}", err=True)
            sys.exit(1)
    except TypeError:
        # Fallback if isinstance fails (shouldn't happen, but be safe)
        click.echo(f"[ERROR] {context} failed: {str(e)}", err=True)
        sys.exit(1)


def format_output(data, raw=False, pipe=False):
    """Format and output data with improved UX."""
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
                    click.echo(f"  {name}")
                    for inst in item.get("instances") or []:
                        start_ts = inst.get("start") or ""
                        end_ts = inst.get("end") or ""
                        all_day = inst.get("is_all_day", False)
                        suffix = " [all day]" if all_day else ""
                        click.echo(f"    {start_ts} – {end_ts}{suffix}")
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


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """AnyMoment CLI - Manage calendars and events."""
    pass


@cli.group()
def auth():
    """Authentication commands."""
    pass


@auth.command()
@click.option("--host", "-h", default=None, help="API host URL")
def login(host):
    """Interactive login (prompts for email/password)."""
    api_url = host or get_api_url()
    click.echo(f"Logging in to {api_url}...")
    
    email = click.prompt("Email", type=str, default=None)
    if not email:
        click.echo("[ERROR] Email is required.", err=True)
        sys.exit(1)
    
    password = click.prompt("Password", type=str, hide_input=True, default=None)
    if not password:
        click.echo("[ERROR] Password is required.", err=True)
        sys.exit(1)
    
    try:
        client = Client(api_url=api_url)
        token = client.login(email, password)
        click.echo("[OK] Login successful!")
        click.echo(f"  Token saved for {api_url}")
    except AuthenticationError as e:
        click.echo(f"[ERROR] Authentication failed: {e.message}", err=True)
        click.echo("   Please check your email and password.", err=True)
        sys.exit(2)
    except Exception as e:
        handle_api_error(e, "Login")


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
        if not raw and not pipe and calendars:
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
        if not raw:
            click.echo("[OK] Calendar created successfully!\n")
        format_output(calendar, raw=raw)
        if not raw:
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
        if not raw:
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
        if not raw:
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
        if not raw:
            webhook_url = result.get("webhook_url", "N/A")
            click.echo(f"[OK] Webhook URL generated:\n  {webhook_url}\n")
        format_output(result, raw=raw)
    except Exception as e:
        handle_api_error(e, "Get webhook URL")


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


@cli.group()
def agenda():
    """Agenda and search (time window and fuzzy search)."""
    pass


@agenda.command("list")
@click.option("--start", "-s", default=None, help="Start of window (ISO 8601, e.g. 2025-02-03T00:00:00Z)")
@click.option("--end", "-e", default=None, help="End of window (ISO 8601)")
@click.option("--calendar", "-c", default=None, help="Restrict to calendar ID(s); comma-separated for multiple")
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
        calendar_ids = [x.strip() for x in calendar.split(",")] if calendar else None
        client = get_client(host)
        items = client.get_agenda(
            start=start_iso,
            end=end_iso,
            calendar_ids=calendar_ids,
            use_cache=not no_cache,
            include_webhooks=webhooks,
        )
        if not raw and not pipe and items:
            click.echo(f"Found {len(items)} event(s) in window:\n")
        format_output(items, raw=raw, pipe=pipe)
    except Exception as e:
        handle_api_error(e, "Agenda list")


@agenda.command("search")
@click.argument("query")
@click.option("--start", "-s", default=None, help="Only events with instance on or after this time (ISO 8601)")
@click.option("--end", "-e", default=None, help="Only events with instance on or before this time (ISO 8601)")
@click.option("--calendar", "-c", default=None, help="Restrict to calendar ID(s); comma-separated for multiple")
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
        calendar_ids = [x.strip() for x in calendar.split(",")] if calendar else None
        client = get_client(host)
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
        if not raw and not pipe and items:
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
@click.option("--name", help="Event name (extracted from text if not provided)")
@click.option("--description", help="Event description")
@click.option("--timezone", "-z", default=None, help="Event timezone (defaults to config or UTC)")
@click.option("--calendar", "-c", default=None, help="Calendar ID (defaults to config default)")
@click.option("--model", default="high", type=click.Choice(["high", "low", "mega"]), help="Model: high, low, mega")
@click.option("--host", "-h", help="API host URL")
@click.option("--raw", is_flag=True, help="Output full JSON")
def create(
    text, name, description, timezone, calendar, model, host, raw
):
    """Create an event from natural language."""
    try:
        client = get_client(host)
        # Use defaults from config if not provided
        tz = timezone or get_default_timezone()
        cal_id = calendar or get_default_calendar_id()
        
        # Don't show calendar ID if using default - it's expected behavior
        
        event = client.create_event_from_text(
            recurrence_text=text,
            name=name,
            description=description,
            timezone=tz,
            calendar_id=cal_id,
            model=model,
        )
        if not raw:
            click.echo("[OK] Event created successfully!\n")
        format_output(event, raw=raw)
        if not raw:
            click.echo(f"\n  Event ID: {event.get('id', 'N/A')}")
    except Exception as e:
        handle_api_error(e, "Create event")


@events.command()
@click.option("--calendar", "-c", default=None, help="Calendar ID (defaults to config default)")
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
        # Use default calendar from config if not provided
        cal_id = calendar or get_default_calendar_id()
        
        events = client.list_events(
            calendar_id=cal_id,
            is_active=active,
            limit=limit,
            offset=offset,
            minimal=minimal,
        )
        if not raw and not pipe and events:
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
@click.option("--name", help="Event name")
@click.option("--description", help="Event description")
@click.option("--host", "-h", help="API host URL")
@click.option("--raw", is_flag=True, help="Output full JSON")
def update(event_id, name, description, host, raw):
    """Update an event."""
    try:
        client = get_client(host)
        event = client.update_event(event_id, name=name, description=description)
        if not raw:
            click.echo("[OK] Event updated successfully!\n")
        format_output(event, raw=raw)
    except Exception as e:
        handle_api_error(e, "Update event")


@events.command()
@click.argument("event_id")
@click.option("--host", "-h", help="API host URL")
def delete(event_id, host):
    """Delete an event."""
    try:
        client = get_client(host)
        client.delete_event(event_id)
        click.echo("[OK] Event deleted successfully")
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
        if not raw:
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
        if not raw and instances:
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
        if not raw and instance:
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
        if not raw:
            email = user.get("email", "N/A")
            click.echo(f"Logged in as: {email}\n")
        format_output(user, raw=raw)
    except Exception as e:
        handle_api_error(e, "Get user info")
