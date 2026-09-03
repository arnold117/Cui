# Cui 全流程(产品旅程图)— 文献探讨主线

> 2026-09-02 与 Arnold 对齐后的主流程梳理;实现映射到现有页面/端点;变更先改本文件再改代码。
> 一句话:对一个**新问题**,先**正向**(假设→关键词→找文献→覆盖梳理)把支持面建起来,再**反向**(固化 claim→对抗/文献发难→裁决)把它打薄,最后**收敛**(现状图景→gap→related-work/综述草稿)。

## 0. 出发点判断(新 UI 闸门)

进入「文献探讨」时,按工作区状态自动分型:

| 状态 | 判据(读工作区) | 引导 |
|---|---|---|
| **全新问题** | 无 claim、无已确认取证、无勾选料、无 gap | 提示"先找文献,再谈论断";给出候选**假设 + 关键词** |
| **有初步料** | 已勾选料/已有探索稿 | 从正向检索/梳理继续 |
| **已有裁决史** | 有 claim+裁决 | 可直接进入反向段(或开新一轮 claim) |

原则:判断是**提示不是锁**,任何状态都能手动跳到任意阶段(人说了算)。

## 1. 正向段:把支持面建起来(会话过程,不入轨迹)

1. **假设与关键词**(新端点,LLM):基于问题给 3–5 条 possible hypotheses + 8–12 条 possible keywords/短语(中英都行)→ 展示为 chips。
2. **正向检索**:关键词分批走语料检索(active),合并去重 → agent `literature-search` 从候选提炼 top-k + 每篇一句理由。
3. **你勾选 3–5 篇** → 进入精读范围。
4. **覆盖梳理**(现状梳理端点):"这几篇覆盖了什么 / 还没覆盖什么"——这就是支持面与缺口的第一次画像。
5. (可选)把 tentative 假设/方向写进**探索稿**(note 机制,可留档);不强制成 claim。

## 2. 反向段:对抗与裁决(入轨迹)

1. **固化 claim**(必须由你亲写;可从假设/探索稿长出来)→ 开审查轮,LLM 生成基础挑战。
2. **文献发难**:用勾选料追加文献挑战(`basis_refs`=locator,事件入库)。
3. 你**回答 → 裁决**(存活/证伪/不值一探/划界/有条件存活);可多轮、多 claim。裁决/挑战是轨迹事实。

## 3. 收敛段

1. **现状图景**:工作区读回 = 存活 claim + 已确认取证 + gap(含裁决史)。
2. **gap 收敛**:agent 起草(S20 形状:覆盖声明+可复现检索记录+反例邀请)→ **你改并署名提交 → 你确认**;confirmed gap 进轨迹。
3. **related-work 段草稿**(LLM,带 [locator] 引用)→ 复制/下载;outline→整篇导出(S24 模板已收编,接线待做)。
4. 后续把 confirmed gap / 方向固化到 direction(结晶自动化待第二批判例)。

## 铁律映射

- **会话过程不入库**:假设/关键词/勾选/梳理文本/草稿 = 会话(刷新可丢,UI 用 sessionStorage 缓);中途产物若想留 → 写入探索稿。
- **入库的只有定见**:claim 文本、挑战(含文献挑战)、回答/裁决、exploration note、confirmed/corrected/rejected gap、方向结晶。
- claim 永远人写;gap 永远人署名;agent 只起草与发难(S6)。

## 当前映射(2026-09-02 现状)

| 步骤 | 前端 | 后端 | 状态 |
|---|---|---|---|
| 出发点判断/假设+关键词 | DialogueDesk 新增闸门 | 新瞬态端点 orientation | 本文发布后实现 |
| 正向检索 top-k+理由(语料库 + **arXiv/OpenAlex 实时**) | DialogueDesk ①(候选带来源标签) | literature-search / corpus-search / external_search | ✅ |
| 勾选 | ① chips | —(会话) | ✅ |
| 覆盖梳理 | ② | landscape-summary | ✅ |
| 探索稿留档 | 工作区 note | save_note | ✅(既有) |
| claim+审查轮 | ③ | claims / review-rounds | ✅(既有) |
| 文献发难 | ③ 追加 | literature-challenges | ✅ |
| 回答/裁决 | ReviewRoundDesk | answers / verdicts | ✅(既有) |
| 现状图景 | LandscapePanel / ③ | workspace landscape | ✅ |
| gap 起草/确认 | ④ | gap-draft / gap-candidates | ✅ |
| related-work 草稿 | ⑤ | related-work-draft | ✅ |
| outline→整篇导出 | 未接 | exporters/templates 已归档 | 待收敛 |

## 打开顺序

问题工作区 → 现状图景与 gap →「与 Cui 一起读文献」→ 文献探讨页(按 §0–§3 走)。
