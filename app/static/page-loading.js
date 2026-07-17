(function () {
  const DELAY_MS = 350;
  let timer = null;

  const overlay = document.getElementById("page-loading");
  if (!overlay) return;

  function show() {
    overlay.classList.remove("hidden");
    overlay.setAttribute("aria-hidden", "false");
  }

  function hide() {
    clearTimeout(timer);
    timer = null;
    overlay.classList.add("hidden");
    overlay.setAttribute("aria-hidden", "true");
  }

  function scheduleShow() {
    clearTimeout(timer);
    timer = setTimeout(show, DELAY_MS);
  }

  function shouldShowForLink(link, event) {
    if (event.defaultPrevented) return false;
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
      return false;
    }
    if (link.target === "_blank" || link.hasAttribute("download")) return false;
    if (link.dataset.noLoading !== undefined) return false;

    const href = link.getAttribute("href");
    if (!href || href.startsWith("#") || href.startsWith("javascript:")) return false;

    try {
      const url = new URL(link.href, location.href);
      if (url.origin !== location.origin) return false;
      if (url.pathname === location.pathname && url.search === location.search && !url.hash) {
        return false;
      }
    } catch (_) {
      return false;
    }
    return true;
  }

  document.addEventListener(
    "click",
    (event) => {
      const link = event.target.closest("a[href]");
      if (link && shouldShowForLink(link, event)) {
        scheduleShow();
        return;
      }

      const submitBtn = event.target.closest("button[type='submit'], input[type='submit']");
      if (submitBtn && submitBtn.form && submitBtn.form.dataset.noLoading === undefined) {
        scheduleShow();
      }
    },
    true
  );

  document.addEventListener("submit", (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) return;
    if (form.dataset.noLoading !== undefined) return;
    setTimeout(() => {
      if (!event.defaultPrevented) scheduleShow();
    }, 0);
  });

  window.addEventListener("pageshow", (event) => {
    if (event.persisted) hide();
  });

  window.addEventListener("pagehide", hide);
})();
