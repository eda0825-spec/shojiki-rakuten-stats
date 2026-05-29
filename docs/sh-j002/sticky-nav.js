// ヘッダー(.hdr)の実高さに合わせて、固定ナビ(.topnav)の sticky オフセットを動的設定。
// ヘッダーは画面幅で折り返して高さが変わる (PC ~58px / スマホ折返し時 ~100px) ため、
// 固定値ではなく実測値を使う。読み込み時・リサイズ時・フォント反映後に再計算する。
(function () {
  function setOffset() {
    var hdr = document.querySelector(".hdr");
    var nav = document.querySelector(".topnav");
    if (!hdr || !nav) return;
    nav.style.top = Math.max(0, hdr.offsetHeight - 1) + "px";
  }
  setOffset();
  window.addEventListener("load", setOffset);
  window.addEventListener("resize", setOffset);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(setOffset);
})();
