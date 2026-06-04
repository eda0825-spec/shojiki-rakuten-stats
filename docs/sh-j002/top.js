// TOP page: standalone aggregation from 3 sources + lang toggle + sales widget

const REPO = "eda0825-spec/shojiki-rakuten-stats";
const BRANCH = "main";
const PRODUCT = window.PRODUCT;
const LS_LANG_KEY = "shojiki-dashboard-lang";

// --- topic → cluster mapping (same as app.js) ---
const CLUSTERS = [
  { key: "charging", emoji: "🔋", name_ja: "充電・バッテリー", name_zh: "充电·电池", topics: ["バッテリー","充電","充電端子","充電スタンド","充電台","電気系統","電池"] },
  { key: "weight",   emoji: "⚖️", name_ja: "重量・サイズ",     name_zh: "重量·尺寸",   topics: ["重量","軽量","コンパクト","本体形状"] },
  { key: "suction",  emoji: "💨", name_ja: "吸引力",          name_zh: "吸力",        topics: ["吸引力","吸力","基本機能"] },
  { key: "noise",    emoji: "🔊", name_ja: "音・静音性",      name_zh: "噪音·静音",   topics: ["騒音","静音性","動作音","音"] },
  { key: "dustcup",  emoji: "🗑️", name_ja: "ダストカップ",   name_zh: "集尘杯",      topics: ["ダストカップ","集尘杯","ゴミ捨て"] },
  { key: "roller",   emoji: "🪥", name_ja: "ローラー・ヘッド", name_zh: "滚刷·吸头",  topics: ["ローラー","ヘッド","滚刷","吸头","ノズル","髪の毛","頭髪","毛絡まり"] },
  { key: "filter",   emoji: "🧽", name_ja: "フィルター",       name_zh: "过滤器",      topics: ["フィルター","过滤器","メンテナンス","お手入れ"] },
  { key: "operation",emoji: "🎛️", name_ja: "操作・ボタン",   name_zh: "操作·按钮",   topics: ["操作性","操作ボタン","スイッチ","ハンディモード","ボタン"] },
  { key: "stand",    emoji: "📐", name_ja: "スタンド・自立",  name_zh: "支架·自立",   topics: ["自立機能","自走機能","スタンド","転倒耐性","壁掛け"] },
  { key: "design",   emoji: "🎨", name_ja: "デザイン",        name_zh: "外观",        topics: ["デザイン","外装","外壳","カラー","色"] },
  { key: "safety",   emoji: "⚠️", name_ja: "安全性",         name_zh: "安全性",      topics: ["安全性","怪我","発火","感電"] },
  { key: "carpet",   emoji: "🏠", name_ja: "床・カーペット",  name_zh: "地板·地毯",   topics: ["カーペット対応","カーペット","絨毯対応","床"] },
];
const TOPIC_TO_CLUSTER = (() => { const m = new Map(); for (const c of CLUSTERS) for (const t of c.topics) m.set(t, c.key); return m; })();

const state = {
  lang: (typeof localStorage !== "undefined" && localStorage.getItem(LS_LANG_KEY)) || "ja",
  data: { reviews: [], cats: [], merged: { issues: [] }, sales: null },
};

function esc(s) {
  return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
async function fetchJSON(file) {
  // raw を優先 (fresh)。jsdelivr は中国アクセス用フォールバック (一覧ページと統一)
  const urls = [
    `https://raw.githubusercontent.com/${REPO}/${BRANCH}/${file}`,
    `https://cdn.jsdelivr.net/gh/${REPO}@${BRANCH}/${file}`,
  ];
  let lastErr;
  for (const u of urls) {
    try {
      const r = await fetch(u, { cache: "no-cache" });
      if (!r.ok) throw new Error(`${r.status}`);
      return await r.json();
    } catch (e) { lastErr = e; }
  }
  throw lastErr;
}

// ===== Language toggle =====
function applyLang(lang) {
  document.body.classList.toggle("lang-ja", lang === "ja");
  document.body.classList.toggle("lang-zh", lang === "zh");
  document.querySelectorAll(".lang-toggle button").forEach(b => b.classList.toggle("active", b.dataset.lang === lang));
}
(function initLang() {
  applyLang(state.lang);
  document.querySelectorAll(".lang-toggle button").forEach(b => {
    b.addEventListener("click", () => {
      state.lang = b.dataset.lang;
      try { localStorage.setItem(LS_LANG_KEY, state.lang); } catch(e) {}
      applyLang(state.lang);
      renderAll();
    });
  });
})();

// ===== Data loaders =====
async function loadAll() {
  const [reviews, cats, merged, sales, summary] = await Promise.all([
    fetchJSON(`reviews-${PRODUCT}.json`).catch(() => ({ reviews: [] })),
    fetchJSON(`categorized-${PRODUCT}.json`).catch(() => ({ results: [] })),
    fetchJSON(`docs/data/defects-merged.json`).catch(() => ({ issues: [] })),
    fetchJSON(`sales-summary.json`).catch(() => null),
    fetchJSON(`summary-${PRODUCT}.json`).catch(() => null),
  ]);
  state.data.reviews = reviews.reviews || [];
  state.data.cats = cats.results || [];
  state.data.merged = merged;
  state.data.sales = sales;
  state.data.summary = summary;
  state.data.reviewsUpdatedAt = reviews.updatedAt;
}

// ===== Render: sales widget =====
function renderSales() {
  const widget = document.getElementById("sales-widget");
  const sales = state.data.sales;
  if (!sales) return;
  const bp = (sales.byProduct || {})[PRODUCT];
  if (!bp) return;
  const status = bp.platformStatus || {};
  const anyConfigured = Object.values(status).some(p => p.configured);
  if (!anyConfigured && (bp.allTime?.total || 0) === 0) return;
  widget.hidden = false;
  document.getElementById("sw-today").textContent     = (bp.today?.total ?? 0).toLocaleString();
  document.getElementById("sw-month").textContent     = (bp.thisMonth?.total ?? 0).toLocaleString();
  document.getElementById("sw-lastmonth").textContent = (bp.lastMonth?.total ?? 0).toLocaleString();
  document.getElementById("sw-alltime").textContent   = (bp.allTime?.total ?? 0).toLocaleString();
  if (sales.updatedAt) {
    const d = new Date(sales.updatedAt);
    document.getElementById("sw-updated").textContent =
      "更新: " + d.toLocaleString(state.lang === "zh" ? "zh-CN" : "ja-JP", { timeZone: "Asia/Tokyo" });
  }
  const platLabels = { rakuten: "楽天", amazon: "Amazon", shopify: "Shopify" };
  document.getElementById("sw-platforms").innerHTML =
    ["rakuten", "amazon", "shopify"].map(plat => {
      const s = status[plat] || {};
      const todayQty = bp.today?.[plat] ?? 0;
      const monthQty = bp.thisMonth?.[plat] ?? 0;
      const cls = s.configured ? "" : "dim";
      const note = s.configured ? "" : (state.lang === "zh" ? "未配置" : "未設定");
      return `<span class="sw-plat ${cls}"><strong>${platLabels[plat]}</strong> ${s.configured ? `今日 ${todayQty} ・ 今月 ${monthQty}` : note}</span>`;
    }).join("");
}

// ===== Render: 3 hero count cells =====
function renderCounts() {
  const cats = state.data.cats;
  const def = cats.filter(c => c.category === "defect").length;
  const imp = cats.filter(c => c.category === "improvement").length;
  document.getElementById("cnt-feedback").textContent = (def + imp).toLocaleString();

  const issues = (state.data.merged.issues || []).filter(i => i.product === PRODUCT);
  const isReturn = (i) => (i.labels || []).includes("type:return");
  const isDefect = (i) => !isReturn(i);
  const openDefects = issues.filter(i => isDefect(i) && i.state === "open").length;
  const openReturns = issues.filter(i => isReturn(i)  && i.state === "open").length;
  document.getElementById("cnt-defects").textContent = openDefects.toLocaleString();
  document.getElementById("cnt-returns").textContent = openReturns.toLocaleString();
}

// ===== Render: cluster chart =====
function renderClusterChart() {
  const reviewMap = new Map(state.data.reviews.map(r => [r.id, r]));
  const joined = state.data.cats.map(c => ({ ...c, ...(reviewMap.get(c.id) || {}) }));

  const buckets = new Map();
  for (const c of CLUSTERS) buckets.set(c.key, { defect: 0, improvement: 0 });
  for (const r of joined) {
    if (r.category !== "defect" && r.category !== "improvement") continue;
    // PRIMARY cluster only: first matching topic in Claude's topic array.
    // (Claude lists topics in importance order; counts the review against
    // its main subject, avoiding double-counting across clusters.)
    let primaryCluster = null;
    for (const tp of r.topics || []) {
      const ck = TOPIC_TO_CLUSTER.get(tp);
      if (ck) { primaryCluster = ck; break; }
    }
    if (primaryCluster) buckets.get(primaryCluster)[r.category]++;
  }
  const ranked = CLUSTERS.map(c => ({ ...c, ...buckets.get(c.key) }))
    .filter(c => (c.defect + c.improvement) > 0)
    .sort((a, b) => (b.defect + b.improvement) - (a.defect + a.improvement))
    .slice(0, 8);
  const section = document.getElementById("cluster-chart-section");
  const rowsWrap = document.getElementById("cluster-chart-rows");
  if (!ranked.length) { section.hidden = true; return; }
  section.hidden = false;
  const max = Math.max(1, ...ranked.map(c => c.defect + c.improvement));
  rowsWrap.innerHTML = ranked.map(c => {
    const name = state.lang === "zh" ? c.name_zh : c.name_ja;
    const total = c.defect + c.improvement;
    const totalPct = (total / max) * 100;
    const defectPct = total > 0 ? (c.defect / total) * totalPct : 0;
    const impPct = total > 0 ? (c.improvement / total) * totalPct : 0;
    return `
      <a class="cluster-row" href="./feedback.html#cluster=${c.key}">
        <span class="cluster-row-label"><span class="emo">${c.emoji}</span><span class="name">${esc(name)}</span></span>
        <span class="cluster-row-bar">
          ${c.defect > 0 ? `<span class="seg-d" style="width:${defectPct}%"></span>` : ""}
          ${c.improvement > 0 ? `<span class="seg-i" style="width:${impPct}%"></span>` : ""}
          ${c.defect >= max * 0.08 ? `<span class="lbl-d">${c.defect}</span>` : ""}
          ${c.improvement >= max * 0.08 ? `<span class="lbl-i" style="left:${defectPct}%;right:auto">${c.improvement}</span>` : ""}
        </span>
        <span class="cluster-row-count">${total}</span>
      </a>`;
  }).join("");
}

// ===== Render: latest lists =====
function renderLatestLists() {
  const isJa = state.lang !== "zh";

  // Latest defects (from Issues with type:defect)
  const issues = (state.data.merged.issues || []).filter(i => i.product === PRODUCT);
  const isReturn = (i) => (i.labels || []).includes("type:return");
  const defects = issues.filter(i => !isReturn(i) && i.state === "open").slice(0, 5);
  const returns = issues.filter(i =>  isReturn(i) && i.state === "open").slice(0, 5);

  const empty = `<li class="mini-empty">${isJa ? "まだありません" : "还没有"}</li>`;

  const dUl = document.getElementById("latest-defects");
  dUl.innerHTML = defects.length === 0 ? empty : defects.map(i => `
    <li>
      <span class="mini-badge cat-defect">${isJa ? "不具合" : "故障"}</span>
      <a href="${esc(i.url)}" target="_blank">${esc(i.title)}</a>
      <span class="mini-date">${esc((i.updated_at || "").slice(0,10))}</span>
    </li>`).join("");

  const rUl = document.getElementById("latest-returns");
  rUl.innerHTML = returns.length === 0 ? empty : returns.map(i => `
    <li>
      <span class="mini-badge cat-return">${isJa ? "返品" : "退货"}</span>
      <a href="${esc(i.url)}" target="_blank">${esc(i.title)}</a>
      <span class="mini-date">${esc((i.updated_at || "").slice(0,10))}</span>
    </li>`).join("");

  // Latest feedback (severity high first, then medium)
  const reviewMap = new Map(state.data.reviews.map(r => [r.id, r]));
  const sevRank = { high: 0, medium: 1, low: 2, "n/a": 3 };
  const neg = state.data.cats
    .filter(c => c.category === "defect" || c.category === "improvement")
    .map(c => ({ ...c, ...(reviewMap.get(c.id) || {}) }))
    .filter(c => c.postDate)
    .sort((a, b) => {
      const sa = sevRank[a.severity] ?? 9, sb = sevRank[b.severity] ?? 9;
      if (sa !== sb) return sa - sb;
      return (b.postDate || "").localeCompare(a.postDate || "");
    })
    .slice(0, 5);
  const fUl = document.getElementById("latest-feedback");
  fUl.innerHTML = neg.length === 0 ? empty : neg.map(c => {
    const cat = c.category;
    const sum = (isJa ? c.summary_ja : c.summary_zh) || c.body || "";
    return `
    <li>
      <span class="mini-badge cat-${esc(cat)}">${isJa ? (cat === "defect" ? "不具合" : "改善") : (cat === "defect" ? "故障" : "改善")}</span>
      <a href="./feedback.html">${esc(sum.slice(0, 80))}</a>
      <span class="mini-date">${esc(c.postDate || "")}</span>
    </li>`;
  }).join("");
}

function renderUpdated() {
  if (state.data.reviewsUpdatedAt) {
    const dt = new Date(state.data.reviewsUpdatedAt);
    document.getElementById("last-update").textContent =
      "レビュー取得: " + dt.toLocaleString(state.lang === "zh" ? "zh-CN" : "ja-JP", { timeZone: "Asia/Tokyo" });
  }
}

// ===== Render: AI Summary =====
function renderSummary() {
  const widget = document.getElementById("ai-summary");
  const s = state.data.summary;
  if (!s) { widget.hidden = true; return; }
  const lang = state.lang === "zh" ? "summary_zh" : "summary_ja";
  const block = s[lang] || s.summary_ja;
  if (!block) { widget.hidden = true; return; }
  widget.hidden = false;

  document.getElementById("ai-headline").textContent = block.headline || "";
  document.getElementById("ai-narrative").textContent = block.narrative || "";

  // Source breakdown chips (3-source integration visibility)
  const srcEl = document.getElementById("ai-sources");
  if (srcEl && s.stats) {
    const isJa = state.lang !== "zh";
    const st = s.stats;
    const labels = isJa
      ? { rev: "📝 レビュー", iss_d: "🔧 不具合Issue", iss_r: "📦 返品", praise: "👍 称賛" }
      : { rev: "📝 评价", iss_d: "🔧 故障Issue", iss_r: "📦 退货", praise: "👍 好评" };
    const reviewNeg = (st.defect || 0) + (st.improvement || 0);
    srcEl.innerHTML = [
      `<span class="src-chip src-neg">${labels.rev} ${reviewNeg}${isJa?"件":"条"} <small>(${isJa?"不満":"不满"})</small></span>`,
      `<span class="src-chip src-iss">${labels.iss_d} ${st.issue_defect || 0}${isJa?"件":"条"}</span>`,
      `<span class="src-chip src-ret">${labels.iss_r} ${st.issue_return || 0}${isJa?"件":"条"}</span>`,
      `<span class="src-chip src-praise">${labels.praise} ${st.praise || 0}${isJa?"件":"条"}</span>`,
    ].join("");
    srcEl.hidden = false;
  }

  // Find matching cluster meta for each finding (to show defect/return breakdown)
  const clustersByName = {};
  (s.top_clusters || []).forEach(c => { clustersByName[c.name] = c; });

  const findings = block.key_findings || [];
  document.getElementById("ai-findings").innerHTML = findings.length
    ? findings.map(f => {
        const meta = clustersByName[f.topic] || null;
        const isJa = state.lang !== "zh";
        const breakdown = [];
        if (meta) {
          if (meta.issue_return) breakdown.push(`<span class="bk-tag bk-ret">${isJa?"返品":"退货"} ${meta.issue_return}</span>`);
          if (meta.issue_defect) breakdown.push(`<span class="bk-tag bk-iss">${isJa?"工場":"工厂"} ${meta.issue_defect}</span>`);
          if (meta.review_defect) breakdown.push(`<span class="bk-tag bk-def">${isJa?"深刻":"严重"} ${meta.review_defect}</span>`);
          if (meta.review_improvement) breakdown.push(`<span class="bk-tag bk-imp">${isJa?"改善要望":"改善"} ${meta.review_improvement}</span>`);
          if (meta.is_core_function) breakdown.unshift(`<span class="bk-tag bk-core">${isJa?"⚠ 核心機能":"⚠ 核心功能"}</span>`);
        }
        return `<li>
          <div class="finding-head"><span class="topic-tag">${esc(f.topic || "")}</span><span class="count-tag">(${f.count || 0}${isJa?"件":"条"})</span></div>
          <div class="finding-body">${esc(f.finding || "")}</div>
          ${breakdown.length ? `<div class="finding-bk">${breakdown.join("")}</div>` : ""}
        </li>`;
      }).join("")
    : `<li style="border-left-color:#aaa;background:transparent">${state.lang === "zh" ? "暂无数据" : "データなし"}</li>`;

  const actions = block.actions || [];
  document.getElementById("ai-actions").innerHTML = actions.length
    ? actions.map(a => `<li>${esc(a)}</li>`).join("")
    : `<li style="border-left-color:#aaa;background:transparent">${state.lang === "zh" ? "暂无" : "—"}</li>`;

  if (s.updatedAt) {
    const d = new Date(s.updatedAt);
    document.getElementById("ai-updated").textContent =
      d.toLocaleString(state.lang === "zh" ? "zh-CN" : "ja-JP", { timeZone: "Asia/Tokyo" });
  }
}

// ===== 微信(WeChat)共有用サマリー: 中文テキストを生成してコピー =====
async function buildWechatSummary() {
  const s = state.data.summary || {};
  const block = s.summary_zh || s.summary_ja || {};
  const cats = state.data.cats || [];
  const imp = cats.filter(c => c.category === "improvement").length;
  const praise = cats.filter(c => c.category === "praise").length;
  const totalRev = (state.data.reviews || []).length;
  // 返品・不具合の件数: PAT があれば GitHub API から live 取得 (CDNキャッシュに影響されず正確)
  let openReturns = null, openDefects = null;
  const pat = (() => { try { return localStorage.getItem("shojiki-uploader-pat"); } catch (e) { return null; } })();
  const ISSUE_REPO = window.DEFECT_REPO;
  if (pat && ISSUE_REPO) {
    try {
      const live = [];
      for (let page = 1; page <= 3; page++) {
        const r = await fetch(`https://api.github.com/repos/${ISSUE_REPO}/issues?state=open&per_page=100&page=${page}`, {
          headers: { "Authorization": `Bearer ${pat}`, "Accept": "application/vnd.github+json" }, cache: "no-cache",
        });
        if (!r.ok) throw new Error("api " + r.status);
        const batch = await r.json();
        if (!Array.isArray(batch) || !batch.length) break;
        batch.forEach(it => { if (!it.pull_request) live.push(it); });
        if (batch.length < 100) break;
      }
      const isRet = it => (it.labels || []).some(l => (typeof l === "string" ? l : (l && l.name) || "").includes("return"));
      openReturns = live.filter(isRet).length;
      openDefects = live.filter(it => !isRet(it)).length;
    } catch (e) { openReturns = null; }
  }
  if (openReturns == null) {
    const issues = (state.data.merged.issues || []).filter(i => i.product === PRODUCT && i.state === "open");
    const isReturn = i => (i.labels || []).includes("type:return");
    openReturns = issues.filter(isReturn).length;
    openDefects = issues.filter(i => !isReturn(i)).length;
  }
  const date = new Date().toLocaleDateString("zh-CN", { timeZone: "Asia/Tokyo" });

  const L = [];
  L.push(`【SHOJIKI SH-J002 品质摘要 ${date}】`);
  L.push("");
  L.push(`📦 退货 ${openReturns}件 ・ 🔧 故障(内部) ${openDefects}件 ・ 💬 客户反馈 ${totalRev}条 (改善需求${imp}/好评${praise})`);
  L.push("");
  if (block.headline) L.push(`【最优先】${block.headline}`);
  if (block.narrative) L.push(block.narrative);
  const findings = block.key_findings || [];
  if (findings.length) {
    L.push("");
    L.push("主要趋势:");
    findings.forEach((f, i) => L.push(`${i + 1}. ${f.topic || ""}${f.count ? `(${f.count}条)` : ""}${f.finding ? `: ${f.finding}` : ""}`));
  }
  const actions = block.actions || [];
  if (actions.length) {
    L.push("");
    L.push("改善行动:");
    actions.forEach((a, i) => L.push(`${i + 1}. ${a}`));
  }
  L.push("");
  L.push("(GlowUp 品质看板 · 自动生成)");
  return L.join("\n");
}

(function bindWechatCopy() {
  const btn = document.getElementById("copy-wechat");
  if (!btn) return;
  btn.addEventListener("click", async () => {
    const msg = document.getElementById("copy-wechat-msg");
    if (msg) msg.textContent = state.lang === "zh" ? "生成中…" : "生成中…";
    const text = await buildWechatSummary();
    try {
      await navigator.clipboard.writeText(text);
      if (msg) { msg.textContent = state.lang === "zh" ? "已复制，可粘贴到微信" : "コピーしました(微信に貼り付け)"; setTimeout(() => { msg.textContent = ""; }, 4000); }
    } catch (e) {
      window.prompt(state.lang === "zh" ? "请复制以下内容:" : "コピーしてください:", text);
    }
  });
})();

function renderAll() {
  renderSummary();
  renderSales();
  renderCounts();
  renderClusterChart();
  renderLatestLists();
  renderUpdated();
}

loadAll().then(renderAll).catch(e => {
  console.error(e);
  document.getElementById("last-update").textContent = "読込失敗: " + e.message;
});
