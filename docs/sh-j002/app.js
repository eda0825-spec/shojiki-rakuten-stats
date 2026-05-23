// Product-locked dashboard (single-product variant of docs/app.js).
// Bilingual: toggle between ja and zh via header switch.
// Reads window.PRODUCT etc. set by the host index.html.

const PRODUCT = window.PRODUCT;
const DEFECT_REPO = window.DEFECT_REPO;
const RAKUTEN_ITEM = window.RAKUTEN_ITEM;

const REPO = "eda0825-spec/shojiki-rakuten-stats";
const BRANCH = "main";
const SOURCES = (file) => [
  `https://cdn.jsdelivr.net/gh/${REPO}@${BRANCH}/${file}`,
  `https://raw.githubusercontent.com/${REPO}/${BRANCH}/${file}`,
];

const LS_LANG_KEY = "shojiki-dashboard-lang";

const state = {
  lang: (typeof localStorage !== "undefined" && localStorage.getItem(LS_LANG_KEY)) || "ja",
  cat: "defect", sev: "all", star: "all", topic: null, q: "",
  cluster: null,  // selected cluster key
  data: null,
  lastFiltered: [],
};

// Cluster groups — multiple raw topics map to one user-facing cluster
const CLUSTERS = [
  { key: "charging", emoji: "🔋", name_ja: "充電・バッテリー", name_zh: "充电·电池", topics: ["バッテリー", "充電", "充電端子", "充電スタンド", "充電台", "電気系統", "電池"] },
  { key: "weight",   emoji: "⚖️", name_ja: "重量・サイズ",     name_zh: "重量·尺寸",   topics: ["重量", "軽量", "コンパクト", "本体形状"] },
  { key: "suction",  emoji: "💨", name_ja: "吸引力",          name_zh: "吸力",        topics: ["吸引力", "吸力", "基本機能"] },
  { key: "noise",    emoji: "🔊", name_ja: "音・静音性",      name_zh: "噪音·静音",   topics: ["騒音", "静音性", "動作音", "音"] },
  { key: "dustcup",  emoji: "🗑️", name_ja: "ダストカップ",   name_zh: "集尘杯",      topics: ["ダストカップ", "集尘杯", "ゴミ捨て"] },
  { key: "roller",   emoji: "🪥", name_ja: "ローラー・ヘッド", name_zh: "滚刷·吸头",  topics: ["ローラー", "ヘッド", "滚刷", "吸头", "ノズル", "髪の毛", "頭髪", "毛絡まり"] },
  { key: "filter",   emoji: "🧽", name_ja: "フィルター・お手入れ", name_zh: "过滤器·保养", topics: ["フィルター", "过滤器", "メンテナンス", "お手入れ"] },
  { key: "operation",emoji: "🎛️", name_ja: "操作・ボタン",   name_zh: "操作·按钮",   topics: ["操作性", "操作ボタン", "スイッチ", "ハンディモード", "ボタン"] },
  { key: "stand",    emoji: "📐", name_ja: "スタンド・自立",  name_zh: "支架·自立",   topics: ["自立機能", "自走機能", "スタンド", "転倒耐性", "壁掛け"] },
  { key: "design",   emoji: "🎨", name_ja: "デザイン・外装",  name_zh: "外观·外壳",   topics: ["デザイン", "外装", "外壳", "カラー", "色"] },
  { key: "safety",   emoji: "⚠️", name_ja: "安全性",         name_zh: "安全性",      topics: ["安全性", "怪我", "発火", "感電"] },
  { key: "carpet",   emoji: "🏠", name_ja: "床・カーペット",  name_zh: "地板·地毯",   topics: ["カーペット対応", "カーペット", "絨毯対応", "床"] },
  { key: "support",  emoji: "💬", name_ja: "サポート対応",    name_zh: "客服对应",    topics: ["サポート対応", "サポート"] },
  { key: "package",  emoji: "📦", name_ja: "梱包・配送",      name_zh: "包装·配送",   topics: ["梱包", "配送"] },
  { key: "assembly", emoji: "🔧", name_ja: "組み立て・接続",  name_zh: "组装·连接",   topics: ["組み立て", "パイプ接続", "ロック機構"] },
  { key: "light",    emoji: "💡", name_ja: "LED・ライト",     name_zh: "LED·灯光",   topics: ["LEDライト", "ライト", "LED灯", "LED"] },
];
// quick lookup: topic JP → cluster key
const TOPIC_TO_CLUSTER = (() => {
  const m = new Map();
  for (const c of CLUSTERS) for (const t of c.topics) m.set(t, c.key);
  return m;
})();

// --- i18n strings ---
const I18N = {
  ja: {
    catLabels: { defect: "不具合", improvement: "改善要望", praise: "称賛", question: "質問", other: "その他", unclassified: "未分類" },
    sevLabels: { high: "深刻度: 高", medium: "深刻度: 中", low: "深刻度: 低" },
    summaryLabel_ja: "日本語要約", summaryLabel_zh: "中文摘要",
    poster: "購入者",
    expandHint: "▾ 全文を見る",
    notranslated: "(対策案は日本語のみ表示)",
    issueBtn: "📋 Issue化",
    issueBtnTitle: "この声を defect Issue として起票",
    csvNoRows: "エクスポートする結果がありません",
    statusLoading: "データ取得中…",
    statusShowing: (p) => `${p} のデータを表示中`,
    lastUpdated: (rev, cat) => `レビュー取得: ${rev} ・ 分類: ${cat}`,
    notGenerated: "未生成",
    monthSuffix: "ヶ月表示",
    legendDefect: "不具合",
    legendImp: "改善要望",
    overflow: (n) => `表示は最新${n}件まで。フィルタや検索で絞り込んでください。`,
    countSuffix: (a, b) => `${a}件 / ${b}件`,
  },
  zh: {
    catLabels: { defect: "故障", improvement: "改善需求", praise: "好评", question: "提问", other: "其他", unclassified: "未分类" },
    sevLabels: { high: "严重度: 高", medium: "严重度: 中", low: "严重度: 低" },
    summaryLabel_ja: "日语摘要", summaryLabel_zh: "中文摘要",
    poster: "购买者",
    expandHint: "▾ 查看全文",
    notranslated: "(对策建议仅日语显示)",
    issueBtn: "📋 起 Issue",
    issueBtnTitle: "将此评论登记为 defect Issue",
    csvNoRows: "没有可导出的结果",
    statusLoading: "加载中…",
    statusShowing: (p) => `正在显示 ${p} 的数据`,
    lastUpdated: (rev, cat) => `评论获取: ${rev} ・ 分类: ${cat}`,
    notGenerated: "未生成",
    monthSuffix: "个月",
    legendDefect: "故障",
    legendImp: "改善需求",
    overflow: (n) => `仅显示最近 ${n} 条，请使用筛选或搜索缩小范围。`,
    countSuffix: (a, b) => `${a} / ${b} 条`,
  },
};
const t = () => I18N[state.lang];

// --- common JP topic → ZH ---
const TOPIC_ZH = {
  "吸引力": "吸力", "重量": "重量", "操作性": "操作性", "ダストカップ": "集尘杯",
  "ヘッド": "吸头", "バッテリー": "电池", "自立機能": "自立功能", "収納": "收纳",
  "騒音": "噪音", "自走機能": "自驱动", "デザイン": "外观", "ローラー": "滚刷",
  "静音性": "静音性", "耐久性": "耐久性", "LEDライト": "LED灯", "髪の毛": "头发",
  "充電": "充电", "収納性": "收纳性", "カーペット対応": "地毯适用", "カーペット": "地毯",
  "ノズル": "吸嘴", "軽量": "轻量", "ライト": "灯", "動作音": "运行声音",
  "充電スタンド": "充电底座", "充電端子": "充电接口", "サポート対応": "客服对应",
  "外装": "外壳", "梱包": "包装", "組み立て": "组装", "フィルター": "过滤器",
  "コンパクト": "紧凑", "スタンド": "支架", "付属品": "配件", "電気系統": "电气系统",
  "本体形状": "机身形状", "安全性": "安全性", "怪我": "受伤", "モーター": "电机",
  "操作ボタン": "操作按钮", "スイッチ": "开关", "ハンディモード": "手持模式",
  "絨毯対応": "地毯适用", "転倒耐性": "倒下耐性", "パイプ接続": "管口接合",
  "ロック機構": "锁紧机构", "基本機能": "基本功能", "接触不良": "接触不良",
};
const tx = (jp) => state.lang === "zh" ? (TOPIC_ZH[jp] || jp) : jp;

async function fetchJSON(file) {
  let lastErr;
  for (const url of SOURCES(file)) {
    try {
      const r = await fetch(url, { cache: "no-cache" });
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
      return await r.json();
    } catch (e) { lastErr = e; }
  }
  throw lastErr;
}

async function loadData() {
  let reviewsBlk = { reviews: [], summary: {}, updatedAt: null };
  let catBlk = { results: [] };
  try { reviewsBlk = await fetchJSON(`reviews-${PRODUCT}.json`); } catch (e) { console.warn(e); }
  try { catBlk = await fetchJSON(`categorized-${PRODUCT}.json`); } catch (e) { console.warn(e); }
  const byId = {};
  for (const row of catBlk.results || []) byId[row.id] = row;
  state.data = {
    reviews: reviewsBlk.reviews || [],
    summary: reviewsBlk.summary || {},
    updatedAt: reviewsBlk.updatedAt,
    categorizedUpdatedAt: catBlk.updatedAt,
    categorized: byId,
  };
}

function stars(n) {
  n = Math.max(0, Math.min(5, Math.round(n || 0)));
  return "★".repeat(n) + "☆".repeat(5 - n);
}
function fmtDate(d) { return d || "—"; }
function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function joinReviewsAndCats(d) {
  const out = [];
  for (const r of d.reviews) {
    const c = d.categorized[r.id];
    out.push({ ...r, ...(c || { category: "unclassified", severity: "n/a", summary_ja: "", summary_zh: "", topics: [], action_hint: null }) });
  }
  return out;
}

function applyFilters(rows) {
  const q = state.q.trim().toLowerCase();
  const filtered = rows.filter((r) => {
    if (state.cat !== "all" && r.category !== state.cat) return false;
    if (state.sev !== "all" && r.severity !== state.sev) return false;
    if (state.star !== "all" && String(r.rating) !== state.star) return false;
    if (state.topic && !(r.topics || []).includes(state.topic)) return false;
    if (state.cluster) {
      const topics = r.topics || [];
      const inCluster = topics.some(t => TOPIC_TO_CLUSTER.get(t) === state.cluster);
      if (!inCluster) return false;
    }
    if (q) {
      const hay = [r.body, r.title, r.summary_ja, r.summary_zh, r.action_hint, ...(r.topics || [])]
        .filter(Boolean).join("\n").toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
  if (state.cat === "all") {
    const catOrder = { defect: 0, improvement: 1, question: 2, praise: 3, other: 4, unclassified: 5 };
    const sevOrder = { high: 0, medium: 1, low: 2, "n/a": 3 };
    filtered.sort((a, b) => {
      const ca = catOrder[a.category] ?? 6, cb = catOrder[b.category] ?? 6;
      if (ca !== cb) return ca - cb;
      const sa = sevOrder[a.severity] ?? 4, sb = sevOrder[b.severity] ?? 4;
      if (sa !== sb) return sa - sb;
      return (b.postDate || "").localeCompare(a.postDate || "");
    });
  } else {
    const sevOrder = { high: 0, medium: 1, low: 2, "n/a": 3 };
    filtered.sort((a, b) => {
      const sa = sevOrder[a.severity] ?? 4, sb = sevOrder[b.severity] ?? 4;
      if (sa !== sb) return sa - sb;
      return (b.postDate || "").localeCompare(a.postDate || "");
    });
  }
  return filtered;
}

function renderClusterChart(joined) {
  const buckets = new Map();
  for (const c of CLUSTERS) buckets.set(c.key, { defect: 0, improvement: 0 });
  for (const r of joined) {
    if (r.category !== "defect" && r.category !== "improvement") continue;
    const seenClusters = new Set();
    for (const tp of r.topics || []) {
      const ck = TOPIC_TO_CLUSTER.get(tp);
      if (!ck || seenClusters.has(ck)) continue;
      seenClusters.add(ck);
      buckets.get(ck)[r.category]++;
    }
  }
  const ranked = CLUSTERS
    .map(c => ({ ...c, ...buckets.get(c.key) }))
    .filter(c => (c.defect + c.improvement) > 0)
    .sort((a, b) => (b.defect + b.improvement) - (a.defect + a.improvement))
    .slice(0, 12);

  const section = document.getElementById("cluster-chart-section");
  const rowsWrap = document.getElementById("cluster-chart-rows");
  if (!section || !rowsWrap) return;
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
      <button class="cluster-row ${state.cluster === c.key ? 'active' : ''}" data-cluster="${c.key}">
        <span class="cluster-row-label"><span class="emo">${c.emoji}</span><span class="name">${esc(name)}</span></span>
        <span class="cluster-row-bar">
          ${c.defect > 0 ? `<span class="seg-d" style="width:${defectPct}%"></span>` : ""}
          ${c.improvement > 0 ? `<span class="seg-i" style="width:${impPct}%"></span>` : ""}
          ${c.defect >= max * 0.08 ? `<span class="lbl-d">${c.defect}</span>` : ""}
          ${c.improvement >= max * 0.08 ? `<span class="lbl-i" style="left:${defectPct}%;right:auto">${c.improvement}</span>` : ""}
        </span>
        <span class="cluster-row-count">${total}</span>
      </button>`;
  }).join("");

  rowsWrap.onclick = (e) => {
    const btn = e.target.closest("[data-cluster]");
    if (!btn) return;
    const k = btn.dataset.cluster;
    state.cluster = state.cluster === k ? null : k;
    if (state.cluster) {
      state.cat = "all";
      document.querySelectorAll(".simple-filter .big-chip").forEach(b => b.classList.toggle("active", b.dataset.cat === "all"));
    }
    render();
  };
}

function renderClusters(joined) {
  // Group reviews by cluster, count defect+improvement only
  const buckets = new Map();
  for (const c of CLUSTERS) buckets.set(c.key, { defect: 0, improvement: 0, samples: [] });
  for (const r of joined) {
    if (r.category !== "defect" && r.category !== "improvement") continue;
    const topics = r.topics || [];
    const seenClusters = new Set();
    for (const tp of topics) {
      const ck = TOPIC_TO_CLUSTER.get(tp);
      if (!ck || seenClusters.has(ck)) continue;
      seenClusters.add(ck);
      const b = buckets.get(ck);
      b[r.category]++;
      if (b.samples.length < 5) {
        // pick best sample (severity high > medium > low, then short summary)
        const sumKey = state.lang === "zh" ? "summary_zh" : "summary_ja";
        const s = r[sumKey] || r[state.lang === "zh" ? "summary_ja" : "summary_zh"] || "";
        if (s) b.samples.push({ text: s, severity: r.severity, category: r.category });
      }
    }
  }
  // sort samples within each bucket: defect > improvement, high > medium > low
  const sevRank = { high: 0, medium: 1, low: 2, "n/a": 3 };
  const catRank = { defect: 0, improvement: 1 };
  for (const b of buckets.values()) {
    b.samples.sort((a, b2) => {
      const ca = catRank[a.category] ?? 9, cb = catRank[b2.category] ?? 9;
      if (ca !== cb) return ca - cb;
      return (sevRank[a.severity] ?? 9) - (sevRank[b2.severity] ?? 9);
    });
    b.samples = b.samples.slice(0, 2);
  }
  // Rank clusters by total (defect+improvement), descending
  const ranked = CLUSTERS
    .map(c => ({ ...c, ...buckets.get(c.key) }))
    .filter(c => (c.defect + c.improvement) > 0)
    .sort((a, b) => (b.defect + b.improvement) - (a.defect + a.improvement))
    .slice(0, 9);

  const grid = document.getElementById("clusters-grid");
  const section = document.getElementById("clusters-section");
  if (!ranked.length) { section.hidden = true; return; }
  section.hidden = false;
  const labels = t();
  grid.innerHTML = ranked.map(c => {
    const name = state.lang === "zh" ? c.name_zh : c.name_ja;
    const total = c.defect + c.improvement;
    const dLab = state.lang === "zh" ? "故障" : "不具合";
    const iLab = state.lang === "zh" ? "改善" : "改善";
    return `
      <button class="cluster-card ${state.cluster === c.key ? 'active' : ''}" data-cluster="${c.key}">
        <div class="cluster-head">
          <span class="cluster-emoji">${c.emoji}</span>
          <span class="cluster-name">${esc(name)}</span>
          <span class="cluster-count">${total}</span>
        </div>
        <div class="cluster-breakdown">
          ${c.defect > 0 ? `<span class="b-d">● ${dLab} ${c.defect}</span>` : ""}
          ${c.improvement > 0 ? `<span class="b-i">● ${iLab} ${c.improvement}</span>` : ""}
        </div>
        ${c.samples.length ? `<div class="cluster-samples"><ul>${c.samples.map(s => `<li>${esc(s.text)}</li>`).join("")}</ul></div>` : ""}
      </button>`;
  }).join("");
  grid.onclick = (e) => {
    const btn = e.target.closest("[data-cluster]");
    if (!btn) return;
    const k = btn.dataset.cluster;
    state.cluster = state.cluster === k ? null : k;
    // when selecting a cluster, also reset cat filter to "all" so we see everything in that cluster
    if (state.cluster) {
      state.cat = "all";
      document.querySelectorAll(".simple-filter .big-chip").forEach(b => b.classList.toggle("active", b.dataset.cat === "all"));
    }
    render();
  };
}

function renderStats(d, joined) {
  document.getElementById("stat-total").textContent = joined.length || "—";
  const c = { defect: 0, improvement: 0, praise: 0, question: 0, other: 0, unclassified: 0 };
  for (const r of joined) c[r.category] = (c[r.category] || 0) + 1;
  document.getElementById("stat-defect").textContent = c.defect;
  document.getElementById("stat-improvement").textContent = c.improvement;
  document.getElementById("stat-praise").textContent = c.praise;
}

function renderTopics(joined) {
  const counts = new Map();
  for (const r of joined) for (const tp of r.topics || []) counts.set(tp, (counts.get(tp) || 0) + 1);
  const sorted = [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 24);
  const wrap = document.getElementById("topics");
  const cloud = document.getElementById("topic-cloud");
  if (!sorted.length) { wrap.hidden = true; return; }
  wrap.hidden = false;
  cloud.innerHTML = sorted.map(([tp, n]) =>
    `<span class="topic-pill${state.topic === tp ? " active" : ""}" data-topic="${esc(tp)}">${esc(tx(tp))}<span class="cnt">${n}</span></span>`
  ).join("");
  cloud.onclick = (e) => {
    const el = e.target.closest(".topic-pill");
    if (!el) return;
    const tp = el.dataset.topic;
    state.topic = state.topic === tp ? null : tp;
    render();
  };
}

function renderTrend(joined) {
  const buckets = new Map();
  for (const r of joined) {
    if (!r.postDate) continue;
    if (r.category !== "defect" && r.category !== "improvement") continue;
    const ym = r.postDate.slice(0, 7);
    if (!buckets.has(ym)) buckets.set(ym, { defect: 0, improvement: 0 });
    buckets.get(ym)[r.category]++;
  }
  const keys = [...buckets.keys()].sort();
  const wrap = document.getElementById("trend");
  if (keys.length < 2) { wrap.hidden = true; return; }
  wrap.hidden = false;
  const recent = keys.slice(-18);
  const canvas = document.getElementById("trend-chart");
  const ctx = canvas.getContext("2d");
  const w = canvas.width, h = canvas.height;
  const padL = 40, padB = 24, padR = 12, padT = 8;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, w, h);
  const maxV = Math.max(1, ...recent.flatMap(k => [buckets.get(k).defect + buckets.get(k).improvement]));
  const yMax = Math.ceil(maxV * 1.15);
  ctx.strokeStyle = "#eee"; ctx.fillStyle = "#999";
  ctx.font = "10px -apple-system, sans-serif";
  for (let i = 0; i <= 4; i++) {
    const y = padT + (h - padT - padB) * (1 - i / 4);
    ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(w - padR, y); ctx.stroke();
    ctx.fillText(String(Math.round(yMax * i / 4)), 8, y + 3);
  }
  const colDefect = "#d93b3b", colImprovement = "#d98330";
  const barW = (w - padL - padR) / recent.length;
  recent.forEach((ym, i) => {
    const v = buckets.get(ym);
    const x = padL + i * barW;
    const totalH = (v.defect + v.improvement) / yMax * (h - padT - padB);
    const defectH = v.defect / yMax * (h - padT - padB);
    ctx.fillStyle = colImprovement;
    ctx.fillRect(x + 3, h - padB - totalH + defectH, barW - 6, totalH - defectH);
    ctx.fillStyle = colDefect;
    ctx.fillRect(x + 3, h - padB - totalH, barW - 6, defectH);
    ctx.fillStyle = "#999";
    if (i % Math.ceil(recent.length / 8) === 0 || i === recent.length - 1) {
      ctx.fillText(ym.slice(2), x + 4, h - 8);
    }
  });
  document.getElementById("trend-legend").innerHTML =
    `<span style="display:inline-block;width:10px;height:10px;background:${colDefect};vertical-align:middle;margin-right:4px"></span>${esc(t().legendDefect)}` +
    ` &nbsp; <span style="display:inline-block;width:10px;height:10px;background:${colImprovement};vertical-align:middle;margin-right:4px"></span>${esc(t().legendImp)}` +
    ` &nbsp; <span style="opacity:0.6">${recent.length}${esc(t().monthSuffix)}</span>`;
}

function renderList(rows) {
  const list = document.getElementById("list");
  const empty = document.getElementById("empty");
  document.getElementById("result-count").textContent = t().countSuffix(rows.length, state.data?.reviews.length || 0);
  if (!rows.length) { list.innerHTML = ""; empty.hidden = false; return; }
  empty.hidden = true;
  const MAX_RENDER = 300;
  const slice = rows.slice(0, MAX_RENDER);
  const labels = t();
  list.innerHTML = slice.map((r) => {
    const catLab = labels.catLabels[r.category] || labels.catLabels.unclassified;
    const sevLab = r.severity && r.severity !== "n/a" ? labels.sevLabels[r.severity] : "";
    const showJa = state.lang === "ja";
    const showZh = state.lang === "zh";
    const removedLab = state.lang === "zh" ? "已删除" : "削除済み";
    return `
    <article class="card ${r.removed_at ? 'card--removed' : ''}" id="rev-${esc(r.id)}">
      <div class="card-head">
        <span class="stars">${stars(r.rating)}</span>
        <span class="cdate">${esc(fmtDate(r.postDate))}</span>
        <span class="badge cat-${esc(r.category)}">${esc(catLab)}</span>
        ${sevLab ? `<span class="badge sev-${esc(r.severity)}">${esc(sevLab)}</span>` : ""}
        ${r.removed_at ? `<span class="badge badge-removed" title="楽天から削除されました: ${esc(r.removed_at)}">🗑 ${esc(removedLab)}</span>` : ""}
        <span class="cnick">— ${esc(r.nickname || labels.poster)}</span>
        <button class="chip" style="margin-left:6px" data-escalate="${esc(r.id)}" title="${esc(labels.issueBtnTitle)}">${esc(labels.issueBtn)}</button>
      </div>
      ${(r.topics && r.topics.length) ? `<div class="topics-line">${r.topics.map(tp => `<span class="tag">${esc(tx(tp))}</span>`).join("")}</div>` : ""}
      ${(r.summary_ja || r.summary_zh) ? `
        <div class="summary">
          <div class="sum-cell ja"><div class="lang">${esc(labels.summaryLabel_ja)}</div>${esc(r.summary_ja || "—")}</div>
          <div class="sum-cell zh"><div class="lang">${esc(labels.summaryLabel_zh)}</div>${esc(r.summary_zh || "—")}</div>
        </div>` : ""}
      ${r.action_hint && showJa ? `<div class="action-hint">${esc(r.action_hint)}</div>` : ""}
      ${r.action_hint && showZh ? `<div class="action-hint" title="${esc(r.action_hint)}">${esc(labels.notranslated)}</div>` : ""}
      ${r.title ? `<div style="font-weight:600;margin-bottom:4px">${esc(r.title)}</div>` : ""}
      <div class="body">${esc(r.body)}</div>
    </article>`;
  }).join("");
  if (rows.length > MAX_RENDER) {
    list.insertAdjacentHTML("beforeend", `<div class="empty">${esc(labels.overflow(MAX_RENDER))}</div>`);
  }
  list.querySelectorAll(".body").forEach((el) => el.addEventListener("click", () => el.classList.toggle("expanded")));
  list.querySelectorAll("[data-escalate]").forEach((btn) => {
    btn.addEventListener("click", (e) => { e.stopPropagation(); escalateReview(btn.dataset.escalate); });
  });
}

function escalateReview(id) {
  const r = state.data.reviews.find(x => x.id === id);
  const c = state.data.categorized[id] || {};
  if (!r) return;
  const sev = c.severity || "n/a";
  const sevTag = ({ high: "[高]", medium: "[中]", low: "[低]" })[sev] || "";
  const titlePrefix = "[" + PRODUCT.replace("sh-", "").toUpperCase() + "]";
  const titleJa = (c.summary_ja || r.body || "顧客レビュー").split("\n")[0].slice(0, 60);
  const title = [titlePrefix, "[顧客]", sevTag, titleJa].filter(Boolean).join(" ").replace(/\s+/g, " ").trim();

  const params = new URLSearchParams();
  params.set("template", "defect.yml");
  params.set("title", title);
  params.set("source", "顧客レビュー");
  if (sev === "high") params.set("severity", "高");
  else if (sev === "medium") params.set("severity", "中");
  else if (sev === "low") params.set("severity", "低");
  params.set("symptom_ja", c.summary_ja || "");
  params.set("symptom_zh", c.summary_zh || "");
  params.set("suspected_cause", c.action_hint || "");
  const reviewUrl = `https://review.rakuten.co.jp/item/1/437323_${RAKUTEN_ITEM}/`;
  params.set("extra",
    `**楽天レビューより自動転載**\n\n` +
    `> ${(r.body || "").trim().replace(/\n/g, "\n> ")}\n\n` +
    `★ ${r.rating} ・ ${r.postDate} ・ ${r.nickname || "—"}\n` +
    (c.topics?.length ? `部位/部位: ${c.topics.join(", ")}\n` : "") +
    `\n元レビュー: ${reviewUrl}\nReview ID: \`${r.id}\``
  );
  window.open(`https://github.com/${DEFECT_REPO}/issues/new?${params.toString()}`, "_blank");
}

function exportCSV() {
  const rows = state.lastFiltered || [];
  if (!rows.length) { alert(t().csvNoRows); return; }
  const header = ["id", "product", "rating", "postDate", "nickname", "category", "severity", "summary_ja", "summary_zh", "topics", "action_hint", "body"];
  const escCsv = (v) => {
    if (v == null) return "";
    const s = String(v).replace(/"/g, '""');
    return /[",\n]/.test(s) ? `"${s}"` : s;
  };
  const lines = [header.join(",")];
  for (const r of rows) {
    lines.push([r.id, PRODUCT, r.rating, r.postDate, r.nickname, r.category, r.severity, r.summary_ja, r.summary_zh, (r.topics || []).join("|"), r.action_hint, r.body].map(escCsv).join(","));
  }
  const csv = "﻿" + lines.join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `shojiki-reviews-${PRODUCT}-${new Date().toISOString().slice(0,10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

function applyLang() {
  document.body.classList.toggle("lang-ja", state.lang === "ja");
  document.body.classList.toggle("lang-zh", state.lang === "zh");
  // search placeholder
  const q = document.getElementById("q");
  if (q) q.placeholder = q.dataset[`placeholder${state.lang.charAt(0).toUpperCase()}${state.lang.slice(1)}`] || "";
  // toggle visual
  document.querySelectorAll(".lang-toggle button").forEach(b => b.classList.toggle("active", b.dataset.lang === state.lang));
}

function render() {
  if (!state.data) return;
  applyLang();
  const joined = joinReviewsAndCats(state.data);
  const filtered = applyFilters(joined);
  renderStats(state.data, joined);
  renderClusterChart(joined);
  renderClusters(joined);
  renderTopics(joined);
  renderTrend(joined);
  renderList(filtered);
  state.lastFiltered = filtered;
  const lastJp = state.data.updatedAt ? new Date(state.data.updatedAt).toLocaleString(state.lang === "zh" ? "zh-CN" : "ja-JP", { timeZone: "Asia/Tokyo" }) : "—";
  const catUpd = state.data.categorizedUpdatedAt ? new Date(state.data.categorizedUpdatedAt).toLocaleString(state.lang === "zh" ? "zh-CN" : "ja-JP", { timeZone: "Asia/Tokyo" }) : t().notGenerated;
  document.getElementById("last-update").innerHTML = t().lastUpdated(lastJp, catUpd);
  document.getElementById("status-text").textContent = t().statusShowing(window.PRODUCT_LABEL || PRODUCT);
}

async function init() {
  applyLang();

  // language toggle
  document.querySelectorAll(".lang-toggle button").forEach(b => {
    b.addEventListener("click", () => {
      state.lang = b.dataset.lang;
      try { localStorage.setItem(LS_LANG_KEY, state.lang); } catch (e) {}
      render();
    });
  });

  // Primary filter: simple-filter (big chips, category only)
  document.querySelectorAll(".simple-filter .big-chip").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".simple-filter .big-chip").forEach(b => b.classList.toggle("active", b === btn));
      state.cat = btn.dataset.cat;
      state.cluster = null;   // category filter clears cluster
      render();
    });
  });
  // Advanced filters inside the <details>: severity, star
  function bindAdvChips(label, key) {
    document.querySelectorAll(`.advanced-body .fgrp .chip[data-${key}]`).forEach(btn => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(`.advanced-body .fgrp .chip[data-${key}]`).forEach(b => b.classList.toggle("active", b === btn));
        state[key] = btn.dataset[key];
        render();
      });
    });
  }
  bindAdvChips("severity", "sev");
  bindAdvChips("star", "star");
  const q = document.getElementById("q");
  q.addEventListener("input", () => { state.q = q.value; render(); });
  document.getElementById("export-csv").addEventListener("click", exportCSV);
  document.getElementById("status-text").textContent = t().statusLoading;
  try {
    await loadData();
    render();
  } catch (e) {
    document.getElementById("status-text").textContent = `読み込み失敗 / 加载失败: ${e.message}`;
  }
}
init();
