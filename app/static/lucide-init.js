(function () {
  var LUCIDE_ATTRS = {
    "stroke-width": "1.5",
    "stroke-linecap": "round",
    "stroke-linejoin": "round",
  };

  function initLucide(root) {
    if (!window.lucide) return;
    var options = { attrs: LUCIDE_ATTRS };
    if (root && root !== document) {
      options.root = root;
    }
    lucide.createIcons(options);
  }

  window.gdpInitLucideIcons = initLucide;

  document.addEventListener("DOMContentLoaded", function () {
    initLucide();
  });
})();
