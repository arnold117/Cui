"""Global test isolation.

WHY THIS EXISTS
---------------
``_init_state`` calls ``load_dotenv()`` before reading ``CUI_DATABASE_URL``
(it must — otherwise a ``.env``-supplied database URL is silently ignored and
every trajectory dies at restart). The direct consequence: from a developer's
machine the test suite would otherwise pick up ``backend/.env`` and run against
the REAL research database — writing test fixtures into the corpus the whole
product exists to protect.

So the suite unsets the variable for every test, always. Tests that want the
PostgreSQL path assert it explicitly (see ``TestEnvLoadOrder``) by patching
``deps.load_dotenv``; they never reach a real server. The Postgres integration
tests gate on their own opt-in variable (``CUI_TEST_DATABASE_URL``).

轨迹是护城河 — the test suite is never allowed near it.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _never_touch_the_real_database(monkeypatch):
    """Neutralise CUI_DATABASE_URL for every test (autouse, no opt-out).

    Set to "" rather than deleted: ``load_dotenv()`` would refill a MISSING
    variable straight out of ``backend/.env``, while an already-present one is
    left alone (dotenv does not override by default). Empty is falsy, so
    ``_init_state`` takes the in-memory branch — whatever the developer's
    ``.env`` happens to hold.
    """
    monkeypatch.setenv("CUI_DATABASE_URL", "")
