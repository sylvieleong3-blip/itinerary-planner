(function () {
  const DELAY_MS = 350;
  const SAFETY_MS = 12000;
  let timer = null;
  let safetyTimer = null;

  const overlay = document.getElementById("page-loading");
  if (!overlay) return;

  function show() {
    overlay.classList.remove("hidden");
    overlay.setAttribute("aria-hidden", "false");
    clearTimeout(safetyTimer);
    safetyTimer = setTimeout(hide, SAFETY_MS);
  }

  function hide() {
    clearTimeout(timer);
    clearTimeout(safetyTimer);
    timer = null;
    safetyTimer = null;
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

  hide();

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", hide);
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

  document.addEventListener(
    "submit",
    (event) => {
      const form = event.target;
      if (!(form instanceof HTMLFormElement)) return;
      if (form.dataset.noLoading !== undefined) return;
      if (event.defaultPrevented) {
        hide();
        return;
      }
      if (typeof form.checkValidity === "function" && !form.checkValidity()) {
        hide();
        return;
      }
      scheduleShow();
    },
    true
  );

  document.addEventListener(
    "invalid",
    () => {
      hide();
    },
    true
  );

  window.addEventListener("pageshow", hide);
  window.addEventListener("pagehide", hide);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") hide();
  });
})();
