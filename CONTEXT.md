# Anneal — 领域术语表 (Glossary)

> 只放术语定义，不放实现细节。实现决策见 `docs/spec-*.md` 与 `docs/adr/`。
> 产品方向/铁律见用户记忆 `project_direction.md`（灵魂文档）。

## 三区

- **PARK（灵感停车场）** — 零摩擦捕获、密封隔离的想法。不喂 Lens、不算进度。停过车 ≠ 学分。
- **GRILL（拷问场）** — 对抗式拷问的场所，全程录像成 trajectory。强度可调（调的是闸门时机，不是有没有闸门）。
- **DOC** — 只留 verified（survived、已确认、无 debt）内容的产出面。

## 核心对象

- **Claim** — 拷问与落定的最小单位。属 Library 层的**漂浮节点**，可被多个 Artifact 引用。`status`（open/survived/killed/parked）是从事件算出的**投影**，不存。
- **Artifact** — 写作产物（脊柱对象），kind 是开放集：idea/review/paper/revision…。其 `events[]` 事件流 = 唯一真相。
- **Trajectory（轨迹）** — 一条 Artifact 上的全部事件流：challenge/answer/verdict/ground… 幸存者与阵亡者都录。
- **Grilled trajectory（拷问过的轨迹）** — 经过 GRILL 闸门的 trajectory。**Lens 只吃这个，永不吃 PARK**（防投毒）。
- **Material** — 收集来的材料，kind=paper（已实现）等。grounding 的对象。

## Lens

- **Lens（学习制 Lens）** — 护城河本体。一个**学会并复用「你这个研究者怎么提炼文献 / 怎么辩护 claim」、跨领域可移植**的程序。learned 非 authored。作用域 = **Library 内穿透**（跨库硬墙）。
- **Lens 喂入（feed）** — grilled trajectory 进入 Lens 的投影点（`lens_feed_projection`）。已存在。
- **Lens 读出（read-out）** — 用积累的历史轨迹**影响当下 grill**。L3 起步；第一刀 = 跨想法矛盾检测。

## 铁律相关

- **取证（evidence-gathering）** — 翻出事实：找证据、找矛盾、监控、端反例。**可以自动化。**
- **定见（verdict / opinion）** — 裁决：claim 死活、rationale、为什么还做。**永不自动化**——必须人产出/确认。
- **铁律一句话**：自动化「取证」，永不自动化「定见」。grill 是闸门；闸门后的学习/辅助提炼被允许，但未经拷问的东西不许冒充已验证。
- **taste 打分红线** — 逻辑没做对前，不塞 LLM 给想法好坏的**绝对打分**。判断要锚在真实历史/真实 claim 上。

## 跨想法矛盾检测（P2 第一刀术语）

- **硬矛盾** — 当下 claim 断言 X、用户某旧 claim 断言 ¬X（逻辑冲突）。
- **重复** — 当下 claim 本质是用户已 killed/survived 过的同一想法。
- **软张力** — 不构成硬矛盾，但跨想法的模式（如「又一个 method-X 的 incremental 变体」）。必须以**取证形状**（事实模式 + 问题）呈现，永不打分。
- **取证形状 vs 打分形状** — 取证 = 摆出事实模式 + 把判断留给用户；打分 = 替用户裁决想法好坏（禁止）。
