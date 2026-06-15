# Implementation Plan: Trajectory Spine (P0)

> Derived from `docs/spec-trajectory-spine.md` (v0.1, 2026-06-14/15 grill sessions).
> Backend-only. 12 PRs, each independently reviewable. Python 3.11+, pytest, FastAPI.

---

## Repo layout

```
backend/
  pyproject.toml
  anneal/
    __init__.py
    domain/
      __init__.py
      models.py          # Pydantic domain models
      events.py          # Event types + verb table
      projections.py     # Pure functions: doc, lens_feed, versions, doc_projection
      invariants.py      # Business rules that must hold before writes
    store/
      __init__.py
      event_store.py     # EventStore protocol + InMemoryEventStore + SqliteEventStore
      repository.py      # Thin repo wrapping store (artifact CRUD, claim lookup)
    services/
      __init__.py
      event_service.py   # Confirm/retract/batch-confirm — cross-cutting human gate
      park_service.py    # PARK capture + isolation
      grill_service.py   # Challenge-answer-verdict loop
      promote_service.py # Survive → DOC promotion (debt gate)
      lens_feed_service.py  # Write grilled trajectory into Lens feed table
    api/
      __init__.py
      routes.py          # FastAPI endpoints
  tests/
    conftest.py
    test_models.py
    test_events.py
    test_event_store.py
    test_projections.py
    test_invariants.py
    test_event_service.py
    test_park_service.py
    test_grill_service.py
    test_promote_service.py
    test_lens_feed_service.py
    test_api.py
    test_acceptance.py   # End-to-end against spec §5
```

---

## Dependencies (pyproject.toml)

```toml
[project]
name = "anneal"
requires-python = ">=3.11"
dependencies = [
  "pydantic>=2",
  "fastapi",
  "uvicorn",
]

[project.optional-dependencies]
dev = [
  "pytest",
  "httpx",
  "pytest-asyncio",
]
```

---

## What is NOT in scope (spec §3.2)

- Lens learning/distillation algorithm.
- Cross-domain migration discovery.
- Project management UI.
- Grill intensity knob UX polish.
- Any bridge/adapter/converter from legacy structures.
- Library snapshot import/export + permission management.
- Frontend of any kind.
- `constrain`/`revise` event handling (constraint-aware rewriting).
- `paper`/`revision` artifact kinds (schema supports them; services do not implement them).
- Material kinds beyond `paper` (schema supports them; services do not implement them).
- Export feature (no export endpoint in first cut).

---

## PR #1 — Domain models (`anneal/domain/models.py`)

Define Pydantic models for all domain entities from spec §3.3.

```python
class Library:      # id, name, created_at
class Project:      # id, library_id, goal
class Conversation: # id, library_id, project_ids: list[str], created_at, updated_at
class Claim:        # id, library_id, body, artifact_ids: list[str], created_at, updated_at
class Material:     # id, library_id, kind: str, provenance: dict, payload: dict
class Artifact:     # id, library_id, kind: str, goal, constraints: list[dict],
                    #   project_ids: list[str], material_ids: list[str],
                    #   title, created_at, updated_at
```

**Key design decisions:**

- **`Artifact.kind` is `str`, not `Literal[...]`.** Spec §2.4 says "泛化抽象，不泛化实现" — the schema must be generic; only implementation is narrow. The model layer stores whatever string the caller passes. Validation that `kind` is one of the currently-supported set (`{"idea", "review"}`) belongs in the **service layer** (e.g. `park_service`, `grill_service`). This way adding `paper`/`revision` later does not touch the model definition.

- **`Material.kind` is `str`, not `Literal[...]`.** Same principle. The model accepts any kind string. Validation that `kind="paper"` (the only implemented kind) belongs in the **service layer**. Future kinds (`dataset`, `result`, `draft`, `figure`) slot in without model changes.

- `Claim.status` is NOT stored — it is a projection from events (spec §3.3 comment: "status 是投影，从 events 算，不存").

- `Conversation.project_ids` is `list[str]` (m:n schema), but first-cut services treat it as single-select.

**Tests (`test_models.py`):**
- Round-trip serialization for each model.
- `Artifact.kind` accepts arbitrary strings (e.g. `"paper"`, `"revision"`, `"idea"`).
- `Material.kind` accepts arbitrary strings.
- Default values and optional fields behave correctly.

---

## PR #2 — Event types (`anneal/domain/events.py`)

Define the Event model and the verb table from spec §3.3.

```python
class Event:
    id: str
    ts: datetime
    type: str           # One of the verb table values
    actor: str          # "user" | "system"
    strictness: int | None
    debt: bool          # bypass-produced events get debt=True
    confirmed: bool     # user confirmation gate
    target_ref: str | None
    payload: dict
```

Event type constants (matching spec verb table):

```python
PARK = "park"
COLLECT_MATERIAL = "collect_material"
ANALYZE_MATERIAL = "analyze_material"
CHALLENGE = "challenge"
ANSWER = "answer"
VERDICT = "verdict"           # payload.outcome: "survive" | "kill"
GAP = "gap"
DRAFT = "draft"               # default debt=True
CONSTRAIN = "constrain"
REVISE = "revise"
GROUND = "ground"
PROMOTE = "promote"
EDIT = "edit"                  # payload.scope: "surface" | "substance"
CONFIRM = "confirm"
RETRACT = "retract"
```

Helper: `make_event(type, actor, payload, debt=False, confirmed=False, ...) -> Event` factory with auto-generated `id` and `ts`.

**Tests (`test_events.py`):**
- `make_event` produces valid Event with correct defaults.
- `debt` defaults to False; `draft` events can be created with `debt=True`.
- Payload round-trips through serialization.

---

## PR #3 — Event store (`anneal/store/event_store.py`)

Protocol-based store with two implementations.

```python
class EventStore(Protocol):
    def append(self, artifact_id: str, event: Event) -> None: ...
    def get_events(self, artifact_id: str) -> list[Event]: ...
    def get_events_by_type(self, artifact_id: str, event_type: str) -> list[Event]: ...

class InMemoryEventStore:
    """Dict-backed. Used in tests."""

class SqliteEventStore:
    """SQLite-backed. Used in prod. Single table: (artifact_id, event_id, ts, data JSON)."""
```

Both implementations enforce append-only semantics (no update, no delete).

**Tests (`test_event_store.py`):**
- Parametrized over both `InMemoryEventStore` and `SqliteEventStore`.
- Append + retrieve preserves order.
- Multiple artifacts are isolated.
- `get_events_by_type` filters correctly.
- No mutation/deletion API exists.

---

## PR #4 — Projections (`anneal/domain/projections.py`)

Pure functions that derive views from event streams. No side effects, no state.

```python
def doc_projection(events: list[Event]) -> list[Event]:
    """Spec §3.3: doc = project(events: survive AND NOT debt AND confirmed).
    Returns filtered events suitable for DOC rendering.
    Retracted events are excluded."""

def lens_feed_projection(events: list[Event]) -> list[Event]:
    """Spec §3.3: lens_feed = project(events: grilled AND scope != "surface").
    Returns events suitable for Lens ingestion.
    Includes both survivors and killed ideas (killed = private asset, not garbage)."""

def snapshot_projection(events: list[Event]) -> list[dict]:
    """Reconstruct version snapshots from events."""

def claim_status(events: list[Event], claim_id: str) -> str:
    """Derive claim status from events: open / survived / killed / parked."""
```

**Important: Document is NOT a domain model.** Per spec §2.6 decision #1 ("文档不是独立一等状态，是 event stream 的投影"), Document has no separate Pydantic model and no independent storage. `doc_projection` returns a filtered `list[Event]` — the "document" is purely this projection. Any rendering (Markdown, PDF, etc.) is a downstream concern that consumes this event list. This is a deliberate architectural choice: the event stream is the single source of truth; Document is a view, not an entity.

**Tests (`test_projections.py`):**
- `doc_projection`: includes only survived + confirmed + no-debt events; excludes killed, unconfirmed, debt-bearing, and retracted events.
- `lens_feed_projection`: includes grilled events (challenge/answer/verdict), excludes `scope="surface"` edits; includes killed ideas (they are mining material for Lens).
- `snapshot_projection`: reconstructs incremental versions.
- `claim_status`: correctly derives status from event sequences.

---

## PR #5 — Invariants (`anneal/domain/invariants.py`)

Business rules checked before state transitions. These are pure functions that raise on violation.

```python
def assert_can_promote(events: list[Event], claim_id: str) -> None:
    """Spec §4 Q-D + §5 acceptance criterion 7.
    Raises if:
    - The claim has any events with debt=True that are not yet resolved (confirmed).
    - The claim has not survived grill (no verdict=survive event).
    Called by promote_service before writing a promote event."""

def assert_claim_no_debt(events: list[Event], claim_id: str) -> None:
    """Spec §4 Q-D: hard-block on referencing a claim that has unresolved debt.
    Raises if the claim has any events with debt=True that have not been
    subsequently confirmed.
    Called by any service when an artifact references (uses/cites) a claim —
    e.g. when a new artifact lists a claim_id in its references, or when
    a draft event cites a claim.

    Spec says THREE hard-block triggers: promote / export / referencing a
    debt-bearing claim. Promote is covered by assert_can_promote. Export is
    deferred (no export feature in first cut). This invariant covers the
    third trigger: reference-time debt blocking."""

def assert_park_isolation(events: list[Event]) -> None:
    """Ensures parked items have not been fed to Lens or promoted.
    PARK = sealed isolation zone; the only path to the moat is through GRILL."""
```

**Tests (`test_invariants.py`):**
- `assert_can_promote` raises on debt-bearing claim; passes after debt is cleared.
- `assert_can_promote` raises on claim without survive verdict.
- `assert_claim_no_debt` raises when referencing a claim with unresolved debt; passes after confirmation.
- `assert_claim_no_debt` correctly identifies debt resolved by a subsequent `confirm` event.
- `assert_park_isolation` raises if a parked-only item has promote or lens_feed events.

---

## PR #6 — Event service (`anneal/services/event_service.py`)

Cross-cutting meta-operations for the human confirmation gate. Confirm, retract, and batch-confirm are needed by ALL domain flows (grill confirmation, edit batch confirmation, debt clearance), so they live in a shared service rather than inside any single domain service.

```python
class EventService:
    def __init__(self, store: EventStore): ...

    def append_event(self, artifact_id: str, event: Event) -> Event:
        """Append an event. If confirmed=False, event is pending user confirmation."""

    def confirm_event(self, artifact_id: str, event_id: str) -> Event:
        """User confirms a pending event. Appends 'confirm' event targeting event_id.
        Used across all flows: grill confirmation, edit scope review, debt clearance."""

    def retract_event(self, artifact_id: str, event_id: str) -> Event:
        """User rejects an event. Appends 'retract' event (追加否定，不删历史)."""

    def batch_confirm(self, artifact_id: str, event_ids: list[str]) -> list[Event]:
        """Batch confirmation for edit flow (spec §2.6 decision #5).
        User clicks '完成编辑', reviews all pending edit events' scope at once."""

    def pending_events(self, artifact_id: str) -> list[Event]:
        """List events awaiting user confirmation."""
```

**Tests (`test_event_service.py`):**
- Single confirm: confirming a pending event appends a `confirm` event targeting the original event_id.
- Batch confirm: batch_confirm appends one `confirm` event per event_id; all previously pending events are no longer in `pending_events`.
- Retract: retracting an event appends a `retract` event; retracted events are excluded from `pending_events`.
- Pending list: `pending_events` returns only events with `confirmed=False` that have no corresponding `confirm` or `retract` event.

---

## PR #7 — Park service (`anneal/services/park_service.py`)

Captures inspiration into the sealed isolation zone.

```python
class ParkService:
    def __init__(self, store: EventStore): ...

    def park(self, library_id: str, body: str, kind: str = "idea") -> Artifact:
        """Create a new Artifact and append a 'park' event.
        Validates kind is in SUPPORTED_KINDS = {"idea", "review"}.
        The artifact starts ungrilled in PARK isolation."""

    def list_parked(self, library_id: str) -> list[Artifact]:
        """Return all artifacts whose only event is 'park' (still in isolation)."""
```

**Service-layer kind validation:** `park` validates that `kind` is in the currently-supported set `{"idea", "review"}`. The `Artifact` model itself accepts any string (see PR #1). When `paper`/`revision` are implemented, only this service constant needs updating.

**Material kind validation pattern (same principle):** Any service that handles materials validates `kind="paper"` at the service boundary. The `Material` model itself accepts any string.

**Tests (`test_park_service.py`):**
- Park creates artifact with a single `park` event.
- Parked artifact is retrievable and isolated.
- `list_parked` returns only ungrilled artifacts.
- Parking with unsupported kind (e.g. `"paper"`) raises a validation error at the service layer.
- Parking with `kind="idea"` and `kind="review"` both succeed.

**Acceptance (spec §5 line 1):** "能 park 一个灵感，它存在隔离区、标 `ungrilled`、查询学习料时查不到它。"

---

## PR #8 — Grill service (`anneal/services/grill_service.py`)

The adversarial questioning loop. Implements PARK → GRILL transition and the challenge-answer-verdict cycle. Uses `EventService` for event confirmation after grill rounds.

```python
class GrillService:
    def __init__(self, store: EventStore, event_service: EventService): ...

    def start_grill(self, artifact_id: str) -> Event:
        """Transition artifact from PARK to GRILL.
        从零开始拷问，无偷渡 — starts fresh, no smuggling of ungrilled content.
        Validates artifact kind is in SUPPORTED_KINDS at service layer."""

    def challenge(self, artifact_id: str, question: str) -> Event:
        """System poses a challenge. Appends 'challenge' event."""

    def answer(self, artifact_id: str, response: str) -> Event:
        """User/system answers. Appends 'answer' event."""

    def verdict(self, artifact_id: str, claim_id: str, outcome: str) -> Event:
        """outcome = 'survive' | 'kill'. Appends 'verdict' event.
        Killed ideas permanently remain in trajectory (mining material)."""

    def bypass(self, artifact_id: str, claim_id: str) -> Event:
        """Skip grill for a claim, but mark debt=True.
        The claim gets a verdict=survive event with debt=True.
        Debt must be repaid before promote/export/reference."""
```

**Tests (`test_grill_service.py`):**
- Full cycle: start_grill → challenge → answer → verdict(survive).
- Full cycle with kill: verdict(kill) event persists in trajectory.
- Bypass creates event with `debt=True`.
- Cannot grill an artifact that was never parked.
- Grill start_grill validates artifact kind at service layer.

**Acceptance (spec §5 lines 2-3):**
- "能把这条 park 拉进拷问场，经历至少一轮 challenge→answer→verdict。"
- "拷问中产生至少一个被 kill 的想法，它永久留在 trajectory 里、可回放。"

---

## PR #9 — Promote service (`anneal/services/promote_service.py`)

Moves survived claims from GRILL into DOC projection. Uses `EventService` for debt clearance (confirm/retract); does NOT own confirm_event itself.

```python
class PromoteService:
    def __init__(self, store: EventStore, event_service: EventService): ...

    def promote(self, artifact_id: str, claim_id: str) -> Event:
        """Promote a survived claim into DOC.
        Calls assert_can_promote (debt gate + survival check).
        Appends 'promote' event."""

    def reference_claim(self, artifact_id: str, claim_id: str) -> None:
        """Called when an artifact references/cites a claim.
        Calls assert_claim_no_debt — hard-blocks if the claim carries
        unresolved debt. This enforces spec §4 Q-D reference-time blocking."""
```

**Tests (`test_promote_service.py`):**
- Promote succeeds for survived, confirmed, no-debt claim.
- Promote raises on debt-bearing claim (spec §5 line 7).
- Promote raises on claim without survive verdict.
- Promote succeeds after debt is cleared via `EventService.confirm_event`.
- `reference_claim` raises on debt-bearing claim.
- `reference_claim` succeeds on clean claim.
- DOC projection after promote contains only clean content.

**Acceptance (spec §5 lines 4, 7):**
- "幸存者能 promote 进 DOC，DOC 里不含任何 ungrilled / killed 内容。"
- "尝试 promote 一个带 `debt=true` 的 claim，系统硬拦不让过；还清 debt 后才能 promote。"

---

## PR #10 — Lens feed service (`anneal/services/lens_feed_service.py`)

Writes grilled trajectory into the Lens feed table (empty-table hook — no learning algorithm).

```python
class LensFeedService:
    def __init__(self, store: EventStore): ...

    def feed(self, artifact_id: str) -> list[Event]:
        """Compute lens_feed_projection for the artifact's events.
        Write result to lens_feed table (first cut: just persist the list).
        Includes both survived AND killed ideas (both are Lens food).
        Excludes PARK-only items (assert_park_isolation).
        Excludes surface-scope edits."""

    def query_feed(self, library_id: str) -> list[Event]:
        """Return all Lens feed entries for a library.
        Parked-only items must NOT appear here."""
```

**Tests (`test_lens_feed_service.py`):**
- Feed includes grilled trajectory (challenge/answer/verdict events).
- Feed includes killed ideas (they are private mining assets, spec §2.2).
- Feed excludes PARK-only items (spec §2.5: Lens never eats PARK).
- Feed excludes `scope="surface"` edits (spec §2.6 decision 4).
- `query_feed` returns nothing for items still in PARK.

**Acceptance (spec §5 line 5):** "这条完整 trajectory 能被写入 Lens 投喂点（哪怕下游只是落库、不学习）。"

---

## PR #11 — FastAPI endpoints (`anneal/api/routes.py`)

Thin HTTP layer delegating to services. No business logic in routes.

```python
# Park
POST   /api/v1/park                    # Park a new inspiration
GET    /api/v1/park?library_id=...     # List parked items

# Grill
POST   /api/v1/grill/{artifact_id}/start
POST   /api/v1/grill/{artifact_id}/challenge
POST   /api/v1/grill/{artifact_id}/answer
POST   /api/v1/grill/{artifact_id}/verdict

# Promote
POST   /api/v1/promote/{artifact_id}/{claim_id}

# Events (cross-cutting confirmation gate — EventService)
POST   /api/v1/events/{artifact_id}/confirm        # single confirm
POST   /api/v1/events/{artifact_id}/batch-confirm   # batch confirm (edit flow)
POST   /api/v1/events/{artifact_id}/retract          # retract
GET    /api/v1/events/{artifact_id}/pending          # list pending

# Projections (read-only)
GET    /api/v1/artifact/{artifact_id}/doc        # doc_projection
GET    /api/v1/artifact/{artifact_id}/trajectory  # full event stream
GET    /api/v1/artifact/{artifact_id}/lens-feed   # lens_feed_projection

# Lens feed
GET    /api/v1/lens-feed?library_id=...
POST   /api/v1/lens-feed/{artifact_id}           # trigger feed write
```

**Tests (`test_api.py`):**
- Each endpoint returns correct status codes.
- Error cases (promote with debt, grill unparked item) return 4xx with meaningful messages.
- Uses `httpx.AsyncClient` + `InMemoryEventStore` for fast test execution.

---

## PR #12 — Acceptance tests (`tests/test_acceptance.py`)

End-to-end tests mapping 1:1 to spec §5 acceptance criteria. Each test walks the full flow through services (not HTTP — these test domain logic end-to-end).

```python
def test_park_isolation():
    """§5.1: Park a灵感, it's in isolation, marked ungrilled,
    not visible in Lens feed queries."""

def test_park_to_grill_cycle():
    """§5.2: Pull parked item into grill, complete at least one
    challenge→answer→verdict round."""

def test_killed_idea_persists():
    """§5.3: During grill, at least one idea is killed.
    It permanently remains in trajectory and is replayable."""

def test_promote_clean_doc():
    """§5.4: Survivor promotes to DOC. DOC contains no ungrilled/killed content."""

def test_lens_feed_write():
    """§5.5: Complete trajectory is written to Lens feed point
    (even if downstream just persists, no learning)."""

def test_unified_schema():
    """§5.6: Both idea and review flows use the same trajectory schema
    (proof of unified verbs)."""

def test_debt_blocks_promote():
    """§5.7: Attempting to promote a debt=True claim is hard-blocked.
    Clearing debt allows promotion."""

def test_debt_blocks_reference():
    """§4 Q-D (reference trigger): Attempting to reference a claim with
    unresolved debt is hard-blocked. This is the third hard-block trigger
    beyond promote and export."""
```

---

## Cross-cutting notes

1. **Model vs service validation boundary.** `Artifact.kind` and `Material.kind` are `str` at the model layer. Services validate against the currently-supported set. This is spec §2.4: "泛化抽象，不泛化实现" — schema is generic, implementation is narrow. When new kinds are implemented, only service-layer constants change; the model and store are untouched.

2. **Document is a projection, not an entity.** There is no `Document` Pydantic model. `doc_projection(events) -> list[Event]` is the document. Per spec §2.6 decision #1: "文档不是独立一等状态，是 event stream 的投影." Any code that needs "the document" calls this projection function. This keeps the event stream as the single source of truth with no dual-state conflicts.

3. **EventService is a shared dependency.** Confirm, retract, and batch-confirm are cross-cutting meta-operations (the "human gate") needed by all domain flows — grill confirmation, edit batch confirmation, debt clearance. They live in `EventService` (PR #6), not inside any single domain service. All domain services (`ParkService`, `GrillService`, `PromoteService`) depend on `EventService` for event writes and confirmation. Dependency ordering: EventStore → EventService → domain services.

4. **Three debt hard-block triggers (spec §4 Q-D):**
   - **Promote** — `assert_can_promote` in `invariants.py`, enforced by `promote_service`.
   - **Export** — deferred (no export feature in first cut).
   - **Reference** — `assert_claim_no_debt` in `invariants.py`, enforced by `promote_service.reference_claim` and any service that allows an artifact to cite a claim.

5. **Killed ideas are assets, not garbage.** They permanently live in the trajectory and are included in `lens_feed_projection`. Spec §2.2: "别人抄不走的不是幸存结论（公共知识），是阵亡想法（用你的失败史训练出的私有资产）."

6. **Append-only, immutable events.** No event is ever mutated or deleted. `retract` appends a new negation event. Projections filter out retracted events.

7. **Test strategy.** `InMemoryEventStore` for unit/integration tests (fast, no I/O). `SqliteEventStore` for store-level parametrized tests. Acceptance tests use services directly (not HTTP) to test domain logic end-to-end.
