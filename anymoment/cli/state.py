"""Global CLI flags and machine-readable output.

Flags are registered on every command so `--json` works after the subcommand.
Values live on the root context and in a context var the command body can read.
"""

import contextvars
import json
import sys
from typing import Any, Optional

import click

from anymoment.cli.exitcodes import (
    EXIT_AUTH,
    EXIT_CONFLICT,
    EXIT_NOT_FOUND,
    EXIT_RATE_LIMIT,
    EXIT_REMOTE,
    EXIT_USAGE,
)
from anymoment.exceptions import (
    AnyMomentException,
    AuthenticationError,
    ConflictError,
    EmailNotVerifiedError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    ServerError,
    UnprocessableError,
    ValidationError,
)

_STATE: contextvars.ContextVar[dict] = contextvars.ContextVar("anymoment_cli_state", default={})


def _root_obj(ctx: click.Context) -> dict:
    root = ctx.find_root()
    if not isinstance(root.obj, dict):
        root.obj = {}
    return root.obj


def remember(ctx: click.Context, param: click.Parameter, value: Any) -> Any:
    """Keep eager global flags on the root context."""
    data = _root_obj(ctx)
    if getattr(param, "is_flag", False):
        if value:
            data[param.name] = True
    elif value is not None:
        data[param.name] = value
    _STATE.set(data)
    return value


def global_options() -> list[click.Option]:
    """Fresh option objects. Click will not share one Option across commands."""
    return [
        click.Option(
            ["--json"],
            is_flag=True,
            expose_value=False,
            is_eager=True,
            callback=remember,
            help="Print one compact JSON object to stdout.",
        ),
        click.Option(
            ["--jsonl"],
            is_flag=True,
            expose_value=False,
            is_eager=True,
            callback=remember,
            help="Print one compact JSON object per line.",
        ),
        click.Option(
            ["--fields"],
            expose_value=False,
            is_eager=True,
            callback=remember,
            help="Comma-separated fields to keep in JSON output.",
        ),
        click.Option(
            ["--yes", "-y"],
            is_flag=True,
            expose_value=False,
            is_eager=True,
            callback=remember,
            help="Skip confirmations on a terminal.",
        ),
        click.Option(
            ["--dry-run"],
            is_flag=True,
            expose_value=False,
            is_eager=True,
            callback=remember,
            help="Show the mutation without sending it.",
        ),
        click.Option(
            ["--idempotency-key"],
            expose_value=False,
            is_eager=True,
            callback=remember,
            help="Local key. Repeating it returns the first result without calling the API again.",
        ),
    ]


def activate(ctx: click.Context) -> None:
    _STATE.set(_root_obj(ctx))


def state() -> dict:
    return _STATE.get()


def machine() -> bool:
    data = state()
    return bool(data.get("json") or data.get("jsonl"))


def jsonl_mode() -> bool:
    return bool(state().get("jsonl"))


def dry_run() -> bool:
    return bool(state().get("dry_run"))


def confirmed() -> bool:
    return bool(state().get("yes"))


def idempotency_key() -> Optional[str]:
    value = state().get("idempotency_key")
    return str(value) if value else None


def field_names() -> Optional[list[str]]:
    raw = state().get("fields")
    if not raw:
        return None
    names = [part.strip() for part in str(raw).split(",") if part.strip()]
    return names or None


def to_plain(value: Any) -> Any:
    """Convert result objects to JSON-ready data. Nested dicts stay dicts."""
    if isinstance(value, dict):
        return {key: to_plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_plain(item) for item in value]
    as_dict = getattr(value, "as_dict", None)
    if callable(as_dict):
        return to_plain(as_dict())
    events = getattr(value, "events", None)
    failures = getattr(value, "failures", None)
    if events is not None and failures is not None and not isinstance(value, (str, bytes)):
        return {"events": to_plain(events), "failures": to_plain(failures)}
    return value


def _select(payload: dict, names: list[str]) -> dict:
    kept = {"v": payload.get("v", 1)}
    for name in names:
        if name == "v":
            continue
        if name in payload:
            kept[name] = payload[name]
    return kept


def envelope(data: Any) -> dict:
    plain = to_plain(data)
    if not isinstance(plain, dict):
        plain = {"result": plain}
    payload = {"v": 1, **{key: value for key, value in plain.items() if key != "v"}}
    names = field_names()
    if names:
        payload = _select(payload, names)
    return payload


def dump(data: Any) -> str:
    return json.dumps(data, separators=(",", ":"), sort_keys=True, default=str)


def emit(data: Any) -> str:
    """Print JSON and return the text that was written."""
    if jsonl_mode():
        plain = to_plain(data)
        rows = plain if isinstance(plain, list) else [plain]
        text = "\n".join(dump(envelope(row)) for row in rows)
        click.echo(text)
        return text
    text = dump(envelope(data))
    click.echo(text)
    return text


def exit_code_for(exc: BaseException) -> int:
    if isinstance(exc, (EmailNotVerifiedError, AuthenticationError)):
        return EXIT_AUTH
    if isinstance(exc, NotFoundError):
        return EXIT_NOT_FOUND
    if isinstance(exc, ConflictError):
        return EXIT_CONFLICT
    if isinstance(exc, (ValidationError, UnprocessableError)):
        return EXIT_USAGE
    if isinstance(exc, RateLimitError):
        return EXIT_RATE_LIMIT
    if isinstance(exc, click.UsageError):
        return EXIT_USAGE
    if isinstance(exc, (PermissionDeniedError, ServerError, AnyMomentException)):
        return EXIT_REMOTE
    if isinstance(exc, click.ClickException):
        return exc.exit_code
    return EXIT_REMOTE


def error_payload(exc: BaseException) -> dict:
    status = getattr(exc, "status_code", None)
    user_message = getattr(exc, "user_message", None) or str(exc)
    return {
        "code": getattr(exc, "code", None),
        "next_step": getattr(exc, "next_step", None),
        "retry_after": getattr(exc, "retry_after", None),
        "status": status,
        "user_message": user_message,
    }


def write_error(exc: BaseException, context: str = "Operation") -> None:
    """Write a failure to stderr. JSON when the caller asked for machine output."""
    payload = error_payload(exc)
    if machine():
        click.echo(dump({"error": payload}), err=True)
        return
    message = payload["user_message"]
    click.echo(f"[ERROR] {message}", err=True)
    if payload["next_step"]:
        click.echo(payload["next_step"], err=True)
    if isinstance(exc, AuthenticationError):
        click.echo("Run 'anymoment auth login' to authenticate.", err=True)


def fail(exc: BaseException, context: str = "Operation") -> None:
    write_error(exc, context)
    sys.exit(exit_code_for(exc))
