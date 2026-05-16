// Markdown+ Viewer runtime — minimal client-side enhancement.
// No framework. Handles: tab switching, code copy, scroll-spy TOC highlight.
(function () {
  "use strict";

  // ---- Tab switching ----
  document.querySelectorAll(".mdp-tabs").forEach(function (tabs) {
    var btns = tabs.querySelectorAll(".mdp-tab-btn");
    var panels = tabs.querySelectorAll(".mdp-tab-panel");
    btns.forEach(function (btn) {
      btn.addEventListener("click", function () {
        var target = btn.getAttribute("data-target");
        btns.forEach(function (b) {
          b.classList.toggle("mdp-tab-active", b === btn);
          b.setAttribute("aria-selected", b === btn ? "true" : "false");
        });
        panels.forEach(function (p) {
          p.classList.toggle("mdp-tab-active", p.id === target);
        });
      });
    });
  });

  // ---- Code copy buttons ----
  document.querySelectorAll(".mdp-copy").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var code = btn.parentElement.querySelector("code");
      if (!code) return;
      var text = code.innerText;
      if (navigator.clipboard) {
        navigator.clipboard.writeText(text).then(function () {
          var orig = btn.textContent;
          btn.textContent = "Copied";
          setTimeout(function () { btn.textContent = orig; }, 1500);
        });
      }
    });
  });

  // ---- Diagram (mermaid / svg) code <-> image toggle ----
  document.querySelectorAll(".mdp-diagram-toggle").forEach(function (d) {
    var btns = d.querySelectorAll(".mdp-diagram-btn");
    var views = d.querySelectorAll(".mdp-diagram-view");
    btns.forEach(function (btn) {
      btn.addEventListener("click", function () {
        var target = btn.getAttribute("data-view");
        btns.forEach(function (b) { b.classList.toggle("mdp-diagram-btn-active", b === btn); });
        views.forEach(function (v) { v.classList.toggle("mdp-diagram-view-active", v.getAttribute("data-view") === target); });
      });
    });
  });

  // ---- Scroll-spy TOC highlight ----
  var tocLinks = document.querySelectorAll(".mdp-toc a[data-toc-target]");
  if (tocLinks.length === 0) return;
  var targetById = {};
  tocLinks.forEach(function (a) {
    var id = a.getAttribute("data-toc-target");
    var el = document.getElementById(id);
    if (el) targetById[id] = { link: a, el: el };
  });
  function update() {
    var y = window.scrollY + 80;
    var active = null;
    for (var id in targetById) {
      var top = targetById[id].el.offsetTop;
      if (top <= y) active = id;
    }
    for (var id2 in targetById) {
      targetById[id2].link.classList.toggle("mdp-toc-active", id2 === active);
    }
  }
  update();
  window.addEventListener("scroll", update, { passive: true });
  window.addEventListener("resize", update);
})();
