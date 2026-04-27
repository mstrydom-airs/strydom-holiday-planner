"""Smoke tests — verify the app boots and the home page responds.

These are intentionally minimal so the test suite is green from day one.
Replace and grow them as features land. Each new test should reference a
``TEST-`` need (see ``docs/tests/index.rst``) and the ``REQ-`` it covers.
"""

from __future__ import annotations

import pytest


@pytest.mark.smoke
def test_home_page_returns_200(flask_client) -> None:  # type: ignore[no-untyped-def]
    """The home page should load successfully.

    Needs: REQ-001, TEST-001
    """

    response = flask_client.get("/")
    assert response.status_code == 200
