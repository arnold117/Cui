# 淬 · Cui

> **让严肃研究者持续经营一个会反过来质询自己的研究宇宙。**

An AI-native research environment. Cui starts from questions, not documents: users explore in problem workspaces, submit self-authored claims to adversarial examination, confirm evidence and conclusions, and let those traceable changes shape private research directions. Documents are downstream, externally-facing forms—not the center.

## v5 — LitScribe 融入升级(slice0 迁移完成,2026-09-02)

- **主名 Cui(淬);前身 = LitScribe(文献综述引擎,v4 归档于 `arnold117/LitScribe`,只读)**。一条产品线叙事:"Cui,前身 LitScribe,持续开发自 2026-01"。
- **架构**:kernel(事件+围栏+投影+守门,零 LLM/HTTP)+ SDK(python 接口规范 + REST thin adapter)+ host + 插件;层间由 import-linter 机器执法(`make lint-contracts`)。
- **本里程碑已落地**:包与 conda env rename anneal→cui;legacy v1 垂直归档 `cui/legacy_archive/`;v4 语料 **163 篇**入厂(native `material_added`,active/legacy 双语料 workspace,幂等);v4 纯逻辑 cherry-pick(ranking/pdf/exporters/templates/contradictions-diff)归档待 slice1 接线。
- **产物终点方向**:现状图景 → gap 清单 → 可行方向(综述文档只是导出形式);决策真相见 `docs/spec-v5-merge.md`(已收敛);执行记录见 `docs/plan-v5-slice0.md` §5–§11;新 session 启动包 `docs/v5-handoff.md`。
- **slice0 验收数字**:pytest **530 passed / 15 skipped**;canary L3 8/8、slice6 6/6 双绿;前端 vitest 66 + build;Playwright native 主路径 mock 冒烟 10 passed;importer 重跑幂等(0 新增)。

## Product authority

- [v5 merge spec(决策真相)](docs/spec-v5-merge.md)
- [v5 slice0 plan(任务清单与执行记录)](docs/plan-v5-slice0.md)
- [v4 corpus inventory(入厂盘点)](docs/v4-corpus-inventory.md)
- [Product requirements — Research Universe](docs/prd-research-universe.md)
- [Phase 1 specification — Minimal Research Universe](docs/spec-research-universe-mvp.md)
- [Phase 1 UX / interaction specification](docs/spec-research-universe-ux.md)
- [Phase 1 visual specification](docs/spec-research-universe-visual.md)
- [Phase 1 native rebuild implementation plan](docs/plan-research-universe-phase1.md)
- [Domain glossary](CONTEXT.md)
- [Pre-redesign specs (historical archive)](docs/archive/pre-research-universe/)

## Principles

- Automate evidence-gathering; never automate verdicts.
- Preserve evolution: questions, claims, conclusions, and directions may change, but never without provenance.
- Lens learns only from user-released, gated trajectories—not PARK or unconfirmed exploration.
- A survived claim passed a gate; it is not a truth certificate.

## Status

slice0(迁移里程碑)已完成:Native Research Universe 基线 + 语料库 163 篇 + 边界机器执法全绿。slice1 第一刀(gap 闭环)+ 第二刀后端与「文献探讨」模式页已就位。当前可用主路径:问题工作区 → 探索 → 自写 claim → 不可变审查轮(LLM 挑战)→ 证据候选三态闸 → 人裁决 → 现状图景/gap;「文献探讨」模式(问题 → agent 从语料挑文献并给理由 → 你勾选 → 现状梳理 → 文献发难 → gap → related-work 草稿);archive 只读保留旧轨迹。

## License

MIT
