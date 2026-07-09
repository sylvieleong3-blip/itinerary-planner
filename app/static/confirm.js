(function () {
  const modal = document.getElementById("confirm-modal");
  if (!modal) return;

  const messageEl = document.getElementById("confirm-message");
  const yesBtn = document.getElementById("confirm-yes");
  const noBtn = document.getElementById("confirm-no");
  const backdrop = document.getElementById("confirm-backdrop");
  let pendingResolve = null;

  function close(result) {
    modal.classList.add("hidden");
    modal.setAttribute("aria-hidden", "true");
    document.body.classList.remove("overflow-hidden");
    if (pendingResolve) {
      pendingResolve(result);
      pendingResolve = null;
    }
  }

  function open(message) {
    messageEl.textContent = message;
    modal.classList.remove("hidden");
    modal.setAttribute("aria-hidden", "false");
    document.body.classList.add("overflow-hidden");
    yesBtn.focus();
    return new Promise((resolve) => {
      pendingResolve = resolve;
    });
  }

  yesBtn.addEventListener("click", () => close(true));
  noBtn.addEventListener("click", () => close(false));
  backdrop.addEventListener("click", () => close(false));
  document.addEventListener("keydown", (e) => {
    if (modal.classList.contains("hidden")) return;
    if (e.key === "Escape") close(false);
  });

  window.showConfirm = open;
})();
