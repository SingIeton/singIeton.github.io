/* PoE 도구함 공용 상단 바
 * 사용법: 서비스 페이지 <head> 안에 한 줄 추가 (이 파일은 poetools/style/site-bar.js 에 둡니다)
 *   <script src="../../style/site-bar.js"></script>   ← poetools/poe1/harvest-sim/index.html 기준
 * 경로는 이 스크립트의 위치에서 자동 계산하므로 페이지마다 따로 고칠 것이 없습니다.
 * 언어 변경 시 window 에 "sitebar:lang" 이벤트(detail = "ko" | "en")를 보냅니다.
 */
(function () {
  var doc = document, root = doc.documentElement;
  var src = (doc.currentScript && doc.currentScript.src) || "";
  /* 스크립트 위치(poetools/style/site-bar.js) 기준으로 poetools 경로와 사이트 루트 계산 */
  var TOOLS = new URL("../", src || location.href).href;
  var SITE_ROOT = new URL("../", TOOLS).href;

  var GAMES = [
    { id: "poe1", short: "PoE 1" },
    { id: "poe2", short: "PoE 2" }
  ];
  var SITE = { ko: "PoE Tools", en: "PoE Tools" };

  var LANG = "ko";
  try { LANG = localStorage.getItem("lang") || "ko"; } catch (e) {}
  if (LANG !== "en") LANG = "ko";

  /* 테마: 페이지가 그려지기 전에 적용해서 깜빡임 방지 */
  try { var t0 = localStorage.getItem("theme"); if (t0) root.dataset.theme = t0; } catch (e) {}
  var dk = function () {
    return root.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  };

  /* 현재 페이지가 속한 게임 (주소에 /poe1/ 또는 /poe2/ 포함 여부) */
  var cur = null;
  GAMES.forEach(function (g) { if (location.pathname.indexOf("/" + g.id + "/") !== -1) cur = g.id; });

  /* 폰트: 메인 페이지와 같은 폰트를 사용 */
  var f1 = doc.createElement("link"); f1.rel = "preconnect"; f1.href = "https://fonts.googleapis.com";
  var f2 = doc.createElement("link"); f2.rel = "stylesheet";
  f2.href = "https://fonts.googleapis.com/css2?family=Hahmlet:wght@700&family=IBM+Plex+Sans+KR:wght@600&display=swap";
  doc.head.appendChild(f1); doc.head.appendChild(f2);

  /* CSS: 전부 #site-bar 아래로 한정하고, 페이지의 전역 button/select/a 스타일을 덮어쓸 수 있게 ID 선택자 사용 */
  var css = ''
    + '#site-bar{--sb-bg:#e6e3db;--sb-ink:#1b1913;--sb-mute:#625c4d;--sb-ln:#cbc5b4;--sb-ln2:#b0a891;--sb-g:#575143;--sb-g1:#8f4f14;--sb-g2:#1d6a60;--sb-gi:#fff;'
    + 'position:sticky;top:0;z-index:100;background:color-mix(in oklab,var(--sb-bg) 92%,transparent);-webkit-backdrop-filter:blur(8px);backdrop-filter:blur(8px);border-bottom:1px solid var(--sb-ln);'
    + 'font:15px/1.65 "IBM Plex Sans KR","Pretendard","Apple SD Gothic Neo","Noto Sans KR","Malgun Gothic",system-ui,sans-serif;color:var(--sb-ink);box-sizing:border-box}'
    + '@media (prefers-color-scheme:dark){:root:not([data-theme="light"]) #site-bar{--sb-bg:#0e0d0b;--sb-ink:#ebe5d4;--sb-mute:#a69e89;--sb-ln:#2f2a21;--sb-ln2:#453d2e;--sb-g:#b8b19d;--sb-g1:#d38d49;--sb-g2:#6cb2a6;--sb-gi:#14100a}}'
    + ':root[data-theme="dark"] #site-bar{--sb-bg:#0e0d0b;--sb-ink:#ebe5d4;--sb-mute:#a69e89;--sb-ln:#2f2a21;--sb-ln2:#453d2e;--sb-g:#b8b19d;--sb-g1:#d38d49;--sb-g2:#6cb2a6;--sb-gi:#14100a}'
    + '#site-bar *,#site-bar *::before,#site-bar *::after{box-sizing:border-box}'
    + '#site-bar .sb-wrap{max-width:1200px;margin:0 auto;padding:0 16px;display:flex;align-items:center;gap:18px;height:56px}'
    + '#site-bar .sb-brand{display:flex;align-items:center;gap:10px;text-decoration:none;font:700 17px "Hahmlet","Noto Serif KR","Nanum Myeongjo","AppleMyungjo",serif;color:var(--sb-ink)}'
    + '#site-bar .sb-brand svg{color:var(--sb-g)}'
    + '#site-bar .sb-nav{display:flex;height:100%}'
    + '#site-bar .sb-nav a{display:flex;align-items:center;gap:8px;padding:0 14px;text-decoration:none;font-weight:600;font-size:15px;color:var(--sb-mute);border-bottom:2px solid transparent;margin-bottom:-1px}'
    + '#site-bar .sb-nav a:hover{color:var(--sb-ink)}'
    + '#site-bar .sb-nav a[aria-current]{color:var(--sb-ink);border-bottom-color:var(--gc)}'
    + '#site-bar .sb-nav i{width:8px;height:8px;background:var(--gc);transform:rotate(45deg)}'
    + '#site-bar .sb-nav [data-game=poe1]{--gc:var(--sb-g1)}#site-bar .sb-nav [data-game=poe2]{--gc:var(--sb-g2)}'
    + '#site-bar .sb-tools{margin-left:auto;display:flex;gap:8px;align-items:center}'
    + '#site-bar .sb-seg{display:inline-flex;border:1px solid var(--sb-ln2);border-radius:3px;overflow:hidden}'
    + '#site-bar button{width:auto;margin:0;font:inherit;color:inherit;cursor:pointer;border-radius:0;box-shadow:none}'
    + '#site-bar .sb-seg button{border:0;background:none;color:var(--sb-mute);padding:5px 10px;font-weight:600;font-size:13px}'
    + '#site-bar .sb-seg button[aria-pressed=true]{background:var(--sb-g);color:var(--sb-gi)}'
    + '#site-bar .sb-ibtn{width:34px;height:32px;display:grid;place-items:center;padding:0;border:1px solid var(--sb-ln2);background:none;color:var(--sb-ink);border-radius:3px}'
    + '#site-bar a:focus-visible,#site-bar button:focus-visible{outline:2px solid var(--sb-g);outline-offset:2px}'
    + '@media (max-width:560px){#site-bar .sb-bn{display:none}#site-bar .sb-nav a{padding:0 10px}#site-bar .sb-wrap{gap:8px}}';
  var st = doc.createElement("style"); st.textContent = css; doc.head.appendChild(st);

  var MARK = '<svg viewBox="0 0 24 28" width="22" height="26" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="M3 26V12a9 9 0 0 1 18 0v14z"/><path d="M12 9.5l3 4.5-3 6.5-3-6.5z" fill="currentColor" stroke="none"/></svg>';
  var SUN = '<svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5L19 19M5 19l1.5-1.5M17.5 6.5L19 5"/></svg>';
  var MOON = '<svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" aria-hidden="true"><path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/></svg>';

  var bar;
  function render() {
    var T = function (ko, en) { return LANG === "en" ? en : ko; };
    bar.innerHTML = '<div class="sb-wrap">'
      + '<a class="sb-brand" href="' + SITE_ROOT + '" aria-label="' + SITE[LANG] + '">' + MARK + '<span class="sb-bn">' + SITE[LANG] + '</span></a>'
      + '<nav class="sb-nav" aria-label="' + T("게임", "Games") + '">'
      + GAMES.map(function (g) {
          return '<a href="' + TOOLS + g.id + '/" data-game="' + g.id + '"' + (cur === g.id ? ' aria-current="true"' : '') + '><i></i>' + g.short + '</a>';
        }).join("")
      + '</nav>'
      + '<div class="sb-tools"><div class="sb-seg" role="group" aria-label="Language">'
      + '<button type="button" data-lang="ko" aria-pressed="' + (LANG === "ko") + '">한국어</button>'
      + '<button type="button" data-lang="en" aria-pressed="' + (LANG === "en") + '">EN</button></div>'
      + '<button class="sb-ibtn" id="sb-theme" type="button" aria-label="' + T("화면 테마 바꾸기", "Toggle theme") + '">' + (dk() === "dark" ? SUN : MOON) + '</button></div>'
      + '</div>';
  }

  function mount() {
    bar = doc.createElement("header");
    bar.id = "site-bar";
    doc.body.insertBefore(bar, doc.body.firstChild);
    render();
    bar.addEventListener("click", function (e) {
      var b = e.target.closest("button"); if (!b) return;
      if (b.dataset.lang) {
        LANG = b.dataset.lang;
        try { localStorage.setItem("lang", LANG); } catch (x) {}
        render();
        var nb = bar.querySelector('[data-lang="' + LANG + '"]'); if (nb) nb.focus();
        window.dispatchEvent(new CustomEvent("sitebar:lang", { detail: LANG }));
        return;
      }
      if (b.id === "sb-theme") {
        var t = dk() === "dark" ? "light" : "dark";
        root.dataset.theme = t;
        try { localStorage.setItem("theme", t); } catch (x) {}
        b.innerHTML = t === "dark" ? SUN : MOON;
      }
    });
  }
  if (doc.body) mount(); else doc.addEventListener("DOMContentLoaded", mount);
})();
