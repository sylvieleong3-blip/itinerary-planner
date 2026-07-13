(function () {
  function formatTime12h(time24) {
    if (!time24) return "";
    const [h, m] = time24.split(":").map(Number);
    const period = h >= 12 ? "PM" : "AM";
    const hour = h % 12 || 12;
    return hour + ":" + String(m).padStart(2, "0") + " " + period;
  }

  function bindTimeDisplay(input) {
    const label = input.closest("label")?.querySelector(".time-display-12h")
      || input.closest(".trip-builder-time-row")?.querySelector(".time-display-12h");
    if (!label) return;
    const update = () => { label.textContent = formatTime12h(input.value); };
    update();
    input.addEventListener("input", update);
    input.addEventListener("change", update);
  }

  function initTimeDisplays(root) {
    (root || document).querySelectorAll("input[type=time]").forEach(bindTimeDisplay);
  }

  let draggedCard = null;

  function getTimelineForCard(card) {
    return card.closest(".builder-timeline");
  }

  function initDragDrop(card) {
    card.addEventListener("dragstart", (e) => {
      if (e.target.closest("input, textarea, select, a, button:not(.drag-handle)")) {
        e.preventDefault();
        return;
      }
      draggedCard = card;
      card.classList.add("dragging");
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", card.dataset.id);
    });

    card.addEventListener("dragend", () => {
      card.classList.remove("dragging", "drag-over");
      document.querySelectorAll(".builder-card").forEach((el) => el.classList.remove("drag-over"));
      draggedCard = null;
    });

    card.addEventListener("dragover", (e) => {
      e.preventDefault();
      if (!draggedCard || draggedCard === card) return;
      if (getTimelineForCard(draggedCard) !== getTimelineForCard(card)) return;
      card.classList.add("drag-over");
    });

    card.addEventListener("dragleave", () => card.classList.remove("drag-over"));

    card.addEventListener("drop", (e) => {
      e.preventDefault();
      card.classList.remove("drag-over");
      if (!draggedCard || draggedCard === card) return;
      const timeline = getTimelineForCard(card);
      if (getTimelineForCard(draggedCard) !== timeline) return;
      const rect = card.getBoundingClientRect();
      const before = e.clientY < rect.top + rect.height / 2;
      if (before) timeline.insertBefore(draggedCard, card);
      else timeline.insertBefore(draggedCard, card.nextSibling);
    });
  }

  function initTimelineDragDrop(timeline) {
    if (!timeline) return;
    timeline.querySelectorAll(".builder-card").forEach(initDragDrop);
    timeline.addEventListener("dragover", (e) => {
      e.preventDefault();
      if (!draggedCard || getTimelineForCard(draggedCard) !== timeline) return;
      const cards = [...timeline.querySelectorAll(".builder-card:not(.dragging)")];
      const after = cards.find((card) => e.clientY < card.getBoundingClientRect().top + card.offsetHeight / 2);
      if (after) timeline.insertBefore(draggedCard, after);
      else timeline.appendChild(draggedCard);
    });
  }

  function removeItem(btn) {
    const card = btn.closest(".builder-card");
    if (!card) return;
    const titleEl = card.querySelector(".trip-builder-card-title, .title, .font-medium");
    const title = titleEl ? titleEl.textContent.trim() : "";
    const label = title ? '"' + title + '"' : "this stop";
    const confirmFn = window.showConfirm || ((msg) => Promise.resolve(window.confirm(msg)));
    confirmFn("Remove " + label + " from the itinerary? You can add it back from the pool below.").then((ok) => {
      if (ok) card.remove();
    });
  }

  function setLocationElement(el, location, mapsUrl) {
    if (!el) return;
    el.replaceChildren();
    if (!location) {
      el.remove();
      return;
    }
    if (mapsUrl) {
      const link = document.createElement("a");
      link.href = mapsUrl;
      link.target = "_blank";
      link.rel = "noopener";
      link.className = "text-inherit no-underline hover:text-primary hover:underline";
      link.title = "Open in Google Maps";
      link.textContent = "📍 " + location;
      el.appendChild(link);
    } else {
      el.textContent = "📍 " + location;
    }
  }

  function getTimelineEl(day) {
    if (day) return document.getElementById("timeline-day-" + day);
    return document.getElementById("timeline");
  }

  function buildCardHtml(id, title, location, startTime, duration, hasVeto, mapsUrl, day) {
    const locHtml = location
      ? (mapsUrl
        ? `<p class="text-sm text-gray-500 mt-1"><a href="${mapsUrl}" target="_blank" rel="noopener" class="text-inherit no-underline hover:text-primary hover:underline" title="Open in Google Maps">📍 ${location}</a></p>`
        : `<p class="text-sm text-gray-500 mt-1">📍 ${location}</p>`)
      : "";
    const vetoHtml = hasVeto
      ? `<div class="trip-builder-veto"><p>⚠️ Vetoed activity</p><input type="text" name="override_note_${id}" placeholder="Override note (required to include)"></div>`
      : "";
    return `
      <div class="builder-card trip-builder-card" data-id="${id}" data-day="${day || ""}" draggable="true">
        <input type="hidden" name="activity_id" value="${id}">
        <div class="trip-builder-card-head">
          <button type="button" class="drag-handle" aria-label="Drag to reorder" title="Drag to reorder">⠿</button>
          <div class="trip-builder-card-body">
            <p class="trip-builder-card-title">${title}</p>
            ${locHtml}
          </div>
          <button type="button" class="trip-builder-remove" title="Remove from timeline">✕</button>
        </div>
        <div class="trip-builder-card-fields">
          <label class="trip-builder-field">Start time
            <div class="trip-builder-time-row">
              <input type="time" name="start_time_${id}" value="${startTime}">
              <span class="time-display-12h">${formatTime12h(startTime)}</span>
            </div>
          </label>
          <label class="trip-builder-field">Duration (min)
            <input type="number" name="duration_min_${id}" value="${duration}" min="15" step="15">
          </label>
        </div>
        ${vetoHtml}
      </div>`;
  }

  function addToTimeline(id, title, location, startTime, duration, hasVeto, mapsUrl, day) {
    const timeline = getTimelineEl(day);
    if (!timeline || document.querySelector('.builder-card[data-id="' + id + '"]')) return;
    timeline.insertAdjacentHTML("beforeend", buildCardHtml(id, title, location, startTime, duration, hasVeto, mapsUrl, day));
    const card = timeline.querySelector('.builder-card[data-id="' + id + '"]');
    initDragDrop(card);
    bindTimeDisplay(card.querySelector('input[type=time]'));
    card.querySelector(".trip-builder-remove")?.addEventListener("click", () => removeItem(card.querySelector(".trip-builder-remove")));
  }

  function initTripBuilder() {
    const root = document.getElementById("trip-build-form");
    if (!root) return;

    root.querySelectorAll(".builder-timeline").forEach(initTimelineDragDrop);
    initTimeDisplays(root);

    root.querySelectorAll(".trip-builder-remove").forEach((btn) => {
      btn.addEventListener("click", () => removeItem(btn));
    });

    root.querySelectorAll(".trip-pool-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        addToTimeline(
          btn.dataset.id,
          btn.dataset.title,
          btn.dataset.location || "",
          btn.dataset.start || "12:00",
          parseInt(btn.dataset.duration || "60", 10),
          btn.dataset.veto === "1",
          btn.dataset.maps || "",
          btn.dataset.day || null
        );
      });
    });
  }

  document.addEventListener("DOMContentLoaded", initTripBuilder);
})();
