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

  function formatTripDates(trip) {
    if (!trip.date) return "";
    const numDays = trip.numDays || 1;
    const start = new Date(trip.date + "T12:00:00");
    if (Number.isNaN(start.getTime())) return trip.date;
    if (numDays <= 1) {
      return start.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
    }
    const end = new Date(start);
    end.setDate(end.getDate() + numDays - 1);
    const startStr = start.toLocaleDateString(undefined, { month: "short", day: "numeric" });
    const endStr = end.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
    return startStr + " – " + endStr + " · " + numDays + " days";
  }

  function saveTrip(trip) {
    const trips = getTrips();
    const idx = trips.findIndex((t) => t.code === trip.code);
    const entry = {
      code: trip.code,
      name: trip.name,
      date: trip.date,
      location: trip.location,
      numDays: trip.numDays || 1,
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

  async function pruneStaleTrips() {
    const trips = getTrips();
    if (!trips.length) return 0;

    const results = await Promise.all(
      trips.map(async (trip) => {
        try {
          const res = await fetch(`/t/${encodeURIComponent(trip.code)}/exists`);
          if (!res.ok) return false;
          const data = await res.json();
          return !!data.exists;
        } catch {
          return true;
        }
      })
    );

    const valid = trips.filter((_, i) => results[i]);
    const removed = trips.length - valid.length;
    if (removed > 0) {
      setTrips(valid);
    }
    return removed;
  }

  function renderYourTrips(listEl, sectionEl, emptyEl) {
    const trips = getTrips();
    const hasTrips = trips.length > 0;

    if (emptyEl) {
      emptyEl.classList.toggle("hidden", hasTrips);
    }

    if (!hasTrips) {
      if (listEl) listEl.innerHTML = "";
      return;
    }

    if (sectionEl) sectionEl.classList.remove("hidden");
    if (!listEl) return;

    listEl.innerHTML = trips
      .map(
        (trip) => `
      <div class="flex items-stretch gap-1 bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
        <a href="/t/${escapeHtml(trip.code)}" class="flex-1 flex items-center justify-between gap-3 px-4 py-3.5 no-underline text-inherit hover:bg-gray-50">
          <div>
            <p class="font-semibold mb-0.5">${escapeHtml(trip.name)}</p>
            <p class="text-sm text-gray-500">${escapeHtml(formatTripDates(trip))} · ${escapeHtml(trip.location)}</p>
          </div>
          ${trip.isCreator ? '<span class="text-xs font-medium rounded-full px-2.5 py-1 bg-blue-100 text-blue-600 shrink-0">Creator</span>' : ""}
        </a>
        <button type="button" class="shrink-0 self-center mr-2 border border-gray-200 rounded-lg w-7 h-7 p-0 bg-white text-gray-500 cursor-pointer text-sm leading-none hover:bg-red-50 hover:text-red-600 hover:border-red-200" data-code="${escapeHtml(trip.code)}" title="Remove from your list" aria-label="Remove from your list">✕</button>
      </div>`
      )
      .join("");

    listEl.querySelectorAll("[data-code]").forEach((btn) => {
      btn.addEventListener("click", async (e) => {
        e.preventDefault();
        e.stopPropagation();
        const code = btn.dataset.code;
        const trip = getTrips().find((t) => t.code === code);
        const label = trip ? '"' + trip.name + '"' : "this trip";
        const ok = await showConfirm("Remove " + label + " from your list? This only hides it locally — the trip still exists.");
        if (!ok) return;
        removeTrip(code);
        renderYourTrips(listEl, sectionEl, emptyEl);
      });
    });
  }

  window.gdpTrips = { getTrips, saveTrip, removeTrip, pruneStaleTrips, renderYourTrips };
})();
