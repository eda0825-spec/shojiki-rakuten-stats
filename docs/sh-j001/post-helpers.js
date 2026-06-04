// 投稿フォーム共通ヘルパ: メディア圧縮 + 投稿前の確認モーダル。
// - 画像: canvas で長辺 1600px・JPEG 再エンコード
// - 動画: ffmpeg.wasm (CDN, single-thread core) で H.264/MP4・長辺1280px・CRF28
//   失敗時は原本をそのまま使う (投稿は止めない)
// - confirmSubmit(): 投稿前に内容を一覧表示し、OK/戻るを待つ
(function () {
  const IMG_MAX = 1600, IMG_Q = 0.82, VID_MAX = 1280;

  function isImage(f) { return /^image\//.test(f.type || "") || /\.(png|jpe?g|gif|webp|bmp)$/i.test(f.name || ""); }
  function isVideo(f) { return /^video\//.test(f.type || "") || /\.(mp4|mov|webm|m4v|avi|3gp|mkv)$/i.test(f.name || ""); }

  function loadImage(file) {
    return new Promise((res, rej) => {
      const u = URL.createObjectURL(file);
      const im = new Image();
      im.onload = () => { URL.revokeObjectURL(u); res(im); };
      im.onerror = (e) => { URL.revokeObjectURL(u); rej(e); };
      im.src = u;
    });
  }

  async function compressImage(file) {
    try {
      const img = await loadImage(file);
      let w = img.naturalWidth, h = img.naturalHeight;
      const scale = Math.min(1, IMG_MAX / Math.max(w, h));
      w = Math.max(1, Math.round(w * scale));
      h = Math.max(1, Math.round(h * scale));
      const c = document.createElement("canvas");
      c.width = w; c.height = h;
      c.getContext("2d").drawImage(img, 0, 0, w, h);
      const blob = await new Promise(r => c.toBlob(r, "image/jpeg", IMG_Q));
      if (!blob || blob.size >= file.size) return { blob: file, name: file.name, compressed: false };
      return { blob, name: file.name.replace(/\.[^.]+$/, "") + ".jpg", compressed: true };
    } catch (e) { console.warn("image compress failed", e); return { blob: file, name: file.name, compressed: false }; }
  }

  // 動画圧縮: ブラウザ標準の MediaRecorder で再エンコード (長辺 VID_MAX に縮小 + ビットレート制限)。
  // ffmpeg.wasm は GitHub Pages では cross-origin Worker がブロックされ動かないため不採用。
  // 追加ライブラリ不要・同一オリジンで確実に動作。出力は WebM。音声があれば保持。
  const VID_BITRATE = 1500000; // ~1.5Mbps
  async function compressVideo(file, onProgress) {
    let url = null;
    try {
      if (typeof MediaRecorder === "undefined") throw new Error("MediaRecorder unsupported");
      url = URL.createObjectURL(file);
      const video = document.createElement("video");
      video.src = url; video.muted = true; video.playsInline = true; video.preload = "auto";
      await new Promise((res, rej) => {
        video.onloadedmetadata = res;
        video.onerror = () => rej(new Error("video load error"));
        setTimeout(() => rej(new Error("video metadata timeout")), 20000);
      });
      const dur = video.duration;
      let w = video.videoWidth, h = video.videoHeight;
      if (!w || !h) throw new Error("no video dimensions");
      const scale = Math.min(1, VID_MAX / Math.max(w, h));
      w = Math.max(2, Math.round(w * scale / 2) * 2);
      h = Math.max(2, Math.round(h * scale / 2) * 2);
      const canvas = document.createElement("canvas");
      canvas.width = w; canvas.height = h;
      const ctx = canvas.getContext("2d");
      const mime = ["video/webm;codecs=vp9", "video/webm;codecs=vp8", "video/webm"]
        .find(m => MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(m)) || "video/webm";
      const outStream = canvas.captureStream(24);
      // 音声トラックがあれば引き継ぐ
      try {
        const cap = video.captureStream ? video.captureStream() : (video.mozCaptureStream ? video.mozCaptureStream() : null);
        const at = cap && cap.getAudioTracks && cap.getAudioTracks()[0];
        if (at) { video.muted = false; outStream.addTrack(at); }
      } catch (_) {}
      const rec = new MediaRecorder(outStream, { mimeType: mime, videoBitsPerSecond: VID_BITRATE });
      const chunks = [];
      rec.ondataavailable = e => { if (e.data && e.data.size) chunks.push(e.data); };
      const stopped = new Promise(res => { rec.onstop = res; });
      rec.start(250);
      await video.play();
      await new Promise((res) => {
        let done = false;
        const finish = () => { if (!done) { done = true; res(); } };
        video.onended = finish;
        const tick = () => {
          if (done) return;
          if (video.ended || video.paused) { finish(); return; }
          ctx.drawImage(video, 0, 0, w, h);
          if (onProgress && dur && isFinite(dur)) onProgress(Math.min(99, Math.round((video.currentTime / dur) * 100)));
          requestAnimationFrame(tick);
        };
        tick();
        // セーフティ: 想定の約2倍でも終わらなければ打ち切り
        if (isFinite(dur) && dur > 0) setTimeout(finish, Math.min(600000, dur * 2000 + 8000));
      });
      try { rec.stop(); } catch (_) {}
      await stopped;
      const blob = new Blob(chunks, { type: "video/webm" });
      if (onProgress) onProgress(100);
      if (!blob.size || blob.size >= file.size) return { blob: file, name: file.name, compressed: false };
      return { blob, name: file.name.replace(/\.[^.]+$/, "") + ".webm", compressed: true };
    } catch (e) {
      console.warn("video compress failed (uploading original)", e);
      return { blob: file, name: file.name, compressed: false };
    } finally {
      if (url) try { URL.revokeObjectURL(url); } catch (_) {}
    }
  }

  // file -> { blob, name, compressed }。onStage(stageLabel, percent?) で進捗通知。
  async function process(file, onStage) {
    if (isImage(file)) { if (onStage) onStage("圧縮中"); return compressImage(file); }
    if (isVideo(file)) {
      if (onStage) onStage("動画を圧縮中 (初回は数十秒)");
      return compressVideo(file, (p) => { if (onStage) onStage("動画を圧縮中", p); });
    }
    return { blob: file, name: file.name, compressed: false };
  }

  // ===== 確認モーダル =====
  function ensureStyles() {
    if (document.getElementById("ph-confirm-style")) return;
    const s = document.createElement("style");
    s.id = "ph-confirm-style";
    s.textContent = `
      .ph-modal-bg{position:fixed;inset:0;background:rgba(0,0,0,.5);display:flex;align-items:center;justify-content:center;z-index:1000;padding:20px}
      .ph-modal{background:#fff;border-radius:14px;max-width:560px;width:100%;max-height:88vh;overflow:auto;padding:22px 24px;box-shadow:0 12px 40px rgba(0,0,0,.25)}
      .ph-modal h3{margin:0 0 4px;font-size:18px}
      .ph-modal .ph-sub{color:#888;font-size:12px;margin:0 0 14px}
      .ph-modal table{width:100%;border-collapse:collapse;margin:8px 0;font-size:13px}
      .ph-modal th,.ph-modal td{border:1px solid #eee;padding:7px 10px;text-align:left;vertical-align:top}
      .ph-modal th{background:#f6f6f8;width:120px;font-weight:600}
      .ph-sec-title{font-size:13px;font-weight:700;margin:14px 0 6px;color:#444}
      .ph-att{display:flex;flex-wrap:wrap;gap:8px}
      .ph-att .ph-card{border:1px solid #eee;border-radius:8px;padding:6px;font-size:11px;max-width:160px}
      .ph-att img,.ph-att video{max-width:148px;max-height:110px;border-radius:6px;display:block}
      .ph-warn{background:#fff7e6;border:1px solid #f3d99c;border-radius:8px;padding:10px 12px;font-size:12px;color:#6b4a00;margin:10px 0}
      .ph-actions{display:flex;gap:10px;justify-content:flex-end;margin-top:18px}
      .ph-actions button{font:inherit;font-size:14px;padding:9px 18px;border-radius:8px;cursor:pointer;border:1px solid #ccc;background:#fff}
      .ph-actions .ph-ok{background:#111;color:#fff;border-color:#111;font-weight:600}
      .ph-actions .ph-ok:disabled{opacity:.5;cursor:not-allowed}
    `;
    document.head.appendChild(s);
  }

  function esc(s) { return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;"); }

  // confirmSubmit({title, rows:[[label,value]], sections:[[title,text]], attachments:[{name,url,status}], lang})
  // -> Promise<boolean> (投稿する=true / 戻る=false)
  function confirmSubmit(data) {
    ensureStyles();
    const isJa = (data.lang || "ja") === "ja";
    const rows = (data.rows || []).filter(r => r[1] != null && String(r[1]).trim() !== "");
    const secs = (data.sections || []).filter(s => s[1] != null && String(s[1]).trim() !== "");
    const atts = data.attachments || [];
    const pending = atts.filter(a => a.status && a.status !== "done");

    const rowsHtml = rows.map(r => `<tr><th>${esc(r[0])}</th><td>${esc(r[1])}</td></tr>`).join("");
    const secsHtml = secs.map(s => `<div class="ph-sec-title">${esc(s[0])}</div><div style="font-size:13px;white-space:pre-wrap">${esc(s[1])}</div>`).join("");
    const attHtml = atts.length ? `<div class="ph-sec-title">${isJa ? "添付" : "附件"} (${atts.length})</div><div class="ph-att">` + atts.map(a => {
      const v = /\.(mp4|mov|webm|m4v)$/i.test(a.name || "");
      const img = /\.(png|jpe?g|gif|webp)$/i.test(a.name || "");
      let media = "";
      if (a.url && img) media = `<img src="${esc(a.url)}" loading="lazy">`;
      else if (a.url && v) media = `<video src="${esc(a.url)}" muted></video>`;
      const badge = a.status === "done" ? "✅" : (a.status === "error" ? "❌" : "⏳");
      return `<div class="ph-card">${media}<div>${badge} ${esc(a.name || "")}</div></div>`;
    }).join("") + `</div>` : "";
    const warnHtml = pending.length ? `<div class="ph-warn">${isJa ? `⚠️ ${pending.length} 件のメディアがまだ処理中です。完了を待ってから投稿してください。` : `⚠️ ${pending.length} 个媒体仍在处理中，请等待完成后再提交。`}</div>` : "";

    return new Promise((resolve) => {
      const bg = document.createElement("div");
      bg.className = "ph-modal-bg";
      bg.innerHTML = `
        <div class="ph-modal" role="dialog" aria-modal="true">
          <h3>${isJa ? "この内容で投稿しますか？" : "确认提交以下内容？"}</h3>
          <p class="ph-sub">${esc(data.title || "")}</p>
          ${warnHtml}
          ${rowsHtml ? `<table><tbody>${rowsHtml}</tbody></table>` : ""}
          ${secsHtml}
          ${attHtml}
          <div class="ph-actions">
            <button type="button" class="ph-back">${isJa ? "← 修正に戻る" : "← 返回修改"}</button>
            <button type="button" class="ph-ok" ${pending.length ? "disabled" : ""}>${isJa ? "この内容で投稿" : "确认提交"}</button>
          </div>
        </div>`;
      document.body.appendChild(bg);
      const close = (val) => { bg.remove(); resolve(val); };
      bg.querySelector(".ph-back").addEventListener("click", () => close(false));
      bg.querySelector(".ph-ok").addEventListener("click", () => close(true));
      bg.addEventListener("click", (e) => { if (e.target === bg) close(false); });
    });
  }

  window.PostHelpers = { process, isImage, isVideo, confirmSubmit };
})();
