// Product-locked dashboard (single-product variant of docs/app.js).
// Reads window.PRODUCT etc. set by the host index.html.

const PRODUCT = window.PRODUCT;            // "sh-j002" or "sh-j001"
const DEFECT_REPO = window.DEFECT_REPO;
const RAKUTEN_ITEM = window.RAKUTEN_ITEM;

const REPO = "eda0825-spec/shojiki-rakuten-stats";
const BRANCH = "main";
const SOURCES = (file) => [
  `https://cdn.jsdelivr.net/gh/${REPO}@${BRANCH}/${file}`,
  `https://raw.githubusercontent.com/${REPO}/${BRANCH}/${file}`,
];

const state = {
  cat: "all", sev: "all", star: "all", topic: null, q: "",
  data: null, // { reviews, summary, updatedAt, categorizedUpdatedAt, categorized }
  lastFiltered: [],
};

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

function renderTopics(joined) {
  const counts = new Map();
  for (const r of joined) for (const t of r.topics || []) counts.set(t, (counts.get(t) || 0) + 1);
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
    `<span style="display:inline-block;width:10px;height:10px;background:${colDefect};vertical-align:middle;margin-right:4px"></span>不具合 / 故障` +
    ` &nbsp; <span style="display:inline-block;width:10px;height:10px;background:${colImprovement};vertical-align:middle;margin-right:4px"></span>改善要望 / 改善需求` +
    ` &nbsp; <span style="opacity:0.6">${recent.length}ヶ月表示</span>`;
}

function labelCat(c) {
  return { defect: "不具合", improvement: "改善要望", praise: "称賛", question: "質問", other: "その他" }[c] || c;
}
function labelSev(s) {
  return { high: "深刻度: 高", medium: "深刻度: 中", low: "深刻度: 低" }[s] || s;
}

function renderList(rows) {
  const list = document.getElementById("list");
  const empty = document.getElementById("empty");
  document.getElementById("result-count").textContent = `${rows.length}件 / ${state.data?.reviews.length || 0}件`;
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
        <button class="chip" style="margin-left:6px" data-escalate="${esc(r.id)}" title="この声を defect Issue として起票 / 起 Issue">📋 Issue化</button>
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
  // [J002] or [J001] derived directly from PRODUCT
  const titlePrefix = "[" + PRODUCT.replace("sh-", "").toUpperCase() + "]";
  const titleJa = (c.summary_ja || r.body || "顧客レビュー").split("\n")[0].slice(0, 60);
  const title = [titlePrefix, "[顧客]", sevTag, titleJa].filter(Boolean).join(" ").replace(/\s+/g, " ").trim();

  const params = new URLSearchParams();
  params.set("template", "defect.yml");
  params.set("title", title);
  params.set("source", "顧客レビュー / 客户评论");
  if (sev === "high") params.set("severity", "高 / 高 (安全性 - 発火/感電/怪我リスク, 安全 - 起火/触电/受伤风险)");
  else if (sev === "medium") params.set("severity", "中 / 中 (基本機能停止, 基本功能停止)");
  else if (sev === "low") params.set("severity", "低 / 低 (軽微な不便, 轻微不便)");
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
  if (!rows.length) { alert("エクスポートする結果がありません / 没有可导出的结果"); return; }
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

function render() {
  if (!state.data) return;
  const joined = joinReviewsAndCats(state.data);
  const filtered = applyFilters(joined);
  renderStats(state.data, joined);
  renderTopics(joined);
  renderTrend(joined);
  renderList(filtered);
  state.lastFiltered = filtered;
  const lastJp = state.data.updatedAt ? new Date(state.data.updatedAt).toLocaleString("ja-JP", { timeZone: "Asia/Tokyo" }) : "—";
  const catUpd = state.data.categorizedUpdatedAt ? new Date(state.data.categorizedUpdatedAt).toLocaleString("ja-JP", { timeZone: "Asia/Tokyo" }) : "未生成";
  document.getElementById("last-update").innerHTML = `レビュー取得: ${lastJp} ・ 分類: ${catUpd}`;
  document.getElementById("status-text").textContent = `${(window.PRODUCT_LABEL || PRODUCT).toUpperCase()} のデータを表示中`;
}

async function init() {
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
  const q = document.getElementById("q");
  q.addEventListener("input", () => { state.q = q.value; render(); });
  document.getElementById("export-csv").addEventListener("click", exportCSV);
  document.getElementById("status-text").textContent = "データ取得中…";
  try {
    await loadData();
    render();
  } catch (e) {
    document.getElementById("status-text").textContent = `読み込み失敗: ${e.message}`;
  }
}
init();
