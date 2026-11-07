/* PoE 도구함 공용 상단 바 + 푸터
 * 사용법: 서비스 페이지 <head> 안에 두 줄 추가 (이 파일은 poetools/style/site-bar.js 에 둡니다)
 *   <link rel="stylesheet" href="../../style/theme.css">
 *   <script src="../../style/site-bar.js"></script>   ← poetools/poe1/harvest-sim/ 기준
 * 경로는 이 스크립트의 위치에서 자동 계산하므로 페이지마다 따로 고칠 것이 없습니다.
 *
 * 모양(폰트·색·상단 바 스타일)은 전부 style/theme.css 에서 정합니다. 이 파일에는 스타일이 없습니다.
 * theme.css 링크를 빠뜨려도 여기서 대신 불러오지만, 화면이 잠깐 깜빡일 수 있으니 <link> 를 직접 넣어 주세요.
 * 파비콘이 없는 페이지에는 공용 파비콘을 넣어 줍니다.
 *
 * 언어(lang)·테마(theme) 설정의 단일 관리자입니다.
 *   - 저장: localStorage "lang" / "theme" (사이트 전체 공통 키)
 *   - 어느 페이지에서 바꿔도 다른 탭, 뒤로가기로 돌아온 페이지에 즉시 반영됩니다.
 *   - 언어가 바뀌면 window 에 "sitebar:lang" 이벤트(detail = "ko" | "en")를 보냅니다.
 *     페이지는 이 이벤트만 구독하면 됩니다. 현재 언어는 window.PoEPrefs.lang, <html lang> 에서도 읽을 수 있습니다.
 *   - 상단 바 없이 설정 동기화만 필요한 페이지(허브)는 태그에 data-nobar 를 붙입니다.
 *       <script src="style/site-bar.js" data-nobar></script>
 */
(function () {
  var doc = document, root = doc.documentElement;
  var me = doc.currentScript;
  var src = (me && me.src) || "";
  var NOBAR = !!(me && me.hasAttribute("data-nobar"));
  /* 스크립트 위치(poetools/style/site-bar.js) 기준으로 poetools 경로 계산 */
  var TOOLS = new URL("../", src || location.href).href;

  /* 공용 테마 (poetools/style/theme.css): 아직 없으면 불러오기 */
  var themed = false;
  try { themed = !!getComputedStyle(root).getPropertyValue("--g0").trim(); } catch (e) {}
  if (!themed && !doc.querySelector('link[href$="style/theme.css"]')) {
    var tl = doc.createElement("link"); tl.rel = "stylesheet"; tl.href = TOOLS + "style/theme.css";
    doc.head.appendChild(tl);
  }
  /* 공용 파비콘 */
  if (!doc.querySelector('link[rel~="icon"]')) {
    var fi = doc.createElement("link"); fi.rel = "icon";
    fi.href = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 28'%3E%3Cpath d='M3 26V12a9 9 0 0 1 18 0v14z' fill='none' stroke='%23cf8a45' stroke-width='2'/%3E%3Cpath d='M12 9.5l3 4.5-3 6.5-3-6.5z' fill='%23cf8a45'/%3E%3C/svg%3E";
    doc.head.appendChild(fi);
  }
  /* 배경 이미지 (poetools/style/bg.js) */
  if (!window.__sitebg) { var bgs = doc.createElement("script"); bgs.src = TOOLS + "style/bg.js"; (doc.head || root).appendChild(bgs); }

  var GAMES = [
    { id: "poe1", short: "PoE 1" },
    { id: "poe2", short: "PoE 2" }
  ];
  var SITE = { ko: "PoE Tools", en: "PoE Tools" };
  var FOOT = {
    ko: "비공식 팬 사이트입니다. Grinding Gear Games와 관련이 없으며, Path of Exile과 관련 명칭은 Grinding Gear Games의 것입니다.",
    en: "Unofficial fan site, not affiliated with Grinding Gear Games. Path of Exile and related names belong to Grinding Gear Games."
  };

  /* 설정 읽기: 항상 localStorage 가 기준 */
  function readLang() { var v = null; try { v = localStorage.getItem("lang"); } catch (e) {} return v === "en" ? "en" : "ko"; }
  function readTheme() { var v = null; try { v = localStorage.getItem("theme"); } catch (e) {} return v === "light" ? "light" : "dark"; } /* 기본값: 밤 */
  var LANG = readLang();
  root.lang = LANG;
  root.dataset.theme = readTheme(); /* 페이지가 그려지기 전에 적용해서 깜빡임 방지 */
  var dk = function () {
    return root.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  };

  /* 현재 페이지가 속한 게임 (주소에 /poe1/ 또는 /poe2/ 포함 여부) */
  var cur = null;
  GAMES.forEach(function (g) { if (location.pathname.indexOf("/" + g.id + "/") !== -1) cur = g.id; });

  var MARK = '<svg viewBox="0 0 24 28" width="22" height="26" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="M3 26V12a9 9 0 0 1 18 0v14z"/><path d="M12 9.5l3 4.5-3 6.5-3-6.5z" fill="currentColor" stroke="none"/></svg>';
  var SUN = '<svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5L19 19M5 19l1.5-1.5M17.5 6.5L19 5"/></svg>';
  var MOON = '<svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" aria-hidden="true"><path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/></svg>';

  var bar, foot;
  function render() {
    var T = function (ko, en) { return LANG === "en" ? en : ko; };
    /* 마크업과 클래스는 허브 페이지의 상단 바와 동일 (스타일: theme.css 의 "상단 바") */
    bar.innerHTML = '<div class="wrap">'
      + '<a class="brand" href="' + TOOLS + 'poetools.html" aria-label="' + SITE[LANG] + '">' + MARK + '<span class="bn">' + SITE[LANG] + '</span></a>'
      + '<nav class="gnav" aria-label="' + T("게임", "Games") + '">'
      + GAMES.map(function (g) {
          return '<a href="' + TOOLS + g.id + '/' + g.id + '.html" data-game="' + g.id + '"' + (cur === g.id ? ' aria-current="true"' : '') + '><i></i>' + g.short + '</a>';
        }).join("")
      + '</nav>'
      + '<div class="tools"><div class="seg" role="group" aria-label="Language">'
      + '<button type="button" data-lang="ko" aria-pressed="' + (LANG === "ko") + '">한국어</button>'
      + '<button type="button" data-lang="en" aria-pressed="' + (LANG === "en") + '">EN</button></div>'
      + '<button class="ibtn" id="sb-theme" type="button" aria-label="' + T("화면 테마 바꾸기", "Toggle theme") + '">' + (dk() === "dark" ? SUN : MOON) + '</button></div>'
      + '</div>';
  }
  function renderFoot() {
    foot.innerHTML = '<div class="wrap">' + FOOT[LANG] + '</div>';
  }

  /* 언어/테마 변경 (이 함수들만 저장과 알림을 담당) */
  function applyLang(l) {
    LANG = l; root.lang = l;
    if (bar) render();
    if (foot) renderFoot();
    window.dispatchEvent(new CustomEvent("sitebar:lang", { detail: l }));
  }
  function applyTheme(t) {
    root.dataset.theme = t;
    var b = doc.getElementById("sb-theme"); if (b) b.innerHTML = t === "dark" ? SUN : MOON;
  }
  function setLang(l) { l = l === "en" ? "en" : "ko"; try { localStorage.setItem("lang", l); } catch (x) {} applyLang(l); }
  function setTheme(t) { t = t === "light" ? "light" : "dark"; try { localStorage.setItem("theme", t); } catch (x) {} applyTheme(t); }
  window.PoEPrefs = {
    get lang() { return LANG; }, get theme() { return root.dataset.theme; },
    setLang: setLang, setTheme: setTheme
  };

  function mount() {
    bar = doc.createElement("header");
    bar.id = "site-bar";
    bar.className = "top";
    doc.body.insertBefore(bar, doc.body.firstChild);
    render();
    /* 푸터: 페이지에 .foot 이 이미 있으면 만들지 않음 */
    if (!doc.querySelector("footer.foot")) {
      foot = doc.createElement("footer");
      foot.id = "site-foot";
      foot.className = "foot";
      doc.body.appendChild(foot);
      renderFoot();
    }
    bar.addEventListener("click", function (e) {
      var b = e.target.closest("button"); if (!b) return;
      if (b.dataset.lang) {
        setLang(b.dataset.lang);
        var nb = bar.querySelector('[data-lang="' + LANG + '"]'); if (nb) nb.focus();
        return;
      }
      if (b.id === "sb-theme") setTheme(dk() === "dark" ? "light" : "dark");
    });
  }

  /* 동기화: 다른 탭에서 바꿨을 때, 뒤로가기/앞으로가기로 예전 화면이 복원됐을 때, 탭으로 다시 돌아왔을 때
   * 저장된 값과 "지금 화면에 보이는 값(<html lang>, data-theme)"을 비교해서 다르면 따라갑니다. */
  function sync() {
    var t = readTheme(), l = readLang();
    if (t !== root.dataset.theme) applyTheme(t);
    if (l !== root.lang) applyLang(l);
  }
  window.addEventListener("storage", function (e) { if (e.key === "lang" || e.key === "theme" || e.key === null) sync(); });
  window.addEventListener("pageshow", function (e) { if (e.persisted) sync(); });
  doc.addEventListener("visibilitychange", function () { if (!doc.hidden) sync(); });

  if (NOBAR) return;
  if (doc.body) mount(); else doc.addEventListener("DOMContentLoaded", mount);
})();
