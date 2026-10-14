"""The public SDK does not wrap admin routes."""

from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / "anymoment"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
LIVE = Path(__file__).resolve().parent / "test_live_smoke.py"

FORBIDDEN_SNIPPETS = ("/admin", "/auth/admin", "/google/admin", "/api-keys")


def test_package_source_has_no_admin_routes():
    offenders = []
    for path in PACKAGE.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for snippet in FORBIDDEN_SNIPPETS:
            if snippet in text:
                offenders.append(f"{path.name}: {snippet}")
    assert offenders == []


def test_fixtures_have_no_admin_payloads():
    offenders = []
    for path in FIXTURES.iterdir():
        text = path.read_text(encoding="utf-8").lower()
        if "/admin" in text or "auth/admin" in text:
            offenders.append(path.name)
    assert offenders == []


def test_live_smoke_stays_read_only():
    text = LIVE.read_text(encoding="utf-8")
    for snippet in ("delete_", "create_", "update_", "login(", "resend_verification", "/admin"):
        assert snippet not in text
    assert "get_user_info" in text
    assert "get_agenda" in text
