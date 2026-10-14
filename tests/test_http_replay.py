"""Replay vendored bodies through respx.

The SDK client uses requests, so behavioral tests mock with responses.
respx covers the httpx transport the same fixtures must survive.
"""

import httpx
import pytest

from tests.support import FIXTURES, load_fixture

JSON_FIXTURES = sorted(path.name for path in FIXTURES.glob("*.json"))


@pytest.mark.parametrize("name", JSON_FIXTURES)
def test_respx_replays_fixture(respx_mock, name):
    body = load_fixture(name)
    route = respx_mock.get("https://api.test.anymoment/fixture").mock(
        return_value=httpx.Response(200, json=body)
    )

    response = httpx.get("https://api.test.anymoment/fixture")

    assert route.called
    assert response.status_code == 200
    assert response.json() == body
