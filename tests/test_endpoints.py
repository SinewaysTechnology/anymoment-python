"""Coverage for the user-facing routes added in 2.0."""

import json

import pytest
import responses

from anymoment.client import Client

from tests.support import API, CALENDAR_ID, EVENT_ID, load_fixture


@pytest.fixture
def client(mock_token_file):
    return Client(api_url=API, token="test-token")


def _last(rsps):
    return rsps.calls[-1].request


def _body(request):
    if not request.body:
        return None
    return json.loads(request.body)


def test_signup_change_and_reset_password(client):
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(responses.POST, f"{API}/auth/users", json={"id": "u1"}, status=201)
        rsps.add(responses.POST, f"{API}/auth/users/change-password", json={"ok": True}, status=200)
        rsps.add(responses.POST, f"{API}/auth/users/reset-password", json={"ok": True}, status=200)
        created = client.signup("a@example.com", "secret", display_name="Ada")
        client.change_password("new-secret", old_password="secret")
        client.reset_password("a@example.com", "newer-secret")
        signup, change, reset = (_body(call.request) for call in rsps.calls)
    assert created["id"] == "u1"
    assert signup == {"email": "a@example.com", "password": "secret", "display_name": "Ada"}
    assert change == {"new_password": "new-secret", "old_password": "secret"}
    assert reset == {"user": {"email": "a@example.com"}, "new_password": "newer-secret"}


def test_permanent_tokens_and_feedback(client):
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(responses.POST, f"{API}/auth/permanent-token", json={"token": "perm"}, status=201)
        rsps.add(responses.GET, f"{API}/auth/permanent-token", json=[{"token": "perm"}], status=200)
        rsps.add(responses.DELETE, f"{API}/auth/permanent-token", json={"ok": True}, status=200)
        rsps.add(responses.POST, f"{API}/auth/feedback", json={"ok": True}, status=201)
        token = client.create_permanent_token("a@example.com")
        listed = client.list_permanent_tokens()
        client.delete_permanent_token("perm")
        client.create_feedback("Loved the agenda", rating=5, title="Agenda")
        deleted = _body(rsps.calls[2].request)
        feedback = _body(rsps.calls[3].request)
    assert token["token"] == "perm"
    assert listed[0]["token"] == "perm"
    assert deleted == {"token": "perm"}
    assert feedback["message"] == "Loved the agenda"


def test_structured_create_preview_ics_and_batch(client):
    component = {"type": "daily"}
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(responses.POST, f"{API}/events", json={"id": EVENT_ID}, status=201)
        rsps.add(responses.POST, f"{API}/events/batch", json=[{"id": EVENT_ID}], status=200)
        rsps.add(
            responses.POST,
            f"{API}/events/from-recurrence-text/preview",
            json={"name": "Standup"},
            status=200,
        )
        rsps.add(responses.POST, f"{API}/events/from-ics", json={"id": EVENT_ID}, status=201)
        created = client.create_event("Standup", [component])
        batch = client.get_events_batch([EVENT_ID], minimal=True)
        preview = client.preview_event_from_text(
            "Standup",
            "Every weekday at 9",
            "2026-10-14T00:00:00Z",
            "2026-10-14T23:59:59Z",
        )
        from_ics = client.create_event_from_ics("BEGIN:VCALENDAR", name="Imported")
        bodies = [_body(call.request) for call in rsps.calls]
        urls = [call.request.url for call in rsps.calls]
    assert created.id == EVENT_ID
    assert batch[0]["id"] == EVENT_ID
    assert preview["name"] == "Standup"
    assert from_ics.id == EVENT_ID
    assert bodies[0]["components"] == [component]
    assert bodies[1] == {"event_ids": [EVENT_ID]}
    assert "minimal=true" in urls[1] or "minimal=True" in urls[1]
    assert bodies[2]["recurrence_text"] == "Every weekday at 9"
    assert bodies[3]["ics_content"] == "BEGIN:VCALENDAR"


def test_guests_and_webhooks(client):
    guest_id = "guest-1"
    webhook_id = "hook-1"
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(responses.GET, f"{API}/events/{EVENT_ID}/guests", json=[], status=200)
        rsps.add(responses.POST, f"{API}/events/{EVENT_ID}/guests", json={"id": guest_id}, status=201)
        rsps.add(
            responses.PATCH,
            f"{API}/events/{EVENT_ID}/guests/{guest_id}",
            json={"id": guest_id},
            status=200,
        )
        rsps.add(responses.DELETE, f"{API}/events/{EVENT_ID}/guests/{guest_id}", json={"ok": True}, status=200)
        rsps.add(responses.GET, f"{API}/events/{EVENT_ID}/webhooks", json=[], status=200)
        rsps.add(
            responses.POST,
            f"{API}/events/{EVENT_ID}/webhooks",
            json={"id": webhook_id},
            status=201,
        )
        rsps.add(
            responses.GET,
            f"{API}/events/{EVENT_ID}/webhooks/{webhook_id}",
            json={"id": webhook_id},
            status=200,
        )
        rsps.add(
            responses.PUT,
            f"{API}/events/{EVENT_ID}/webhooks/{webhook_id}",
            json={"id": webhook_id},
            status=200,
        )
        rsps.add(
            responses.DELETE,
            f"{API}/events/{EVENT_ID}/webhooks/{webhook_id}",
            json={"ok": True},
            status=200,
        )
        rsps.add(
            responses.GET,
            f"{API}/events/{EVENT_ID}/webhooks/{webhook_id}/runs",
            json=[],
            status=200,
        )
        client.list_guests(EVENT_ID)
        client.add_guest(EVENT_ID, email="guest@example.com", name="Guest")
        client.update_guest(EVENT_ID, guest_id, response_status="accepted")
        client.delete_guest(EVENT_ID, guest_id)
        client.list_webhooks(EVENT_ID, is_active=True)
        client.create_webhook(EVENT_ID, "https://example.com/hook", "POST")
        client.get_webhook(EVENT_ID, webhook_id)
        client.update_webhook(EVENT_ID, webhook_id, "https://example.com/hook", "POST", is_active=False)
        client.delete_webhook(EVENT_ID, webhook_id)
        client.list_webhook_runs(EVENT_ID, webhook_id)
        bodies = [_body(call.request) for call in rsps.calls]
        urls = [call.request.url for call in rsps.calls]
    assert bodies[1] == {"email": "guest@example.com", "name": "Guest"}
    assert bodies[5]["url"] == "https://example.com/hook"
    assert urls[4].endswith("is_active=true") or "is_active=True" in urls[4]


def test_instances_export_changes_and_event_feedback(client):
    ics = "BEGIN:VCALENDAR\r\nEND:VCALENDAR"
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(responses.GET, f"{API}/calendars/{CALENDAR_ID}/instances", json={"events": []}, status=200)
        rsps.add(responses.GET, f"{API}/calendars/loose-events/instances", json={"events": []}, status=200)
        rsps.add(
            responses.GET,
            f"{API}/calendars/{CALENDAR_ID}/export",
            body=ics,
            status=200,
            content_type="text/calendar",
        )
        rsps.add(responses.GET, f"{API}/refresh/changes", json={"changes": []}, status=200)
        rsps.add(
            responses.GET,
            f"{API}/refresh/calendars/{CALENDAR_ID}/changes",
            json={"changes": []},
            status=200,
        )
        rsps.add(responses.GET, f"{API}/events/feedback", json=[], status=200)
        rsps.add(responses.POST, f"{API}/events/feedback", json={"ok": True}, status=201)
        instances = client.get_calendar_instances(
            CALENDAR_ID, "2026-10-14T00:00:00Z", "2026-10-14T23:59:59Z"
        )
        client.get_loose_event_instances("2026-10-14T00:00:00Z", "2026-10-14T23:59:59Z")
        exported = client.export_calendar(CALENDAR_ID, "2026-10-14T00:00:00Z", "2026-10-14T23:59:59Z")
        client.get_changes("cursor-1")
        client.get_calendar_changes(CALENDAR_ID, "cursor-1")
        client.list_event_feedback(value=1)
        client.create_event_feedback(1, {"id": EVENT_ID}, message="Useful")
        urls = [call.request.url for call in rsps.calls]
        feedback = _body(rsps.calls[6].request)
    assert instances["events"] == []
    assert exported == ics
    assert "since=cursor-1" in urls[3]
    assert feedback["value"] == 1


def test_google_namespace(client):
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(responses.GET, f"{API}/google/accounts", json=[{"id": "g1"}], status=200)
        rsps.add(responses.DELETE, f"{API}/google/accounts/g1", json={"ok": True}, status=200)
        rsps.add(responses.GET, f"{API}/google/sync-health", json={"ok": True}, status=200)
        rsps.add(responses.GET, f"{API}/google/quarantine", json=[], status=200)
        rsps.add(responses.POST, f"{API}/google/quarantine/q1/resolve", json={"ok": True}, status=200)
        rsps.add(responses.GET, f"{API}/google/sync-status", json={"state": "done"}, status=200)
        accounts = client.google.accounts()
        client.google.delete_account("g1")
        client.google.sync_health(export_id="exp-1")
        client.google.quarantine(status="open", provider="google")
        client.google.resolve_quarantine("q1", "accept")
        status = client.google.sync_status("job-1")
        urls = [call.request.url for call in rsps.calls]
    assert accounts[0]["id"] == "g1"
    assert status["state"] == "done"
    assert "export_id=exp-1" in urls[2]
    assert "resolution=accept" in urls[4]
    assert "job_id=job-1" in urls[5]


def test_caldav_namespace_routes(client):
    account_id = "acc-1"
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(responses.GET, f"{API}/caldav/capabilities", json={"ok": True}, status=200)
        rsps.add(responses.POST, f"{API}/caldav/discover", json={"calendars": []}, status=200)
        rsps.add(responses.POST, f"{API}/caldav/accounts/test", json={"ok": True}, status=200)
        rsps.add(responses.GET, f"{API}/caldav/accounts", json=[], status=200)
        rsps.add(responses.POST, f"{API}/caldav/accounts", json={"id": account_id}, status=201)
        rsps.add(responses.GET, f"{API}/caldav/accounts/{account_id}", json={"id": account_id}, status=200)
        rsps.add(responses.PATCH, f"{API}/caldav/accounts/{account_id}", json={"id": account_id}, status=200)
        rsps.add(
            responses.POST,
            f"{API}/caldav/accounts/{account_id}/calendars/refresh",
            json={"ok": True},
            status=200,
        )
        rsps.add(responses.POST, f"{API}/caldav/login-flow/start", json={"poll_token": "t"}, status=200)
        rsps.add(responses.POST, f"{API}/caldav/login-flow/poll", json={"done": False}, status=200)
        rsps.add(responses.GET, f"{API}/caldav/accounts/{account_id}/links", json=[], status=200)
        rsps.add(responses.POST, f"{API}/caldav/accounts/{account_id}/links", json={"ok": True}, status=201)
        rsps.add(
            responses.POST,
            f"{API}/caldav/accounts/{account_id}/destinations",
            json={"ok": True},
            status=201,
        )
        rsps.add(responses.POST, f"{API}/caldav/refresh", json={"ok": True}, status=200)
        rsps.add(responses.POST, f"{API}/caldav/links/link-1/remote-deleted", json={"ok": True}, status=200)
        rsps.add(responses.GET, f"{API}/caldav/sync-health", json={"ok": True}, status=200)
        rsps.add(responses.GET, f"{API}/caldav/quarantine", json=[], status=200)
        rsps.add(responses.POST, f"{API}/caldav/quarantine/q1/resolve", json={"ok": True}, status=200)
        rsps.add(responses.POST, f"{API}/caldav/accounts/{account_id}/push", json={"ok": True}, status=200)
        rsps.add(responses.POST, f"{API}/caldav/certificate", json={"pem": "cert"}, status=200)
        rsps.add(
            responses.GET,
            f"{API}/caldav/accounts/{account_id}/disconnect-preview",
            json={"events": 1},
            status=200,
        )
        rsps.add(
            responses.POST,
            f"{API}/caldav/accounts/{account_id}/reconnect",
            json={"ok": True},
            status=200,
        )
        rsps.add(
            responses.POST,
            f"{API}/caldav/accounts/{account_id}/disconnect",
            json={"ok": True},
            status=200,
        )
        caldav = client.caldav
        caldav.capabilities()
        caldav.discover("https://cal.example", "user", "pw", display_label="Home")
        caldav.test_connection("https://cal.example", "user", "pw")
        caldav.list_accounts()
        created = caldav.create_account("https://cal.example", "user", "pw")
        caldav.get_account(account_id)
        caldav.update_account(account_id, display_label="Home")
        caldav.refresh_calendars(account_id)
        caldav.start_login_flow("https://cal.example")
        caldav.poll_login_flow("https://cal.example/poll", "t")
        caldav.list_links(account_id)
        caldav.create_links(account_id, [{"href": "/cal"}])
        caldav.create_destination(account_id, CALENDAR_ID, display_name="Work")
        caldav.refresh()
        caldav.mark_remote_deleted("link-1", "keep")
        caldav.sync_health()
        caldav.quarantine(status="open")
        caldav.resolve_quarantine("q1", "discard")
        caldav.enable_push(account_id)
        caldav.fetch_certificate("https://cal.example")
        caldav.disconnect_preview(account_id)
        caldav.reconnect(account_id, "new-pw")
        caldav.disconnect(account_id, remove_imported=False)
        bodies = [_body(call.request) for call in rsps.calls]
        urls = [call.request.url for call in rsps.calls]
    assert created["id"] == account_id
    assert bodies[1]["display_label"] == "Home"
    assert bodies[14] == {"action": "keep"}
    assert "resolution=discard" in urls[17]


def test_caldav_auth_failed_does_not_refresh_session(client):
    body = load_fixture("error_caldav.json")
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(responses.GET, f"{API}/caldav/accounts", json=body, status=401)
        rsps.add(responses.GET, f"{API}/auth/token/extend", body='"refreshed-token"', status=200)
        with pytest.raises(Exception):
            client.caldav.list_accounts()
        extend_calls = [
            call for call in rsps.calls if call.request.url.rstrip("/").endswith("/auth/token/extend")
        ]
        assert extend_calls == []
