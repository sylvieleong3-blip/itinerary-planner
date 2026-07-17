(function () {
  function getCsrfToken() {
    const match = document.cookie.match(/(?:^|;\s*)gdp_csrf=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function injectFormTokens() {
    document.querySelectorAll('form[method="post"], form[method="POST"]').forEach((form) => {
      if (form.querySelector('input[name="csrf_token"]')) return;
      const token = getCsrfToken();
      if (!token) return;
      const input = document.createElement("input");
      input.type = "hidden";
      input.name = "csrf_token";
      input.value = token;
      form.appendChild(input);
    });
  }

  const originalFetch = window.fetch;
  window.fetch = function (url, options) {
    options = options || {};
    const method = (options.method || "GET").toUpperCase();
    if (method !== "GET" && method !== "HEAD" && method !== "OPTIONS") {
      const headers = new Headers(options.headers || {});
      const token = getCsrfToken();
      if (token) headers.set("X-CSRF-Token", token);
      options.headers = headers;
    }
    return originalFetch.call(this, url, options);
  };

  window.getCsrfToken = getCsrfToken;
  window.showActionError = function (message) {
    window.alert(message || "Something went wrong. Please try again.");
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", injectFormTokens);
  } else {
    injectFormTokens();
  }
})();
