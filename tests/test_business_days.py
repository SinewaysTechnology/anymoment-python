"""Business-day rules from the live OpenAPI schedule models."""

import json

import pytest
import responses
from click.testing import CliRunner

from anymoment.business import preview_occurrences
from anymoment.cli.commands import cli
from anymoment.client import Client
from anymoment.schedule import ScheduleError, build_scheduled_event

from tests.support import API, EVENT_ID


def test_last_business_day_spain_matches_holiday_calendar():
    preview = preview_occurrences(
        "last",
        start="2026-01-01",
        end="2026-06-30",
        timezone="Europe/Madrid",
        at="09:00",
        country="ES",
    )
    assert preview["label"] == "last business day of the month"
    assert preview["country"] == "ES"
    assert [(row["date"], row["utc_start"]) for row in preview["occurrences"]] == [
        ("2026-01-30", "2026-01-30T08:00:00Z"),
        ("2026-02-27", "2026-02-27T08:00:00Z"),
        ("2026-03-31", "2026-03-31T07:00:00Z"),
        ("2026-04-30", "2026-04-30T07:00:00Z"),
        ("2026-05-29", "2026-05-29T07:00:00Z"),
        ("2026-06-30", "2026-06-30T07:00:00Z"),
    ]


def test_nth_from_end_matches_last_and_madrid_moves_may():
    last = preview_occurrences(
        "last",
        start="2027-05-01",
        end="2027-05-31",
        country="ES",
        timezone="Europe/Madrid",
    )
    nth = preview_occurrences(
        "nth",
        start="2027-05-01",
        end="2027-05-31",
        country="ES",
        timezone="Europe/Madrid",
        nth=1,
        from_end=True,
    )
    assert [row["date"] for row in last["occurrences"]] == [row["date"] for row in nth["occurrences"]]
    national = preview_occurrences(
        "first",
        start="2027-05-01",
        end="2027-05-31",
        country="ES",
        timezone="Europe/Madrid",
    )
    madrid = preview_occurrences(
        "first",
        start="2027-05-01",
        end="2027-05-31",
        country="ES",
        subdiv="MD",
        timezone="Europe/Madrid",
    )
    assert national["occurrences"][0]["date"] == "2027-05-03"
    assert madrid["occurrences"][0]["date"] == "2027-05-04"
    assert madrid["subdiv"] == "MD"


def test_roll_weekends_closures_and_extra_workdays():
    forward = preview_occurrences(
        "day",
        start="2026-12-01",
        end="2026-12-31",
        day=25,
        roll="forward",
        country="ES",
        timezone="Europe/Madrid",
        at="09:00",
    )
    backward = preview_occurrences(
        "day",
        start="2026-12-01",
        end="2026-12-31",
        day=25,
        roll="backward",
        country="ES",
        timezone="UTC",
    )
    assert forward["occurrences"][0]["date"] == "2026-12-28"
    assert forward["occurrences"][0]["utc_start"] == "2026-12-28T08:00:00Z"
    assert backward["occurrences"][0]["date"] == "2026-12-24"
    weekend = preview_occurrences(
        "last",
        start="2026-01-01",
        end="2026-01-31",
        weekend_days="4,5",
        timezone="UTC",
    )
    assert weekend["weekend_days"] == [4, 5]
    assert weekend["occurrences"][0]["date"] == "2026-01-29"
    closed = preview_occurrences(
        "last",
        start="2026-03-01",
        end="2026-03-31",
        closures=["2026-03-31"],
        timezone="UTC",
    )
    assert closed["occurrences"][0]["date"] == "2026-03-30"
    worked = preview_occurrences(
        "last",
        start="2026-01-01",
        end="2026-01-31",
        extra_workdays=["2026-01-31"],
        timezone="UTC",
    )
    assert worked["occurrences"][0]["date"] == "2026-01-31"


def test_post_events_body_matches_openapi_business_calendar():
    body = build_scheduled_event(
        title="Month-end close",
        start="2026-01-30T09:00:00",
        timezone="Europe/Madrid",
        monthly="last",
        country="ES",
    )
    assert body["name"] == "Month-end close"
    assert "roll" not in body
    assert body["business_calendar"] == {"country": "ES"}
    event = body["components"][0]["event_config"]
    assert event["recurrence"] == 2
    assert event["timezone"] == "Europe/Madrid"
    assert event["start_time"] == "09:00"
    assert event["config"]["type"] == "last_business_day"
    assert event["config"]["interval"] == 1
    assert "n" not in event["config"]

    nth = build_scheduled_event(
        title="Third from the end",
        start="2026-01-01T09:00:00",
        timezone="Asia/Jerusalem",
        monthly="nth",
        nth=3,
        from_end=True,
        country="IL",
        weekend_days=[4, 5],
        roll="backward",
        closures=["2026-12-24"],
        extra_workdays=["2026-12-26"],
    )
    assert nth["roll"] == "backward"
    assert nth["business_calendar"]["country"] == "IL"
    assert nth["business_calendar"]["weekend_days"] == [4, 5]
    assert nth["business_calendar"]["closures"] == ["2026-12-24"]
    assert nth["business_calendar"]["extra_workdays"] == ["2026-12-26"]
    config = nth["components"][0]["event_config"]["config"]
    assert config["type"] == "nth_business_day"
    assert config["n"] == 3
    assert config["from_end"] is True


def test_rrule_and_business_day_cannot_both_be_set():
    with pytest.raises(ScheduleError):
        build_scheduled_event(
            title="Both",
            start="2026-01-01T09:00:00",
            rrule="FREQ=MONTHLY;BYMONTHDAY=1",
            monthly="last",
        )


def test_create_event_sends_roll_and_calendar(mock_token_file):
    client = Client(api_url=API, token="test-token")
    with responses.RequestsMock(assert_all_requests_are_fired=True) as rsps:
        rsps.add(responses.POST, f"{API}/events", json={"id": EVENT_ID, "name": "Month-end"}, status=201)
        client.create_scheduled_event(
            title="Month-end",
            start="2026-01-30T09:00:00",
            timezone="Europe/Madrid",
            monthly="last",
            country="ES",
            roll="none",
        )
        sent = json.loads(rsps.calls[0].request.body)
    assert sent["business_calendar"] == {"country": "ES"}
    assert sent["components"][0]["event_config"]["config"]["type"] == "last_business_day"
    assert "roll" not in sent
    with responses.RequestsMock(assert_all_requests_are_fired=True) as rsps:
        rsps.add(responses.POST, f"{API}/events", json={"id": EVENT_ID, "name": "Skip"}, status=201)
        client.create_event(
            "Skip Friday",
            [{"operator": "OR", "event_config": {"recurrence": 2}}],
            roll="skip",
            business_calendar={"country": "ES", "weekend_days": [5, 6], "subdiv": "MD"},
        )
        direct = json.loads(rsps.calls[0].request.body)
    assert direct["roll"] == "skip"
    assert direct["business_calendar"] == {
        "country": "ES",
        "weekend_days": [5, 6],
        "subdiv": "MD",
    }


def test_instances_query_is_start_and_end(mock_token_file, monkeypatch):
    monkeypatch.setenv("ANYMOMENT_TOKEN", "test-token")
    client = Client(api_url=API, token="test-token")
    with responses.RequestsMock(assert_all_requests_are_fired=True) as rsps:
        rsps.add(responses.GET, f"{API}/events/{EVENT_ID}/instances", json=[], status=200)
        client.get_event_instances(EVENT_ID, from_date="2026-01-01", to_date="2026-06-30")
        query = rsps.calls[0].request.url.split("?", 1)[1]
    assert "start=2026-01-01" in query
    assert "end=2026-06-30" in query
    assert "from=" not in query
    assert "to=" not in query
    runner = CliRunner()
    with responses.RequestsMock(assert_all_requests_are_fired=True) as rsps:
        rsps.add(responses.GET, f"{API}/events/{EVENT_ID}/instances", json=[], status=200)
        result = runner.invoke(
            cli,
            [
                "events",
                "instances",
                EVENT_ID,
                "--from",
                "2026-01-01",
                "--to",
                "2026-06-30",
                "--host",
                API,
                "--json",
            ],
        )
        query = rsps.calls[0].request.url.split("?", 1)[1]
    assert result.exit_code == 0, result.output
    assert "start=2026-01-01" in query
    assert "end=2026-06-30" in query


def test_cli_add_sends_roll_and_business_calendar(mock_token_file, monkeypatch):
    monkeypatch.setenv("ANYMOMENT_TOKEN", "test-token")
    with responses.RequestsMock(assert_all_requests_are_fired=True) as rsps:
        rsps.add(
            responses.POST,
            f"{API}/events",
            json={"id": EVENT_ID, "name": "Month-end"},
            status=201,
        )
        result = CliRunner().invoke(
            cli,
            [
                "events",
                "add",
                "--title",
                "Month-end",
                "--start",
                "2026-01-30T09:00:00",
                "--timezone",
                "Europe/Madrid",
                "--business-day",
                "last",
                "--country",
                "ES",
                "--subdiv",
                "MD",
                "--roll",
                "forward",
                "--weekend",
                "5,6",
                "--closure",
                "2026-05-01",
                "--workday",
                "2026-01-31",
                "--host",
                API,
                "--json",
            ],
        )
        sent = json.loads(rsps.calls[0].request.body)
    assert result.exit_code == 0, result.output
    assert sent["roll"] == "forward"
    assert sent["business_calendar"] == {
        "country": "ES",
        "subdiv": "MD",
        "weekend_days": [5, 6],
        "closures": ["2026-05-01"],
        "extra_workdays": ["2026-01-31"],
    }
    assert sent["components"][0]["event_config"]["config"]["type"] == "last_business_day"


def test_cli_previews_spain_without_calling_the_api():
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "events",
            "business-days",
            "--rule",
            "last",
            "--country",
            "ES",
            "--timezone",
            "Europe/Madrid",
            "--time",
            "09:00",
            "--from",
            "2026-01-01",
            "--to",
            "2026-06-30",
        ],
    )
    assert result.exit_code == 0
    assert "last business day of the month, ES" in result.output
    assert "2026-01-30" in result.output
    assert "2026-05-29" in result.output
    assert "2026-01-30T08:00:00Z" in result.output
    assert "does not call the API" in result.output


def test_cli_help_mentions_business_days_and_occurrence_due():
    runner = CliRunner()
    events = runner.invoke(cli, ["events", "add", "--help"])
    preview = runner.invoke(cli, ["events", "business-days", "--help"])
    hooks = runner.invoke(cli, ["calendars", "subscriptions", "create", "--help"])
    assert events.exit_code == 0
    assert "--business-day" in events.output
    assert "--country" in events.output
    assert "--roll" in events.output
    assert preview.exit_code == 0
    assert "Spain" in preview.output
    assert hooks.exit_code == 0
    assert "occurrence.due" in hooks.output
