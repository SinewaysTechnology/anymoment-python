"""Console entry point that still runs on Python 3.9 long enough to explain why."""

import sys


def python_too_old_message() -> str:
    """What to tell someone whose interpreter cannot run AnyMoment."""
    found = ".".join(str(part) for part in sys.version_info[:3])
    return (
        f"AnyMoment requires Python 3.10 or newer. This interpreter is Python {found}.\n"
        "macOS system Python is often 3.9. pip then stops with "
        "`requires a different Python: 3.9.x not in '>=3.10'`.\n"
        "Install the CLI with a current Python instead:\n"
        '  uv tool install "anymoment[cli]"\n'
        '  pipx install "anymoment[cli]"\n'
    )


def main() -> None:
    if sys.version_info < (3, 10):
        sys.stderr.write(python_too_old_message())
        raise SystemExit(1)
    try:
        from anymoment.cli.commands import cli
    except Exception as exc:
        sys.stderr.write(f"[ERROR] {exc}\n")
        raise SystemExit(1) from exc
    cli()
