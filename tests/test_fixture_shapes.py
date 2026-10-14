"""Lock the vendored response shapes.

These tests do not call the SDK. They keep the fixtures aligned with the
public API: captured error bodies, the OpenAPI models, and the audited
shapes for fields the published schema leaves open (resend status codes,
sync warning items, CalDAV errors).
"""

from tests.support import (
    EXPORT_WARNING_KEYS,
    FAILURE_KEYS,
    SYNC_WARNING_KEYS,
    load_fixture,
)

EVENT_FIELDS = {
    "id",
    "name",
    "display_name",
    "is_active",
    "calendar_ids",
    "google_origin",
    "google_event_url",
    "external_origin",
    "sync_warnings",
    "guests",
    "conference_data",
}


def test_recorded_invalid_token_is_a_detail_string():
    body = load_fixture("recorded_invalid_token_401.json")
    assert body == {"detail": "Invalid token"}


def test_recorded_agenda_validation_error_is_a_detail_list():
    body = load_fixture("recorded_agenda_422.json")
    assert isinstance(body["detail"], list)
    assert body["detail"]
    for item in body["detail"]:
        assert {"loc", "msg", "type"} <= set(item)


def test_agenda_batch_shape():
    body = load_fixture("agenda_batch.json")
    assert set(body) == {"events", "failures"}
    assert len(body["events"]) == 2
    assert len(body["failures"]) == 1

    failure = body["failures"][0]
    assert set(failure) == FAILURE_KEYS
    assert failure["is_google_synced"] is True

    local_event = body["events"][0]["event"]
    imported = body["events"][1]["event"]
    assert EVENT_FIELDS <= set(local_event)
    assert local_event["google_origin"] is False
    assert set(local_event["sync_warnings"][0]) == SYNC_WARNING_KEYS
    assert imported["external_origin"]["read_only"] is True
    assert {"start", "end", "is_all_day"} <= set(body["events"][0]["instances"][0])


def test_caldav_error_shape():
    detail = load_fixture("error_caldav.json")["detail"]
    assert {"code", "message", "next_step"} <= set(detail)
    assert detail["code"] == "auth_failed"
    assert "calendar_name" in detail


def test_resend_verification_shapes():
    sent = load_fixture("resend_200_sent.json")
    already = load_fixture("resend_200_already_verified.json")
    limited = load_fixture("resend_429.json")
    failed = load_fixture("resend_502.json")

    assert sent == {"status": "sent"}
    assert already == {"status": "already_verified"}
    assert set(limited) == {"retry_after_seconds", "user_message"}
    assert isinstance(limited["retry_after_seconds"], int)
    assert set(failed) == {"user_message", "next_step"}
    assert "detail" not in limited
    assert "detail" not in failed


def test_mutation_warning_shapes():
    warning = load_fixture("sync_warning.json")
    event = load_fixture("event_with_sync_warnings.json")
    deleted = load_fixture("delete_event.json")
    unlinked = load_fixture("unlink_event.json")
    batch = load_fixture("batch_unlink.json")
    link = load_fixture("link_event.json")

    assert set(warning) == SYNC_WARNING_KEYS
    assert event["sync_warnings"][0]["next_step"] == warning["next_step"]
    assert set(deleted) == {"message", "sync_warnings"}
    assert set(unlinked) == {"message", "sync_warnings"}
    assert "sync_warnings" in batch
    assert set(link) == {"link", "google_export_warnings"}
    assert set(link["google_export_warnings"][0]) == EXPORT_WARNING_KEYS
    assert {"id", "calendar_id", "event_id", "added_at"} <= set(link["link"])


def test_unverified_login_body_is_plain_text():
    body = load_fixture("unverified_401.txt")
    assert isinstance(body, str)
    assert body.strip()
    assert not body.lstrip().startswith("{")
