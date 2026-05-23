// SHOJIKI factory dashboard
// Loads raw reviews + Claude categorization for both products from the
// same repo via raw.githubusercontent.com (works from China), merges by id,
// and renders a filterable list.

const REPO = "eda0825-spec/shojiki-rakuten-stats";
const BRANCH = "main";
// Use jsDelivr as primary (CDN with good China access via fastly + multi-region),
// raw.githubusercontent as fallback.
const SOURCES = (file) => [
  `https://cdn.jsdelivr.net/gh/${REPO}@${BRANCH}/${file}`,
  `https://raw.githubusercontent.com/${REPO}/${BRANCH}/${file}`,
];

const PRODUCTS = ["sh-j001", "sh-j002"];
const state = {
  product: "sh-j001",
  cat: "all",
  sev: "all",
  star: "all",
  topic: null,
  q: "",
  data: {}, // product -> { reviews:[], categorized: {id->row} }
};

// ----- fetch with fallback -----
async function fetchJSON(file) {
  let lastErr;
  for (const url of SOURCES(file)) {
    try {
      const r = await fetch(url, { cache: "no-cache" });
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
      return await r.json();
    } catch (e) {
      lastErr = e;
    }
  }
  throw lastErr;
}

async function loadProduct(product) {
  if (state.data[product]) return state.data[product];
  let reviewsBlk = { reviews: [], summary: {}, updatedAt: null };
  let catBlk = { results: [] };
  try {
    reviewsBlk = await fetchJSON(`reviews-${product}.json`);
  } catch (e) {
    console.warn(`reviews-${product}.json fetch failed`, e);
  }
  try {
    catBlk = await fetchJSON(`categorized-${product}.json`);
  } catch (e) {
    console.warn(`categorized-${product}.json fetch failed`, e);
  }
  const byId = {};
  for (const row of catBlk.results || []) byId[row.id] = row;
  state.data[product] = {
    reviews: reviewsBlk.reviews || [],
    summary: reviewsBlk.summary || {},
    updatedAt: reviewsBlk.updatedAt,
    categorizedUpdatedAt: catBlk.updatedAt,
    categorized: byId,
  };
  return state.data[product];
}

// ----- helpers -----
function stars(n) {
  n = Math.max(0, Math.min(5, Math.round(n || 0)));
  return "★".repeat(n) + "☆".repeat(5 - n);
}
function fmtDate(d) { return d || "—"; }
function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ----- rendering -----
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
    if (q) {
      const hay = [
        r.body, r.title, r.summary_ja, r.summary_zh, r.action_hint,
        ...(r.topics || []),
      ].filter(Boolean).join("\n").toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });

  // When no category filter is active, sort by priority: defects (severity high>med>low) first,
  // then improvements (severity high>med>low), then questions, praise, other, unclassified.
  // Within same bucket, newest date first.
  if (state.cat === "all") {
    const catOrder = { defect: 0, improvement: 1, question: 2, praise: 3, other: 4, unclassified: 5 };
    const sevOrder = { high: 0, medium: 1, low: 2, "n/a": 3 };
    filtered.sort((a, b) => {
      const ca = catOrder[a.category] ?? 6;
      const cb = catOrder[b.category] ?? 6;
      if (ca !== cb) return ca - cb;
      const sa = sevOrder[a.severity] ?? 4;
      const sb = sevOrder[b.severity] ?? 4;
      if (sa !== sb) return sa - sb;
      return (b.postDate || "").localeCompare(a.postDate || "");
    });
  } else {
    // Within a single category, sort by severity then date
    const sevOrder = { high: 0, medium: 1, low: 2, "n/a": 3 };
    filtered.sort((a, b) => {
      const sa = sevOrder[a.severity] ?? 4;
      const sb = sevOrder[b.severity] ?? 4;
      if (sa !== sb) return sa - sb;
      return (b.postDate || "").localeCompare(a.postDate || "");
    });
  }
  return filtered;
}

function renderStats(d, joined) {
  document.getElementById("stat-total").textContent = joined.length || "—";
  document.getElementById("stat-avg").textContent = d.summary?.rating ?? "—";
  const c = { defect: 0, improvement: 0, praise: 0, question: 0, other: 0, unclassified: 0 };
  for (const r of joined) c[r.category] = (c[r.category] || 0) + 1;
  document.getElementById("stat-defect").textContent = c.defect;
  document.getElementById("stat-improvement").textContent = c.improvement;
  document.getElementById("stat-praise").textContent = c.praise;
  document.getElementById("stat-question").textContent = c.question;
}

function renderTopics(joined, filteredCount) {
  const counts = new Map();
  for (const r of joined) {
    for (const t of r.topics || []) counts.set(t, (counts.get(t) || 0) + 1);
  }
  const sorted = [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 24);
  const wrap = document.getElementById("topics");
  const cloud = document.getElementById("topic-cloud");
  if (!sorted.length) { wrap.hidden = true; return; }
  wrap.hidden = false;
  cloud.innerHTML = sorted.map(([t, n]) =>
    `<span class="topic-pill${state.topic === t ? " active" : ""}" data-topic="${esc(t)}">${esc(t)}<span class="cnt">${n}</span></span>`
  ).join("");
  cloud.onclick = (e) => {
    const el = e.target.closest(".topic-pill");
    if (!el) return;
    const t = el.dataset.topic;
    state.topic = state.topic === t ? null : t;
    render();
  };
}

function renderList(rows) {
  const list = document.getElementById("list");
  const empty = document.getElementById("empty");
  document.getElementById("result-count").textContent = `${rows.length}件 / ${state.data[state.product]?.reviews.length || 0}件`;
  if (!rows.length) { list.innerHTML = ""; empty.hidden = false; return; }
  empty.hidden = true;
  const MAX_RENDER = 300;
  const slice = rows.slice(0, MAX_RENDER);
  list.innerHTML = slice.map((r) => `
    <article class="card" id="rev-${esc(r.id)}">
      <div class="card-head">
        <span class="stars">${stars(r.rating)}</span>
        <span class="cdate">${esc(fmtDate(r.postDate))}</span>
        ${r.category && r.category !== "unclassified" ? `<span class="badge cat-${esc(r.category)}">${labelCat(r.category)}</span>` : `<span class="badge cat-other">未分類</span>`}
        ${r.severity && r.severity !== "n/a" ? `<span class="badge sev-${esc(r.severity)}">${labelSev(r.severity)}</span>` : ""}
        <span class="cnick">— ${esc(r.nickname || "購入者")}</span>
      </div>

      ${(r.topics && r.topics.length) ? `<div class="topics-line">${r.topics.map(t => `<span class="tag">${esc(t)}</span>`).join("")}</div>` : ""}

      ${(r.summary_ja || r.summary_zh) ? `
        <div class="summary">
          <div class="sum-cell"><div class="lang">日本語要約 / JP</div>${esc(r.summary_ja || "—")}</div>
          <div class="sum-cell"><div class="lang">中文摘要 / 中国语</div>${esc(r.summary_zh || "—")}</div>
        </div>` : ""}

      ${r.action_hint ? `<div class="action-hint">${esc(r.action_hint)}</div>` : ""}

      ${r.title ? `<div style="font-weight:600;margin-bottom:4px">${esc(r.title)}</div>` : ""}
      <div class="body">${esc(r.body)}</div>
    </article>
  `).join("");
  if (rows.length > MAX_RENDER) {
    list.insertAdjacentHTML("beforeend",
      `<div class="empty">表示は最新${MAX_RENDER}件まで。フィルタや検索で絞り込んでください。<br>仅显示最近 ${MAX_RENDER} 条，请使用筛选或搜索。</div>`);
  }
  // expand body on click
  list.querySelectorAll(".body").forEach((el) => {
    el.addEventListener("click", () => el.classList.toggle("expanded"));
  });
}

function labelCat(c) {
  return { defect: "不具合", improvement: "改善要望", praise: "称賛", question: "質問", other: "その他" }[c] || c;
}
function labelSev(s) {
  return { high: "深刻度: 高", medium: "深刻度: 中", low: "深刻度: 低" }[s] || s;
}

function render() {
  const d = state.data[state.product];
  if (!d) return;
  const joined = joinReviewsAndCats(d);
  const filtered = applyFilters(joined);
  renderStats(d, joined);
  renderTopics(joined, filtered.length);
  renderList(filtered);

  const lastJp = d.updatedAt ? new Date(d.updatedAt).toLocaleString("ja-JP", { timeZone: "Asia/Tokyo" }) : "—";
  const catUpd = d.categorizedUpdatedAt ? new Date(d.categorizedUpdatedAt).toLocaleString("ja-JP", { timeZone: "Asia/Tokyo" }) : "未生成";
  document.getElementById("last-update").innerHTML =
    `レビュー取得: ${lastJp} ・ 分類: ${catUpd}`;
  document.getElementById("status-text").textContent =
    `${state.product.toUpperCase()} のデータを表示中`;
}

// ----- wire up -----
async function init() {
  // tabs
  document.querySelectorAll(".tab").forEach(btn => {
    btn.addEventListener("click", async () => {
      document.querySelectorAll(".tab").forEach(b => b.classList.toggle("active", b === btn));
      state.product = btn.dataset.product;
      state.topic = null;
      try { await loadProduct(state.product); render(); }
      catch (e) {
        document.getElementById("status-text").textContent = `読み込み失敗: ${e.message}`;
      }
    });
  });

  // chip groups
  function bindChips(groupSelector, key) {
    document.querySelectorAll(`${groupSelector} .chip`).forEach(btn => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(`${groupSelector} .chip`).forEach(b => b.classList.toggle("active", b === btn));
        state[key] = btn.dataset[key];
        render();
      });
    });
  }
  bindChips(".fgrp:nth-of-type(1)", "cat");
  bindChips(".fgrp:nth-of-type(2)", "sev");
  bindChips(".fgrp:nth-of-type(3)", "star");

  // search
  const q = document.getElementById("q");
  q.addEventListener("input", () => {
    state.q = q.value;
    render();
  });

  // initial load
  document.getElementById("status-text").textContent = "データ取得中…";
  try {
    await loadProduct("sh-j001");
    render();
    // preload j002 in background
    loadProduct("sh-j002").catch(() => {});
  } catch (e) {
    document.getElementById("status-text").textContent = `読み込み失敗: ${e.message}`;
  }
}

init();
