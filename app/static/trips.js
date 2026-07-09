(function () {
  const STORAGE_KEY = "gdp_trips";

  function getTrips() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      return raw ? JSON.parse(raw) : [];
    } catch {
      return [];
    }
  }

  function setTrips(trips) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(trips));
  }

  function escapeHtml(text) {
    const el = document.createElement("span");
    el.textContent = text;
    return el.innerHTML;
  }

  function formatDate(dateStr) {
    if (!dateStr) return "";
    const d = new Date(dateStr + "T12:00:00");
    if (Number.isNaN(d.getTime())) return dateStr;
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  }

  function saveTrip(trip) {
    const trips = getTrips();
    const idx = trips.findIndex((t) => t.code === trip.code);
    const entry = {
      code: trip.code,
      name: trip.name,
      date: trip.date,
      location: trip.location,
      isCreator: !!trip.isCreator,
      joinedAt: idx >= 0 ? trips[idx].joinedAt : new Date().toISOString(),
    };
    if (idx >= 0) {
      trips[idx] = entry;
    } else {
      trips.unshift(entry);
    }
    setTrips(trips);
  }

  function removeTrip(code) {
    setTrips(getTrips().filter((t) => t.code !== code));
  }

  function renderYourTrips(listEl, sectionEl) {
    const trips = getTrips();
    if (!trips.length) {
      if (sectionEl) sectionEl.classList.add("hidden");
      if (listEl) listEl.innerHTML = "";
      return;
    }

    if (sectionEl) sectionEl.classList.remove("hidden");
    if (!listEl) return;

    listEl.innerHTML = trips
      .map(
        (trip) => `
      <div class="trip-card">
        <a href="/t/${escapeHtml(trip.code)}" class="trip-card-link">
          <div class="trip-card-main">
            <p class="trip-card-name">${escapeHtml(trip.name)}</p>
            <p class="text-sm muted">${escapeHtml(formatDate(trip.date))} · ${escapeHtml(trip.location)}</p>
          </div>
          ${trip.isCreator ? '<span class="badge badge-accent">Creator</span>' : ""}
        </a>
        <button type="button" class="btn-remove-trip" data-code="${escapeHtml(trip.code)}" title="Remove from your list" aria-label="Remove from your list">✕</button>
      </div>`
      )
      .join("");

    listEl.querySelectorAll(".btn-remove-trip").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        removeTrip(btn.dataset.code);
        renderYourTrips(listEl, sectionEl);
      });
    });
  }

  window.gdpTrips = { getTrips, saveTrip, removeTrip, renderYourTrips };
})();
