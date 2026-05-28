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
  const urls = [
    `https://cdn.jsdelivr.net/gh/${REPO}@${BRANCH}/${file}`,
    `https://raw.githubusercontent.com/${REPO}/${BRANCH}/${file}`,
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
  const [reviews, cats, merged, sales] = await Promise.all([
    fetchJSON(`reviews-${PRODUCT}.json`).catch(() => ({ reviews: [] })),
    fetchJSON(`categorized-${PRODUCT}.json`).catch(() => ({ results: [] })),
    fetchJSON(`docs/data/defects-merged.json`).catch(() => ({ issues: [] })),
    fetchJSON(`sales-summary.json`).catch(() => null),
  ]);
  state.data.reviews = reviews.reviews || [];
  state.data.cats = cats.results || [];
  state.data.merged = merged;
  state.data.sales = sales;
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
    const seen = new Set();
    for (const tp of r.topics || []) {
      const ck = TOPIC_TO_CLUSTER.get(tp);
      if (!ck || seen.has(ck)) continue;
      seen.add(ck);
      buckets.get(ck)[r.category]++;
    }
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
  const defects = issues.filter(i => !isReturn(i)).slice(0, 5);
  const returns = issues.filter(i =>  isReturn(i)).slice(0, 5);

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

function renderAll() {
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
