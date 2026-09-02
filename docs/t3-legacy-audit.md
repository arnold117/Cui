# T3 Legacy 审计与引用映射表(2026-09-02)

> 依 `docs/plan-v5-slice0.md` §T3:"先画使用映射表再删"。本文是审计产物(commit 随附),删除/移动决策均以本表引用关系为准。

## 0. 关键结构事实

- 生产/开发工厂 `create_app()` = `create_native_app()`——**v1 legacy API 从不挂生产**;`/api/v2` = native(slice0–6)+ `create_archive_router`(只读 archive)。`create_legacy_regression_app`(v1 全量)仅 test-only。
- **native(research_universe/domain/store/llm)对 legacy 面零 import**(grep 实测:services/lens/search 均无 native 调用方)。
- 12 张 legacy 表(schema.py:libraries/projects/conversations/claims/artifacts/materials/conversation_projects/claim_artifacts/artifact_projects/artifact_materials/events/lens_feed_entries):**冻结保留不 drop**(迁移链不断);`libraries` 表 native 在用(`_resolve_library_context`);archive 端点经 legacy PostgresRepository/EventStore 读旧表 → `cui/store/*` + `cui/domain/*` 保留。
- 前端路由(App.tsx):legacy 视图(ParkView/DocView/GrillView/CorpusGraphView/TrajectoryView/VersionsView/useGrillFlow)**零路由可达**(grep 无任何 import 方,GrillView↔useGrillFlow 互引除外);`/archive*` → LegacyArchive(活跃);`/artifact/:id` 重定向进 archive;`/park*` → ParkDesk(native RU);`/library/*/graph|/claim/*|/grill/*` → RetiredPath。

## 1. 面 → 引用方 → 判定

| 面 | 引用方(仅) | 判定 |
| --- | --- | --- |
| `/api/v1` legacy_router(`cui/api/routes.py`,30 端点:park/grill/artifact/claim/grounding/lens/events/doc/trajectory/lens-feed/evidence/versions) | test-only `create_legacy_regression_app` | **摘除**(整组删除;工厂同删) |
| `cui/api/deps.py`(legacy lifespan/DI/_state) | routes.py + regression app | **摘除**(随 v1) |
| `cui/services/*`(collect/event/grill/grounding/lens/lens_feed/park/promote) | 仅 v1 routes/deps + 服务互引 + canary_l3 | **移 `cui/legacy_archive/services/`**(lens_feed_service 除外 → **摘**,写-only 阑尾,空数据;canary/投影均不从其读) |
| `cui/lens/*`(precedent/prefilter/topic_terms) | 仅 lens_service/grill_service + canary_l3 | **移 `cui/legacy_archive/lens/`**(护城河算法归档保真,canary_l3 改指新路径,T7 双绿可续) |
| `cui/search/*`(arxiv/crossref/europepmc/openalex/pubmed/semantic_scholar/multi/dedupe) | 仅 legacy collect/grounding 链 | **移 `cui/legacy_archive/search/`** |
| `cui/domain/*`(events/models/projections/invariants/constants) | store/archive 端点 + legacy 服务 | **保留**(store 与 archive 仍用;lens_feed_projection 等阑尾投影随引用清理) |
| `cui/store/*`(repository/event_store/schema 等) | native app(`libraries`、archive router)+ legacy 链 | **保留**(只读 archive 活跃面) |
| `/api/v2/legacy-archive`(GET 3 端点) | FE `LegacyArchive`(`/archive*` 活跃路由) | **保留** |
| 前端 legacy 视图 6 个 + `useGrillFlow` | 无(死代码) | **删**(tsc/vitest 验证) |
| FE e2e:legacy 走查 spec(grill/park/evidence 旧流) | — | **删**;archive.spec(archive 面)、RU native spec(workspace/review/crystallization/evidence-gate/evidence-generation/first-fact/park-release.real)保留(后两者 real 需真库,按需跑) |
| legacy 测试(~20 文件:test_api/test_acceptance/test_{collect,event*,grill,grounding,lens*,park,promote,corpus_graph*,models,invariants,events,search*,dedupe,pubmed...}等) | 测已摘除面 | **删**(git 历史可查;数字下降属 plan 预期) |

## 2. 风险与裁决

- **GrillView native 引用面(plan ⚠️)**:实测零 import(forge 由 WorkspaceDesk 承担)→ 删,无残留面。
- **canary_l3 与 T7 双绿**:L3 算法随服务归档至 `cui.legacy_archive.*`;canary_l3 import 改指归档路径,继续作"归档 Lens 算法"回归哨兵,双绿保持。
- **lens_feed 阑尾**:`lens_feed_entries` 表冻结保留(12 表之一);服务与投影引用摘除。
- **corpus_graph / trajectory / versions / evidence 旧只读端点**:v1 摘除后旧记录走 archive 只读面。
- 前端 `/park` 仍是 ParkDesk(native RU 面)——不是 legacy ParkView,保留。

## 3. 执行顺序(commit 切分)

1. 本文(审计产物 commit)
2. 后端归档:git mv services/search/lens → legacy_archive/,子树内 import 改指;删 v1 routes/deps/regression 工厂;删 legacy 测试;pytest 全绿 + canary 双绿(canary_l3 import 改指)
3. 前端:删 6 视图 + useGrillFlow + 相关 e2e + 死引用;tsc/vitest/build 绿
4. 收尾:Playwright native 冒烟(如环境允许)、记录 commit
