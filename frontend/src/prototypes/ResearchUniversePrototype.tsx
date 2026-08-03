/*
 * PROTOTYPE — Research Universe visual direction
 * Question: can a bright mineral research desk, modern-archive typography,
 * and a restrained cold-teal "quench" moment sustain long reading?
 * Variants switch through ?prototype=research-universe&variant=A|B|C.
 * Delete or rewrite after a design verdict; do not promote directly.
 */
import { useEffect, useState } from "react"

type Variant = "A" | "B" | "C" | "D"

const variants: { key: Variant; name: string; description: string }[] = [
  { key: "A", name: "阅读桌", description: "宽阅读稿 + 克制研究边缘" },
  { key: "B", name: "证据摊开", description: "材料与 claim 并列的证据台" },
  { key: "C", name: "方向地形", description: "命题为先的研究宇宙入口" },
  { key: "D", name: "密封到形成", description: "PARK 放行与用户自写 claim" },
]

const directions = [
  { title: "算法化分配如何改变教育资源的不平等，以及什么机制能抵消它。", state: "active", note: "原问题应收窄到 A 范围内", waiting: 1 },
  { title: "数字化评估如何重塑教师对学生的判断。", state: "watching", note: "暂时等待新的课堂观察", waiting: 0 },
]

function QuenchMark({ label = "已确认" }: { label?: string }) {
  return <span className="ru-quench">{label}</span>
}

function Topbar({ variant }: { variant: Variant }) {
  return (
    <header className="ru-topbar">
      <div className="ru-wordmark"><span>淬</span><b>Cui</b></div>
      <div className="ru-breadcrumb">研究宇宙 <i>/</i> 教育资源分配 <i>/</i> 问题试验场</div>
      <div className="ru-actions">
        <button className="ru-text-button">◇ 捕获</button>
        <button className="ru-primary">＋ 开始</button>
      </div>
      <span className="ru-prototype-label">PROTOTYPE · {variant}</span>
    </header>
  )
}

function Rail() {
  return (
    <aside className="ru-rail">
      <p className="ru-eyebrow">研究边缘</p>
      <section>
        <div className="ru-rail-heading"><span>待回应</span><b>2</b></div>
        <button className="ru-rail-item ru-contested"><strong>可能的反证</strong><small>Paper A · 与 Claim 1 对照</small></button>
        <button className="ru-rail-item"><strong>边界仍未说明</strong><small>Claim 1 · 一条 challenge</small></button>
      </section>
      <section>
        <div className="ru-rail-heading"><span>正在检验</span><b>2</b></div>
        <button className="ru-rail-item"><strong>算法匹配改变资源分配</strong><small>审查轮次 01 · 2 个挑战</small></button>
        <button className="ru-rail-item"><strong>透明机制能抵消伤害</strong><small>尚未提交检验</small></button>
      </section>
      <section>
        <div className="ru-rail-heading"><span>最近结晶</span></div>
        <div className="ru-rail-item ru-confirmed"><QuenchMark label="结晶" /><strong>原问题应收窄到 A 范围内</strong><small>昨天 · 用户确认</small></div>
      </section>
    </aside>
  )
}

function VariantA({ mode, onMode }: { mode: "reading" | "forge" | "grill" | "verdict"; onMode: (mode: "reading" | "forge" | "grill" | "verdict") => void }) {
  const forge = mode === "forge"
  const grill = mode === "grill"
  const verdict = mode === "verdict"
  return (
    <div className="ru-page ru-reading-page">
      <Topbar variant="A" />
      <div className="ru-question-spine">
        <span className="ru-spine-label">问题</span>
        <strong>为什么算法化分配会在某些学校扩大教育资源不平等？</strong>
        <span className="ru-status">探索中</span>
        <button>重述</button>
        <small>从「算法与不平等有关？」而来 · 查看问题来路</small>
      </div>
      <div className={`ru-reading-layout ${forge || grill || verdict ? "ru-has-focus" : ""}`}>
        <main className="ru-notebook">
          <div className="ru-surface-caption"><span>自由探索</span><em>未定探索 · 不进入 Lens</em></div>
          <article className="ru-prose" contentEditable suppressContentEditableWarning>
            <p>如果分配模型把过去的表现当作未来潜力，它也许并非只是在预测。它可能把已有的资源差异重新写进了学生的机会。</p>
            <p>我需要分清：模型是否<strong>制造</strong>了差异，还是只是让本来就存在的差异更可见。两者需要不同的证据。</p>
            <p className="ru-anchor">一个可能的断言：在资源稀缺且学校使用历史成绩作为主要输入时，算法匹配会使已有优势更容易累积。 <button onClick={() => onMode("forge")}>接受检验 →</button></p>
            <p>但“资源稀缺”到底意味着预算、师资，还是进入高阶课程的席位？如果这里没有边界，任何结果都会被我解释成支持。</p>
            <p>还需要找一个反例：有没有相同模型、却因补偿机制而缩小差异的学校？</p>
          </article>
          <footer className="ru-notebook-footer"><button>暂时放下</button><button className="ru-outline">确认这次探索的位置</button></footer>
        </main>
        <Rail />
        {forge && <aside className="ru-focus-pane"><p className="ru-eyebrow">锻 · 形成 claim</p><h2>让这段话成为你愿意检验的断言。</h2><p>你究竟在断言什么？</p><textarea defaultValue="在资源稀缺且历史成绩是主要输入时，算法匹配会使已有优势更容易累积。" /><p>它在哪些条件下不成立？</p><textarea placeholder="由你自己写下范围或反例……" /><footer><button onClick={() => onMode("reading")}>返回探索</button><button className="ru-dark-action" onClick={() => onMode("grill")}>确认提交检验</button></footer></aside>}
        {grill && <aside className="ru-focus-pane"><p className="ru-eyebrow">审查轮次 01</p><h2>先看审查地形。</h2><div className="ru-attack-list"><button className="is-active">替代解释是否被排除？</button><button>证据能否区分解释？</button><button>适用边界在哪里？</button></div><p>为什么先问替代解释？X 与 Y 同时出现，也可能都由 Z 导致。这不是预判死亡，而是这条 claim 必须越过的门槛。</p><textarea placeholder="我目前的回应……" /><footer><button onClick={() => onMode("reading")}>回到探索</button><button className="ru-dark-action" onClick={() => onMode("verdict")}>作出本轮裁决</button></footer></aside>}
        {verdict && <aside className="ru-focus-pane"><p className="ru-eyebrow">裁决台</p><h2>这是你的判断。</h2><div className="ru-ledger"><span>已回应 · 替代解释</span><span>仍待回应 · 证据门槛</span><span>带入但未确认 · Paper A</span></div><p>暂时站住了不是真理证书。Cui 不会替你决定结果。</p><div className="ru-verdict-choices"><button>暂时站住了</button><button>这条表述不成立</button><button>需要收窄／改写</button><button>现在先不投入</button></div><textarea placeholder="写下你的理由……" /><footer><button onClick={() => onMode("grill")}>回到审查</button><button className="ru-dark-action ru-confirm-local" onClick={() => onMode("reading")}>确认本轮裁决</button></footer></aside>}
      </div>
      <QuenchPulse />
    </div>
  )
}

function VariantB({ confirmed, onConfirm }: { confirmed: boolean; onConfirm: () => void }) {
  return (
    <div className="ru-page ru-evidence-page">
      <Topbar variant="B" />
      <div className="ru-evidence-header">
        <p className="ru-eyebrow">取证 · 当前审查轮次 01</p>
        <h1>材料不能只告诉你它“相关”。</h1>
        <p>让摘录、claim 与待确认判断同时留在桌面上。</p>
      </div>
      <main className="ru-evidence-board">
        <section className="ru-source-sheet">
          <div className="ru-sheet-meta"><span>材料摘录</span><small>Rodriguez et al. · 2024 · p. 12</small></div>
          <blockquote>“When prior achievement is used as the principal allocation feature, students with earlier access to enrichment are disproportionately routed into advanced tracks.”</blockquote>
          <p>来源定位已固定。你可以补充笔记，但不能替换这一份证据锚。</p>
          <div className="ru-source-facts"><span>研究对象：18 所公立学校</span><span>方法：准实验比较</span></div>
        </section>
        <section className="ru-claim-sheet">
          <div className="ru-sheet-meta"><span>对照 claim</span><small>本轮文本快照</small></div>
          <h2>算法匹配会在资源稀缺的学校扩大教育资源的不平等。</h2>
          <div className={`ru-candidate-label ${confirmed ? "ru-is-confirmed" : ""}`}>{confirmed ? "已确认的取证事实" : "Cui 的取证候选 · 未确认"}</div>
          <h3>{confirmed ? "已记录为反证" : "可能构成反证"}</h3>
          <p>这段研究显示的是历史成绩导致的路径依赖，但没有把“算法匹配”与人工分配直接比较；它可能削弱 claim 的机制表述，而不是整体结论。</p>
          <div className="ru-uncertainty">不确定性：研究对象与当前问题的资源稀缺定义并不相同。</div>
          {confirmed ? <div className="ru-local-receipt"><span className="ru-pulse-dot" />事实已落位：当前审查轮次与工作区取证层。<button onClick={onConfirm}>撤回演示</button></div> : <div className="ru-evidence-actions"><button className="ru-confirm-action" onClick={onConfirm}>确认是反证 <span>↗</span></button><button>改为支持</button><button>查无</button><button>拒绝</button></div>}
        </section>
      </main>
      <QuenchPulse evidence />
    </div>
  )
}

function VariantC() {
  const [focused, setFocused] = useState(false)
  return (
    <div className="ru-page ru-terrain-page">
      <Topbar variant="C" />
      <main className={`ru-terrain ${focused ? "ru-terrain-focused" : ""}`}>
        <div className="ru-terrain-intro"><p className="ru-eyebrow">研究宇宙</p><h1>不是待办清单。<br />是正在长出结构的研究。</h1><p>每一条方向先说明你在追什么；事实只在它实际影响的地方出现。</p></div>
        <section className="ru-direction-field">
          {directions.map((direction, index) => (
            <article key={direction.title} className={`ru-direction ${index === 0 ? "ru-direction-main" : ""} ${focused && index === 0 ? "is-focused" : ""} ${focused && index !== 0 ? "is-receded" : ""}`}>
              <header><span className="ru-direction-index">0{index + 1}</span><span className={`ru-direction-state ${direction.state}`}>{direction.state}</span></header>
              <button className="ru-direction-title" onClick={() => index === 0 && setFocused((value) => !value)}><h2>{direction.title}</h2></button>
              <p className="ru-direction-note">最近结晶 · {direction.note}</p>
              {direction.waiting > 0 && <button className="ru-terrain-fact"><span>●</span> 一条事实正在等待解释 <b>→</b></button>}
              {focused && index === 0 && <div className="ru-direction-viewport"><section><p className="ru-eyebrow">正在试验的问题</p><button>为什么算法化分配会在某些学校扩大资源不平等？ <b>待回应 1</b><span>探索中 · 2 条 claim</span></button><button>何种透明机制能真正改变分配结果？ <b>暂时放下</b><span>重看条件已记录</span></button></section><section><p className="ru-eyebrow">已确认的结晶</p><article><QuenchMark label="结晶" /><strong>原问题应收窄到 A 范围内，才能区分模型效应与既有差异。</strong></article><article><QuenchMark label="取证" /><strong>一段材料未涉及该 claim，不能作为反证。</strong></article></section><footer><button onClick={() => setFocused(false)}>收回地形</button><button>继续进入这条方向 <span>→</span></button></footer></div>}
              <button className="ru-enter" onClick={() => index === 0 && setFocused((value) => !value)}>{focused && index === 0 ? "收起视口" : "看这一条方向"} <span>{focused && index === 0 ? "↑" : "→"}</span></button>
            </article>
          ))}
          <article className={`ru-unplaced ${focused ? "is-receded" : ""}`}><span>未归属的探索</span><strong>为什么不同的透明机制产生相反结果？</strong><p>它可以先独立存在。</p><button>继续探索 →</button></article>
        </section>
      </main>
      <QuenchPulse />
    </div>
  )
}

function VariantD() {
  const [stage, setStage] = useState<"park" | "release" | "workspace" | "forge">("park")
  const [capture, setCapture] = useState("学生被模型分到不同课程之后，好像会越来越难回到同一条路。")
  const question = "什么时候，课程分配模型会把已有的教育差异变成更难逆转的路径？"

  return <div className="ru-page ru-park-page">
    <Topbar variant="D" />
    <main className="ru-park-main">
      {stage === "park" && <section className="ru-park-surface"><div className="ru-surface-caption"><span>◇ PARK · 密封捕获</span><em>未进入研究宇宙 · Cui 不会读取</em></div><p className="ru-eyebrow">尚未承诺的想法</p><h1>先记下。<br />不必现在解释。</h1><textarea value={capture} onChange={(event) => setCapture(event.target.value)} /><p className="ru-park-note"><span>◇</span>这条内容只留在 PARK。它不会被整理、关联、挑战，也不会进入 Lens。</p><footer><button className="ru-plain-action">继续留在 PARK</button><button className="ru-dark-action" onClick={() => setStage("release")}>主动放行 →</button></footer></section>}
      {stage === "release" && <section className="ru-release-surface"><div className="ru-surface-caption"><span>◇ PARK · 放行</span><em>原件仍密封保留</em></div><p className="ru-eyebrow">放行这个捕获</p><blockquote>“{capture}”</blockquote><div className="ru-release-fields"><label>我愿意让它：<select defaultValue="question"><option>触发一个新问题</option><option>带入已有问题，继续探索</option><option>作为待取证材料线索</option><option>暂不命名，只放入探索稿</option></select></label><label>放入：<select defaultValue="new"><option>新问题试验场</option><option>已有工作区</option></select></label></div><p className="ru-park-note"><span>◇</span><strong>密封原件会留在 PARK。</strong> Cui 只会在你指定的工作区中看见这次放行引用。</p><footer><button className="ru-plain-action" onClick={() => setStage("park")}>留在 PARK</button><button className="ru-dark-action" onClick={() => setStage("workspace")}>放行到问题试验场</button></footer></section>}
      {stage === "workspace" && <section className="ru-workspace-surface"><div className="ru-release-link"><button onClick={() => setStage("park")}>◇ PARK 原件</button><span>→ 放行引用</span></div><div className="ru-question-spine ru-d-question"><span className="ru-spine-label">问题</span><strong>{question}</strong><span className="ru-status">探索中</span></div><article className="ru-prose ru-d-prose"><p>如果模型把过去的表现当作未来潜力，它可能并不只是预测，而是在让先前获得的资源变成后续选择的门票。</p><p className="ru-anchor">我想弄清的是：<strong>在资源稀缺、且历史成绩是主要输入时，课程分配模型会使已有优势更难逆转。</strong> <button onClick={() => setStage("forge")}>接受检验 →</button></p><p>这里还需要界定“资源稀缺”究竟是什么；也需要知道，是否存在补偿机制让相同模型产生相反结果。</p></article><footer><button className="ru-plain-action">继续写</button><button className="ru-outline">确认这次探索的位置</button></footer></section>}
      {stage === "forge" && <section className="ru-d-forge"><article><div className="ru-release-link"><button onClick={() => setStage("park")}>◇ PARK 原件</button><span>→ 放行引用</span></div><p className="ru-eyebrow">原始探索片段</p><blockquote>“在资源稀缺、且历史成绩是主要输入时，课程分配模型会使已有优势更难逆转。”</blockquote><p>原件和探索稿不会被改写。你只是在决定是否亲自形成一条可检验的 claim。</p></article><aside className="ru-focus-pane"><p className="ru-eyebrow">锻 · 形成 claim</p><h2>让它成为可被检验的断言。</h2><p>你究竟在断言什么？</p><textarea defaultValue="在资源稀缺且历史成绩是主要输入时，课程分配模型会使已有优势更难逆转。" /><p>它在哪些条件下不成立？</p><textarea placeholder="由你自己写下范围或可能反例……" /><div className="ru-forge-boundary">只问不给 · Cui 可以澄清，但不会代写候选主张。</div><footer><button onClick={() => setStage("workspace")}>回到探索</button><button className="ru-dark-action">确认提交检验</button></footer></aside></section>}
    </main>
    <QuenchPulse />
  </div>
}

function QuenchPulse({ evidence = false }: { evidence?: boolean }) {
  return (
    <div className="ru-quench-demo">
      <span className="ru-pulse-dot" />
      <span>{evidence ? "试试看确认一项取证" : "淬色只在用户确认时出现"}</span>
      <button onClick={(event) => event.currentTarget.parentElement?.classList.toggle("is-quenched")}>确认演示</button>
    </div>
  )
}

function Switcher({ current }: { current: Variant }) {
  const index = variants.findIndex((item) => item.key === current)
  const move = (delta: number) => {
    const next = variants[(index + delta + variants.length) % variants.length]
    const params = new URLSearchParams(window.location.search)
    params.set("prototype", "research-universe")
    params.set("variant", next.key)
    window.history.replaceState({}, "", `${window.location.pathname}?${params}`)
    window.dispatchEvent(new PopStateEvent("popstate"))
  }
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null
      if (target?.matches("input, textarea, [contenteditable=true]")) return
      if (event.key === "ArrowLeft") move(-1)
      if (event.key === "ArrowRight") move(1)
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  })
  return <nav className="ru-switcher"><button onClick={() => move(-1)} aria-label="Previous variation">←</button><span><b>{current}</b> — {variants[index].name}<small>{variants[index].description}</small></span><button onClick={() => move(1)} aria-label="Next variation">→</button></nav>
}

export default function ResearchUniversePrototype({ variant }: { variant: Variant }) {
  const [readingMode, setReadingMode] = useState<"reading" | "forge" | "grill" | "verdict">("reading")
  const [evidenceConfirmed, setEvidenceConfirmed] = useState(false)
  return <><style>{styles}</style>{variant === "A" ? <VariantA mode={readingMode} onMode={setReadingMode} /> : variant === "B" ? <VariantB confirmed={evidenceConfirmed} onConfirm={() => setEvidenceConfirmed((value) => !value)} /> : variant === "C" ? <VariantC /> : <VariantD />}<Switcher current={variant} /></>
}

const styles = `
@import url('https://fonts.googleapis.com/css2?family=Charis+SIL:ital,wght@0,400;0,700;1,400&family=IBM+Plex+Sans:wght@400;500;600&family=Noto+Serif+SC:wght@400;600&family=Noto+Sans+SC:wght@400;500;600&display=swap');
:root { --stone:#eaebe7; --paper:#f8f8f4; --ink:#222725; --muted:#68716e; --line:#d6d9d3; --edge:#315b51; --teal:#2d8c84; --rust:#a94b39; --wash:#e9efeb; }
* { box-sizing:border-box; }
button { font:inherit; cursor:pointer; }
.ru-page { min-height:100vh; color:var(--ink); background:var(--stone); font-family:'IBM Plex Sans','Noto Sans SC',sans-serif; padding-bottom:82px; }
.ru-topbar { height:64px; display:flex; align-items:center; gap:25px; padding:0 36px; border-bottom:1px solid var(--line); background:rgba(248,248,244,.83); backdrop-filter:blur(12px); position:sticky; top:0; z-index:4; }
.ru-wordmark { display:flex; gap:8px; align-items:center; font-size:16px; letter-spacing:-.02em; min-width:90px; }.ru-wordmark span { font-family:'Noto Serif SC',serif; font-size:22px; }.ru-wordmark b{font-weight:600}.ru-breadcrumb{font-size:12px;color:var(--muted);flex:1}.ru-breadcrumb i{font-style:normal;color:#a1a9a4;padding:0 6px}.ru-actions{display:flex;gap:8px;align-items:center}.ru-actions button{border:0;background:none;color:var(--ink);padding:8px 11px;font-size:13px}.ru-primary{background:var(--ink)!important;color:var(--paper)!important;border-radius:3px!important}.ru-prototype-label{font-size:9px;letter-spacing:.11em;color:var(--muted);border-left:1px solid var(--line);padding-left:15px}
.ru-question-spine{max-width:1280px;margin:0 auto;padding:17px 34px 13px;display:flex;flex-wrap:wrap;gap:10px;align-items:baseline;border-bottom:1px solid var(--line)}.ru-spine-label,.ru-eyebrow{font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);font-weight:600}.ru-question-spine strong{font-size:15px;letter-spacing:-.015em}.ru-question-spine button{font-size:12px;border:0;border-bottom:1px solid #909995;background:none;padding:0;color:var(--edge)}.ru-question-spine small{width:100%;margin-left:58px;color:var(--muted);font-size:11px}.ru-status{font-size:11px;color:var(--edge);margin-left:auto}
.ru-reading-layout{max-width:1280px;margin:0 auto;display:grid;grid-template-columns:minmax(0,1fr) 280px;min-height:calc(100vh - 132px)}.ru-notebook{padding:42px min(9vw,135px) 32px 12vw;background:var(--paper);border-right:1px solid var(--line)}.ru-surface-caption{display:flex;justify-content:space-between;border-bottom:1px solid var(--line);padding-bottom:12px;margin-bottom:27px;font-size:12px}.ru-surface-caption span{font-weight:600}.ru-surface-caption em{color:var(--muted);font-style:normal;font-size:11px}.ru-prose{font-family:'Charis SIL','Noto Serif SC',serif;font-size:19px;line-height:1.9;max-width:680px;outline:0}.ru-prose p{margin:0 0 1.25em}.ru-prose strong{font-weight:700}.ru-anchor{background:linear-gradient(90deg,rgba(45,140,132,.11),transparent 85%);border-left:2px solid var(--teal);padding:10px 17px;margin-left:-19px!important}.ru-anchor button{font-family:'IBM Plex Sans','Noto Sans SC',sans-serif;font-size:11px;border:0;background:var(--ink);color:var(--paper);padding:5px 8px;margin-left:8px}.ru-notebook-footer{max-width:680px;border-top:1px solid var(--line);display:flex;justify-content:space-between;padding-top:20px;margin-top:42px}.ru-notebook-footer button{border:0;background:none;color:var(--muted);font-size:12px}.ru-notebook-footer .ru-outline{border:1px solid #9da5a0;color:var(--ink);padding:7px 10px}
.ru-rail{padding:31px 19px;background:#eff0ec}.ru-rail section{margin-top:25px}.ru-rail-heading{display:flex;justify-content:space-between;font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);padding-bottom:9px}.ru-rail-heading b{font-weight:500}.ru-rail-item{width:100%;text-align:left;border:0;border-left:2px solid transparent;background:transparent;padding:8px 9px;margin:2px 0;display:flex;gap:4px;flex-direction:column}.ru-rail-item:hover{background:rgba(255,255,255,.55)}.ru-rail-item strong{font-size:12px;font-weight:500;line-height:1.45}.ru-rail-item small{font-size:10px;color:var(--muted);line-height:1.4}.ru-contested{border-left-color:var(--rust);background:rgba(169,75,57,.055)}.ru-confirmed{border-left-color:var(--edge)}.ru-quench{display:inline-flex;align-items:center;width:max-content;font-size:9px;line-height:1;color:var(--edge);letter-spacing:.09em;text-transform:uppercase;border-bottom:1px solid currentColor;padding-bottom:2px}
.ru-quench-demo{position:fixed;right:27px;bottom:20px;z-index:9;background:#222725;color:#f8f8f4;display:flex;gap:9px;align-items:center;padding:8px 10px 8px 12px;box-shadow:0 9px 25px rgba(20,30,25,.18);font-size:11px}.ru-quench-demo button{border:1px solid #77827d;color:inherit;background:none;font-size:10px;padding:4px 7px}.ru-pulse-dot{width:7px;height:7px;border-radius:50%;background:#8f9c95}.ru-quench-demo.is-quenched .ru-pulse-dot{background:var(--teal);box-shadow:0 0 0 5px rgba(45,140,132,.18)}.ru-quench-demo.is-quenched{border-bottom:2px solid var(--teal)}
.ru-evidence-page{background:#e7e9e5}.ru-evidence-header{max-width:1160px;margin:0 auto;padding:72px 40px 35px}.ru-evidence-header h1,.ru-terrain-intro h1{font-size:42px;line-height:1.12;letter-spacing:-.045em;font-weight:500;margin:12px 0}.ru-evidence-header p:last-child{color:var(--muted);font-size:15px}.ru-evidence-board{max-width:1160px;margin:0 auto;padding:0 40px;display:grid;grid-template-columns:1fr 1fr;gap:1px;background:var(--line);border:1px solid var(--line)}.ru-source-sheet,.ru-claim-sheet{background:var(--paper);padding:34px 38px;min-height:540px}.ru-sheet-meta{display:flex;justify-content:space-between;font-size:11px;color:var(--muted);border-bottom:1px solid var(--line);padding-bottom:12px}.ru-sheet-meta span{color:var(--ink);font-weight:600}.ru-source-sheet blockquote{font-family:'Charis SIL','Noto Serif SC',serif;font-size:25px;line-height:1.55;letter-spacing:-.015em;margin:45px 0 25px}.ru-source-sheet>p{font-size:13px;line-height:1.65;color:var(--muted);max-width:430px}.ru-source-facts{border-top:1px solid var(--line);margin-top:45px;padding-top:13px;display:flex;gap:16px;font-size:11px;color:var(--muted)}.ru-claim-sheet h2{font-family:'Charis SIL','Noto Serif SC',serif;font-weight:400;font-size:27px;line-height:1.45;margin:37px 0 25px}.ru-candidate-label{font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--rust);font-weight:600}.ru-claim-sheet h3{font-size:15px;margin:10px 0}.ru-claim-sheet>p{font-family:'Charis SIL','Noto Serif SC',serif;font-size:17px;line-height:1.65}.ru-uncertainty{border-left:2px solid #99a09b;background:#eff0ec;padding:10px 12px;font-size:12px;color:#525b56;margin:25px 0}.ru-evidence-actions{border-top:1px solid var(--line);padding-top:18px;display:flex;flex-wrap:wrap;gap:7px}.ru-evidence-actions button{background:transparent;border:1px solid #b3bab5;padding:7px 9px;font-size:11px;color:var(--ink)}.ru-evidence-actions .ru-confirm-action{border-color:var(--edge);color:var(--edge)}.ru-confirm-action span{color:var(--teal);font-size:15px;vertical-align:-1px}
.ru-terrain{max-width:1190px;margin:0 auto;padding:87px 42px 45px}.ru-terrain-intro{max-width:690px}.ru-terrain-intro p:last-child{color:var(--muted);font-size:15px;line-height:1.6;max-width:510px}.ru-direction-field{margin-top:64px;display:grid;grid-template-columns:1.25fr .75fr;gap:18px;align-items:stretch}.ru-direction{padding:25px 27px;background:var(--paper);border-top:2px solid #939b95;min-height:260px;display:flex;flex-direction:column}.ru-direction-main{border-top-color:var(--edge)}.ru-direction header{display:flex;justify-content:space-between;color:var(--muted);font-size:11px}.ru-direction-index{letter-spacing:.1em}.ru-direction-state{font-size:10px;letter-spacing:.09em;text-transform:uppercase}.ru-direction-state.active{color:var(--edge)}.ru-direction h2{font-family:'Charis SIL','Noto Serif SC',serif;font-weight:400;font-size:25px;line-height:1.42;letter-spacing:-.02em;margin:28px 0 15px;max-width:630px}.ru-direction-title{border:0;background:none;padding:0;text-align:left;color:inherit}.ru-direction-title:hover h2{text-decoration:underline;text-decoration-color:#9da6a0;text-underline-offset:5px}.ru-direction-note{color:var(--muted);font-size:12px;margin:0}.ru-terrain-fact{display:flex;align-items:center;gap:7px;border:0;background:transparent;color:var(--rust);font-size:12px;padding:20px 0 5px}.ru-direction.is-focused{grid-column:1/-1;min-height:480px;border-top-color:var(--edge);padding:30px 34px}.ru-direction.is-focused h2{font-size:32px;max-width:800px;margin-top:17px}.ru-direction.is-receded,.ru-unplaced.is-receded{opacity:.38;filter:saturate(.45);transform:scale(.985);transform-origin:top}.ru-direction-viewport{margin-top:31px;border-top:1px solid var(--line);display:grid;grid-template-columns:1.15fr .85fr;gap:38px;padding-top:20px}.ru-direction-viewport section{display:flex;flex-direction:column;gap:5px}.ru-direction-viewport section>button{border:0;background:transparent;border-bottom:1px solid var(--line);padding:11px 0;text-align:left;font:15px/1.45 'Charis SIL','Noto Serif SC',serif;color:var(--ink);display:grid;grid-template-columns:1fr auto;gap:8px}.ru-direction-viewport section>button b{font:10px 'IBM Plex Sans','Noto Sans SC',sans-serif;color:var(--rust);white-space:nowrap}.ru-direction-viewport section>button span{grid-column:1/-1;font:10px 'IBM Plex Sans','Noto Sans SC',sans-serif;color:var(--muted)}.ru-direction-viewport article{border-bottom:1px solid var(--line);padding:10px 0;display:grid;grid-template-columns:62px 1fr;gap:12px}.ru-direction-viewport article strong{font:14px/1.5 'Charis SIL','Noto Serif SC',serif;font-weight:400}.ru-direction-viewport footer{grid-column:1/-1;border-top:1px solid var(--line);padding-top:16px;display:flex;justify-content:space-between}.ru-direction-viewport footer button{border:0;background:none;font-size:11px;color:var(--muted)}.ru-direction-viewport footer button:last-child{color:var(--ink);border-bottom:1px solid var(--ink);padding-bottom:2px}.ru-enter{margin-top:auto;align-self:flex-end;border:0;border-bottom:1px solid var(--ink);background:none;padding:0 0 3px;font-size:12px}.ru-enter span{padding-left:7px}.ru-unplaced{grid-column:2;padding:20px 25px;border:1px dashed #abb2ad;color:var(--muted);display:flex;flex-direction:column;gap:12px;min-height:188px}.ru-unplaced span{font-size:10px;letter-spacing:.12em;text-transform:uppercase}.ru-unplaced strong{font-family:'Charis SIL','Noto Serif SC',serif;font-weight:400;font-size:19px;line-height:1.4;color:var(--ink)}.ru-unplaced p{font-size:12px;margin:0}.ru-unplaced button{align-self:flex-start;border:0;background:none;padding:0;border-bottom:1px solid #89938e;font-size:11px;color:var(--ink)}
.ru-switcher{position:fixed;left:50%;bottom:19px;transform:translateX(-50%);z-index:20;display:flex;align-items:stretch;background:#202523;color:#f8f8f4;box-shadow:0 10px 35px rgba(25,35,30,.24);min-width:310px}.ru-switcher button{width:40px;border:0;background:transparent;color:inherit;font-size:17px}.ru-switcher button:hover{background:#315b51}.ru-switcher span{padding:7px 14px;min-width:230px;border-left:1px solid #56605b;border-right:1px solid #56605b;font-size:11px}.ru-switcher b{color:#75c5bd}.ru-switcher small{display:block;color:#a9b1ac;font-size:9px;margin-top:2px}
.ru-reading-layout.ru-has-focus{grid-template-columns:minmax(0,1fr) 360px}.ru-reading-layout.ru-has-focus .ru-rail{display:none}.ru-focus-pane{background:#eef0eb;padding:34px 28px;border-left:1px solid var(--line);box-shadow:-18px 0 42px rgba(34,39,37,.05)}.ru-focus-pane h2{font-family:'Charis SIL','Noto Serif SC',serif;font-weight:400;font-size:27px;line-height:1.35;letter-spacing:-.025em;margin:12px 0 25px}.ru-focus-pane p{font-size:12px;line-height:1.6;color:#4d5752;margin:16px 0 7px}.ru-focus-pane textarea{width:100%;min-height:78px;resize:vertical;border:1px solid #bcc4be;background:var(--paper);padding:9px;font:15px/1.65 'Charis SIL','Noto Serif SC',serif;outline-color:var(--teal)}.ru-focus-pane footer{margin-top:23px;display:flex;justify-content:space-between;align-items:center}.ru-focus-pane footer button{border:0;background:none;color:var(--muted);font-size:11px}.ru-focus-pane .ru-dark-action{background:var(--ink);color:var(--paper);padding:8px 10px}.ru-attack-list{display:flex;flex-direction:column;border-top:1px solid var(--line);margin:4px 0 17px}.ru-attack-list button{border:0;border-bottom:1px solid var(--line);background:transparent;text-align:left;padding:11px 5px;font-size:12px;color:var(--muted)}.ru-attack-list .is-active{color:var(--ink);border-left:2px solid var(--rust);padding-left:9px;background:rgba(169,75,57,.05)}.ru-ledger{border-top:1px solid var(--line);border-bottom:1px solid var(--line);padding:9px 0;display:flex;flex-direction:column;gap:6px;font-size:11px;color:var(--muted)}.ru-verdict-choices{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin:17px 0}.ru-verdict-choices button{background:var(--paper);border:1px solid #b8c0ba;text-align:left;padding:8px;font-size:11px}.ru-confirm-local{border-bottom:2px solid var(--teal)!important}.ru-is-confirmed{color:var(--edge)!important}.ru-local-receipt{border-top:1px solid var(--line);margin-top:24px;padding-top:15px;color:var(--edge);font-size:12px;display:flex;align-items:center;gap:8px}.ru-local-receipt .ru-pulse-dot{background:var(--teal);box-shadow:0 0 0 5px rgba(45,140,132,.14)}.ru-local-receipt button{margin-left:auto;border:0;background:none;border-bottom:1px solid #8d9891;padding:0;font-size:10px;color:var(--muted)}
.ru-park-page{background:var(--stone)}.ru-park-main{max-width:980px;margin:0 auto;padding:58px 42px 110px;min-height:calc(100vh - 64px);display:flex;align-items:flex-start;justify-content:center}.ru-park-surface,.ru-release-surface,.ru-workspace-surface{width:min(760px,100%);background:var(--paper);padding:37px 48px 34px;border-top:1px solid #b8c1ba}.ru-park-surface h1{font-family:'Charis SIL','Noto Serif SC',serif;font-size:41px;line-height:1.18;font-weight:400;letter-spacing:-.04em;margin:15px 0 32px}.ru-park-surface textarea{width:100%;min-height:150px;background:transparent;border:0;border-top:1px solid var(--line);border-bottom:1px solid var(--line);padding:18px 0;font:22px/1.65 'Charis SIL','Noto Serif SC',serif;color:var(--ink);resize:vertical;outline-color:var(--teal)}.ru-park-note{display:flex;gap:8px;align-items:flex-start;color:var(--muted);font-size:12px;line-height:1.6;margin:16px 0 0}.ru-park-note span{color:var(--edge);font-size:15px}.ru-park-note strong{color:var(--ink);font-weight:500}.ru-park-surface footer,.ru-release-surface footer,.ru-workspace-surface>footer{display:flex;justify-content:space-between;margin-top:29px}.ru-plain-action{border:0;background:none;padding:0;color:var(--muted);font-size:12px}.ru-release-surface blockquote{font-family:'Charis SIL','Noto Serif SC',serif;font-size:27px;line-height:1.5;letter-spacing:-.025em;margin:21px 0 34px}.ru-release-fields{display:grid;grid-template-columns:1fr 1fr;gap:18px;border-top:1px solid var(--line);padding-top:18px}.ru-release-fields label{font-size:11px;color:var(--muted)}.ru-release-fields select{width:100%;display:block;margin-top:6px;padding:8px;border:1px solid var(--line);background:#fff;color:var(--ink);font:12px 'IBM Plex Sans','Noto Sans SC',sans-serif}.ru-release-link{display:flex;gap:8px;align-items:center;font-size:10px;color:var(--muted);margin-bottom:25px}.ru-release-link button{border:0;border-bottom:1px solid #9aa49d;background:none;padding:0;color:var(--edge);font-size:10px}.ru-workspace-surface{padding:32px 50px 42px}.ru-d-question{padding:0 0 15px;margin:0;border-bottom:1px solid var(--line)}.ru-d-question small{display:none}.ru-d-prose{margin-top:28px}.ru-workspace-surface .ru-prose{max-width:650px}.ru-workspace-surface .ru-anchor{margin-top:25px!important}.ru-d-forge{width:100%;display:grid;grid-template-columns:minmax(0,1fr) 360px;background:var(--paper);border-top:1px solid #b8c1ba}.ru-d-forge>article{padding:42px 48px;background:#f0f1ed}.ru-d-forge article blockquote{font-family:'Charis SIL','Noto Serif SC',serif;font-size:25px;line-height:1.55;margin:20px 0}.ru-d-forge article>p:last-child{font-size:12px;color:var(--muted);line-height:1.65;max-width:490px}.ru-d-forge .ru-focus-pane{border-left:1px solid var(--line);box-shadow:none}.ru-forge-boundary{margin-top:18px;padding-top:12px;border-top:1px solid var(--line);font-size:10px;letter-spacing:.04em;color:var(--edge)}
@media(max-width:780px){.ru-reading-layout.ru-has-focus{display:block}.ru-focus-pane{border-left:0;border-top:1px solid var(--line)}.ru-topbar{padding:0 16px}.ru-breadcrumb,.ru-prototype-label{display:none}.ru-reading-layout{display:block}.ru-notebook{padding:27px 25px}.ru-rail{display:none}.ru-question-spine{padding:15px 18px}.ru-question-spine small{margin-left:0}.ru-evidence-header,.ru-terrain{padding-left:20px;padding-right:20px}.ru-evidence-board{padding:0;grid-template-columns:1fr}.ru-source-sheet,.ru-claim-sheet{padding:25px}.ru-direction-field{grid-template-columns:1fr}.ru-unplaced{grid-column:auto}.ru-evidence-header h1,.ru-terrain-intro h1{font-size:32px}.ru-switcher{min-width:280px}.ru-topbar .ru-actions{margin-left:auto}.ru-wordmark{min-width:auto}.ru-park-main{padding:28px 20px}.ru-park-surface,.ru-release-surface,.ru-workspace-surface{padding:28px 25px}.ru-park-surface h1{font-size:34px}.ru-release-fields,.ru-d-forge{grid-template-columns:1fr}.ru-d-forge>article{padding:29px 25px}.ru-d-forge .ru-focus-pane{border-left:0;border-top:1px solid var(--line)}}
`
