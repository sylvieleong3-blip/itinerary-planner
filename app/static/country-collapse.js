(function () {
  function setAll(open) {
    document.querySelectorAll("[data-country-panel]").forEach((panel) => {
      panel.open = open;
    });
  }

  document.addEventListener("click", (event) => {
    const expand = event.target.closest("[data-country-expand-all]");
    if (expand) {
      event.preventDefault();
      setAll(true);
      return;
    }
    const collapse = event.target.closest("[data-country-collapse-all]");
    if (collapse) {
      event.preventDefault();
      setAll(false);
    }
  });
})();
