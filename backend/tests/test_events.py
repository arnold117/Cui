import uuid
from datetime import datetime

import pytest

from anneal.domain.events import (
    ALL_EVENT_TYPES,
    ANSWER,
    CHALLENGE,
    COLLECT_MATERIAL,
    CONFIRM,
    CONSTRAIN,
    DRAFT,
    EDIT,
    GAP,
    GROUND,
    ANALYZE_MATERIAL,
    PARK,
    PROMOTE,
    RETRACT,
    REVISE,
    VERDICT,
    Event,
    make_event,
)


class TestMakeEventDefaults:
    def test_correct_defaults(self):
        e = make_event(type=PARK, actor="user")
        assert e.type == PARK
        assert e.actor == "user"
        assert e.debt is False
        assert e.confirmed is False
        assert e.strictness is None
        assert e.target_ref is None
        assert e.payload == {}

    def test_auto_generated_id(self):
        e = make_event(type=PARK, actor="user")
        uuid.UUID(e.id)  # raises if not valid UUID

    def test_auto_generated_ts(self):
        before = datetime.utcnow()
        e = make_event(type=PARK, actor="system")
        after = datetime.utcnow()
        assert before <= e.ts <= after

    def test_two_events_get_distinct_ids(self):
        a = make_event(type=PARK, actor="user")
        b = make_event(type=PARK, actor="user")
        assert a.id != b.id


class TestEventImmutability:
    def test_cannot_set_attribute(self):
        e = make_event(type=PARK, actor="user")
        with pytest.raises(Exception):
            e.type = "challenge"

    def test_cannot_set_debt(self):
        e = make_event(type=PARK, actor="user")
        with pytest.raises(Exception):
            e.debt = True


class TestDraftDebt:
    def test_draft_with_debt(self):
        e = make_event(type=DRAFT, actor="system", debt=True)
        assert e.type == DRAFT
        assert e.debt is True

    def test_park_with_debt_false(self):
        e = make_event(type=PARK, actor="user", debt=False)
        assert e.debt is False


class TestPayloadRoundTrip:
    def test_round_trip_via_model_dump_and_validate(self):
        payload = {"key": "value", "nested": {"a": 1}}
        e = make_event(type=CHALLENGE, actor="system", payload=payload)
        data = e.model_dump()
        restored = Event.model_validate(data)
        assert restored == e
        assert restored.payload == payload

    def test_empty_payload_round_trip(self):
        e = make_event(type=PARK, actor="user")
        data = e.model_dump()
        restored = Event.model_validate(data)
        assert restored.payload == {}


class TestEventTypeConstants:
    def test_all_constants_are_strings(self):
        for t in ALL_EVENT_TYPES:
            assert isinstance(t, str)

    def test_all_event_types_count(self):
        assert len(ALL_EVENT_TYPES) == 16


class TestVerdictPayload:
    def test_verdict_survive(self):
        e = make_event(type=VERDICT, actor="system", payload={"outcome": "survive"})
        assert e.payload["outcome"] == "survive"

    def test_verdict_kill(self):
        e = make_event(type=VERDICT, actor="system", payload={"outcome": "kill"})
        assert e.payload["outcome"] == "kill"


class TestEditPayload:
    def test_edit_surface_scope(self):
        e = make_event(type=EDIT, actor="user", payload={"scope": "surface"})
        assert e.payload["scope"] == "surface"

    def test_edit_substance_scope(self):
        e = make_event(type=EDIT, actor="system", payload={"scope": "substance"})
        assert e.payload["scope"] == "substance"
