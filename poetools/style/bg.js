/* PoE 도구함 공용 배경 이미지
 * 이미지 위치 (확장자는 webp/jpg/jpeg/png/avif/gif/svg 아무거나):
 *   poetools/poetools_bg.*       모든 페이지
 *   poetools/poe1/poe1_bg.*      poe1/ 아래 페이지 (있으면 poetools_bg 대신 사용)
 *   poetools/poe2/poe2_bg.*      poe2/ 아래 페이지 (있으면 poetools_bg 대신 사용)
 * 사용법: <script src="…/style/bg.js"></script> (site-bar.js 를 쓰는 페이지는 자동 로드)
 * 진하기: CSS 변수 --bg-opacity (기본 0.12) 를 :root 에 지정하면 바뀝니다.
 * 흑백 정도: CSS 변수 --bg-gray (0 = 원본 색, 1 = 완전 흑백, 기본 0)
 * 낮 테마는 따로: --bg-opacity-light (기본 0.07), --bg-gray-light (기본 1)
 */
(function () {
  if (window.__sitebg) return;
  window.__sitebg = 1;
  var doc = document, root = doc.documentElement;
  var src = (doc.currentScript && doc.currentScript.src) || "";
  var TOOLS = new URL("../", src || location.href).href;
  var EXT = ["webp", "jpg", "jpeg", "png", "avif", "gif", "svg"];
  var game = null;
  ["poe1", "poe2"].forEach(function (g) { if (location.pathname.indexOf("/" + g + "/") !== -1) game = g; });

  /* 가까운 쪽 우선: 게임별 이미지 → 공통 이미지 */
  var bases = [];
  if (game) bases.push(TOOLS + game + "/" + game + "_bg");
  bases.push(TOOLS + "poetools_bg");

  var st = doc.createElement("style");
  st.textContent = "#site-bg{position:fixed;inset:0;z-index:-1;pointer-events:none;opacity:0;transition:opacity .6s;filter:grayscale(var(--bg-gray,0.7));background:center/cover no-repeat}"
    + "#site-bg.on{opacity:var(--bg-opacity,.065)}"
    + ':root[data-theme="light"] #site-bg{filter:grayscale(var(--bg-gray-light,0.8)) brightness(1.2)}'
    + ':root[data-theme="light"] #site-bg.on{opacity:var(--bg-opacity-light,.04)}';
  (doc.head || root).appendChild(st);
  var layer = doc.createElement("div");
  layer.id = "site-bg";
  layer.setAttribute("aria-hidden", "true");
  root.appendChild(layer);

  function show(url) {
    if (!url) return;
    layer.style.backgroundImage = 'url("' + url + '")';
    layer.classList.add("on");
  }
  function probe(url) {
    return new Promise(function (ok) {
      var im = new Image();
      im.onload = function () { ok(url); };
      im.onerror = function () { ok(null); };
      im.src = url;
    });
  }
  /* 같은 폴더 안에서는 확장자를 동시에 시도하고, EXT 순서로 먼저 맞는 것을 선택 */
  function find(i) {
    if (i >= bases.length) return Promise.resolve("");
    return Promise.all(EXT.map(function (e) { return probe(bases[i] + "." + e); })).then(function (r) {
      for (var k = 0; k < r.length; k++) if (r[k]) return r[k];
      return find(i + 1);
    });
  }

  /* 탭이 열려 있는 동안 결과를 저장해서 페이지를 옮길 때 다시 찾지 않음 */
  var key = "sitebg:" + (game || "home"), cached = null;
  try { cached = sessionStorage.getItem(key); } catch (e) {}
  if (cached !== null) { show(cached); return; }
  find(0).then(function (url) {
    try { sessionStorage.setItem(key, url); } catch (e) {}
    show(url);
  });
})();
