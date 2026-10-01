"""刀2b 外部文献快照在真 PostgreSQL 上的原子性/复用/重放(_replay_commit 依赖同 commit 共享 commit_position);
requires CUI_TEST_DATABASE_URL(只在一次性 cui_slice2_* 库上跑)。"""
import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine

from cui.research_universe.application import Slice1Service
from cui.research_universe.store.event_store import CommandFingerprintConflict, PostgresNativeEventStore
from tests.pg_temp_db import drop_temporary_database, temporary_database_url
from tests.test_external_capture import EXT_A, EXT_B, _Gen, _captured

PG_URL = os.getenv("CUI_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not PG_URL, reason="No PG (set CUI_TEST_DATABASE_URL)")


@pytest.fixture()
def pg(monkeypatch):
    temp_url, database = temporary_database_url(PG_URL)
    monkeypatch.setenv("CUI_DATABASE_URL", temp_url)
    config = Config(str(Path(__file__).parents[1] / "alembic.ini")); config.set_main_option("sqlalchemy.url", temp_url)
    command.upgrade(config, "head")
    engine = create_engine(temp_url, pool_pre_ping=True)
    store = PostgresNativeEventStore(engine); universe = store.create_active_universe("capture-pg")
    service = Slice1Service(store, "local", _Gen())
    wid = service.create_workspace(universe, "w1", 0, "Why does RLHF help?").result_payload["workspace_id"]
    cid = service.create_claim(universe, wid, "c1", 0, "RLHF helps reasoning.").result_payload["claim_id"]
    rid = service.start_review_round(universe, cid, "r1", 0).result_payload["review_round_id"]
    yield store, universe, service, wid, rid
    engine.dispose(); drop_temporary_database(PG_URL, database)


def test_pg_capture_atomic_reuse_and_replay(pg):
    store, universe, service, wid, rid = pg
    first = service.generate_literature_challenge(universe, rid, [], "lit1", 0, externals=[EXT_A, EXT_B])
    assert sorted(m.source_locator for m in _captured(store, universe)) == sorted([EXT_A["locator"], EXT_B["locator"]])
    assert all(m.content_scope == "abstract" for m in _captured(store, universe))
    # 同 commit:容器 workspace + 2 material + challenge 共享一个 commit_position
    positions = {e.commit_position for e in store.read_events(universe) if e.id in first.event_ids}
    assert len(positions) == 1 and len(first.event_ids) == 4
    # 相同重试 → 幂等重放(即使快照已存在、本次不会再写)
    again = service.generate_literature_challenge(universe, rid, [], "lit1", 0, externals=[EXT_A, EXT_B])
    assert again.event_ids == first.event_ids
    # 换文献重试 → 指纹冲突
    with pytest.raises(CommandFingerprintConflict):
        service.generate_literature_challenge(universe, rid, [], "lit1", 0, externals=[EXT_A])
    # 别的命令引用同一篇 → 复用,不重复快照
    service.propose_gap_candidate(universe, wid, "现有文献覆盖对齐,未覆盖推理评测。", "rlhf", "active", [EXT_A["locator"]], "欢迎反例", None, "gap1", 0, externals=[EXT_A])
    assert len(_captured(store, universe)) == 2
