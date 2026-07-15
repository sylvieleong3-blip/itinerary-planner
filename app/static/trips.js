(function () {
  const STORAGE_KEY = "gdp_trips";
  const NAME_KEY = "gdp_display_name";

  const DESTINATION_IMAGES = {
    italy: [
      "https://images.unsplash.com/photo-1502602898657-3e91760cbb34?auto=format&fit=crop&w=600&h=400",
      "https://images.unsplash.com/photo-1555881400-74d7acaacd8b?auto=format&fit=crop&w=600&h=400",
    ],
    france: [
      "https://images.unsplash.com/photo-1502602898657-3e91760cbb34?auto=format&fit=crop&w=600&h=400",
      "https://images.unsplash.com/photo-1555881400-74d7acaacd8b?auto=format&fit=crop&w=600&h=400",
    ],
    uk: [
      "https://images.unsplash.com/photo-1513635269975-59663e0ac1ad?auto=format&fit=crop&w=600&h=400",
      "https://images.unsplash.com/photo-1502602898657-3e91760cbb34?auto=format&fit=crop&w=600&h=400",
    ],
    portugal: [
      "https://images.unsplash.com/photo-1467269204594-9661b134dd2b?auto=format&fit=crop&w=600&h=400",
      "https://images.unsplash.com/photo-1539037116277-4db20889f2d4?auto=format&fit=crop&w=600&h=400",
    ],
    spain: [
      "https://images.unsplash.com/photo-1467269204594-9661b134dd2b?auto=format&fit=crop&w=600&h=400",
      "https://images.unsplash.com/photo-1539037116277-4db20889f2d4?auto=format&fit=crop&w=600&h=400",
    ],
    greece: [
      "https://images.unsplash.com/photo-1613395877344-13d4a8e0d49e?auto=format&fit=crop&w=600&h=400",
      "https://images.unsplash.com/photo-1502602898657-3e91760cbb34?auto=format&fit=crop&w=600&h=400",
    ],
    japan: [
      "https://images.unsplash.com/photo-1540959733332-eab4deabeeaf?auto=format&fit=crop&w=600&h=400",
      "https://images.unsplash.com/photo-1485738422979-f5c462d49f74?auto=format&fit=crop&w=600&h=400",
    ],
    usa: [
      "https://images.unsplash.com/photo-1485738422979-f5c462d49f74?auto=format&fit=crop&w=600&h=400",
      "https://images.unsplash.com/photo-1540959733332-eab4deabeeaf?auto=format&fit=crop&w=600&h=400",
    ],
    default: [
      "https://images.unsplash.com/photo-1502602898657-3e91760cbb34?auto=format&fit=crop&w=600&h=400",
      "https://images.unsplash.com/photo-1467269204594-9661b134dd2b?auto=format&fit=crop&w=600&h=400",
    ],
  };

  const TRIP_IMAGE_FALLBACK =
    "https://images.unsplash.com/photo-1502602898657-3e91760cbb34?auto=format&fit=crop&w=600&h=400";

  const LOCATION_RULES = [
    [/puglia|apulia|apuglia|bari|lecce|alberobello|brindisi/, "italy"],
    [/sicily|palermo|catania|taormina/, "italy"],
    [/rome|roma|florence|firenze|venice|venezia|milan|milano|naples|napoli|tuscany|amalfi|positano|sorrento|cinque terre/, "italy"],
    [/italy|italia/, "italy"],
    [/paris|lyon|marseille|nice|bordeaux|normandy|provence/, "france"],
    [/france/, "france"],
    [/london|edinburgh|manchester|bristol|uk|england|scotland|wales/, "uk"],
    [/lisbon|lisboa|porto|sintra|portugal|algarve/, "portugal"],
    [/barcelona|madrid|seville|valencia|spain|ibiza|mallorca/, "spain"],
    [/athens|santorini|mykonos|crete|greece/, "greece"],
    [/tokyo|kyoto|osaka|japan/, "japan"],
    [/san francisco|los angeles|new york|nyc|chicago|miami|usa|united states/, "usa"],
  ];

  function locationImageKey(location) {
    const loc = (location || "").toLowerCase();
    for (const [pattern, key] of LOCATION_RULES) {
      if (pattern.test(loc)) return key;
    }
    return "default";
  }

  function tripImageUrl(trip) {
    const key = locationImageKey(trip.location);
    const pool = DESTINATION_IMAGES[key] || DESTINATION_IMAGES.default;
    const seed = (trip.code || "") + "|" + (trip.location || "");
    let hash = 0;
    for (let i = 0; i < seed.length; i++) {
      hash = (hash + seed.charCodeAt(i) * (i + 1)) % pool.length;
    }
    return pool[hash] || TRIP_IMAGE_FALLBACK;
  }

  function tripImageFallback(event) {
    const img = event.target;
    if (!img || img.dataset.fallbackApplied === "1") return;
    img.dataset.fallbackApplied = "1";
    img.src = TRIP_IMAGE_FALLBACK;
  }

  function renderTripImage(trip) {
    const url = tripImageUrl(trip);
    return `<img class="home-trip-card-photo" src="${url}" alt="" loading="lazy" decoding="async" onerror="gdpTrips.tripImageFallback(event)">`;
  }

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

  function getDisplayName() {
    try {
      return localStorage.getItem(NAME_KEY) || "";
    } catch {
      return "";
    }
  }

  function saveDisplayName(name) {
    try {
      localStorage.setItem(NAME_KEY, name.trim());
    } catch (_) {}
  }

  function escapeHtml(text) {
    const el = document.createElement("span");
    el.textContent = text;
    return el.innerHTML;
  }

  function tripDateRange(trip) {
    if (!trip.date) return { start: null, end: null };
    const numDays = trip.numDays || 1;
    const start = new Date(trip.date + "T12:00:00");
    if (Number.isNaN(start.getTime())) return { start: null, end: null };
    const end = new Date(start);
    end.setDate(end.getDate() + numDays - 1);
    return { start, end };
  }

  function tripStatus(trip) {
    const { start, end } = tripDateRange(trip);
    if (!start || !end) return "upcoming";
    const today = new Date();
    today.setHours(12, 0, 0, 0);
    if (today >= start && today <= end) return "active";
    if (today < start) return "upcoming";
    return "past";
  }

  function statusLabel(status) {
    if (status === "active") return "In progress";
    if (status === "upcoming") return "Upcoming";
    return "Completed";
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
    const month = start.toLocaleDateString(undefined, { month: "short" });
    const year = end.getFullYear();
    if (start.getMonth() === end.getMonth() && start.getFullYear() === year) {
      return month + " " + start.getDate() + "–" + end.getDate() + ", " + year;
    }
    const startStr = start.toLocaleDateString(undefined, { month: "short", day: "numeric" });
    const endStr = end.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
    return startStr + " – " + endStr;
  }

  function saveTrip(trip) {
    const trips = getTrips();
    const idx = trips.findIndex((t) => t.code === trip.code);
    const prev = idx >= 0 ? trips[idx] : null;
    const entry = {
      code: trip.code,
      name: trip.name,
      date: trip.date,
      location: trip.location,
      numDays: trip.numDays || 1,
      isCreator: trip.isCreator !== undefined ? !!trip.isCreator : !!(prev && prev.isCreator),
      published: trip.published !== undefined ? !!trip.published : !!(prev && prev.published),
      activityCount: trip.activityCount !== undefined ? trip.activityCount : (prev && prev.activityCount) || 0,
      members: trip.members !== undefined ? trip.members : (prev && prev.members) || [],
      joinedAt: prev ? prev.joinedAt : new Date().toISOString(),
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

  async function deleteTripOnServer(code) {
    const res = await fetch(`/t/${encodeURIComponent(code)}/delete`, { method: "POST" });
    if (res.ok) return true;
    if (res.status === 403 || res.status === 404) return false;
    throw new Error("Delete failed");
  }

  async function handleTripDelete(btn, onChange) {
    const code = btn.dataset.code;
    const name = btn.dataset.name || "this trip";
    const isCreator = btn.dataset.creator === "1";
    const message = isCreator
      ? `Delete "${name}"? This permanently removes the trip for everyone. This cannot be undone.`
      : `Remove "${name}" from your list? The trip will still exist for other travelers.`;
    const confirmFn = window.showConfirm || ((msg) => Promise.resolve(window.confirm(msg)));
    const ok = await confirmFn(message);
    if (!ok) return;

    if (isCreator) {
      try {
        const deleted = await deleteTripOnServer(code);
        if (!deleted) {
          window.alert("Could not delete this trip. Only the trip creator can delete it.");
          return;
        }
      } catch (_) {
        window.alert("Could not delete this trip. Please try again.");
        return;
      }
    }

    removeTrip(code);
    if (onChange) onChange();
  }

  async function fetchTripStatus(code) {
    const res = await fetch(`/t/${encodeURIComponent(code)}/exists`);
    if (!res.ok) return null;
    return res.json();
  }

  async function discoverTripsFromServer() {
    try {
      const res = await fetch("/api/my-trips");
      if (!res.ok) return;
      const data = await res.json();
      for (const trip of data.trips || []) {
        saveTrip({
          code: trip.code,
          name: trip.name,
          date: trip.date,
          location: trip.location,
          numDays: trip.num_days || 1,
          isCreator: !!trip.is_creator,
          published: !!trip.published,
          activityCount: trip.activity_count || 0,
          members: trip.members || [],
        });
      }
    } catch (_) {}
  }

  async function pruneStaleTrips() {
    const trips = getTrips();
    if (!trips.length) return 0;

    const results = await Promise.all(
      trips.map((trip) => fetchTripStatus(trip.code).catch(() => null))
    );

    const valid = trips.filter((_, i) => {
      const status = results[i];
      if (!status) return true;
      return status.exists;
    });
    const removed = trips.length - valid.length;
    if (removed > 0) {
      setTrips(valid);
    }
    return removed;
  }

  async function syncTripStatuses() {
    const trips = getTrips();
    if (!trips.length) return;

    const results = await Promise.all(
      trips.map((trip) => fetchTripStatus(trip.code).catch(() => null))
    );

    let changed = false;
    const updated = trips.map((trip, i) => {
      const status = results[i];
      if (!status || !status.exists) return trip;
      const next = {
        ...trip,
        name: status.name || trip.name,
        date: status.date || trip.date,
        location: status.location || trip.location,
        numDays: status.num_days || trip.numDays || 1,
        published: !!status.published,
        activityCount: status.activity_count ?? trip.activityCount ?? 0,
        members: status.members || trip.members || [],
      };
      if (JSON.stringify(next) !== JSON.stringify(trip)) {
        changed = true;
      }
      return next;
    });

    if (changed) {
      setTrips(updated);
    }
  }

  function filterTrips(trips, filter) {
    if (filter === "all") return trips;
    return trips.filter((t) => tripStatus(t) === filter);
  }

  function renderTripGrid(gridEl, filter, onChange) {
    if (!gridEl) return;
    let trips = filterTrips(getTrips(), filter || "all");

    const cards = trips.map((trip, i) => {
      const status = tripStatus(trip);
      const href = `/t/${encodeURIComponent(trip.code)}`;
      const theme = ["coral", "purple", "green", "teal"][i % 4];
      const count = trip.activityCount || 0;
      const members = trip.members && trip.members.length ? trip.members : [{ initial: "?", name: "You" }];
      const avatars = members
        .slice(0, 4)
        .map((m, j) => {
          const bg = ["#e87868", "#7ca0d4", "#58c070", "#9b80d0"][j % 4];
          return `<span class="home-trip-avatar" style="background:${bg}" title="${escapeHtml(m.name || "")}">${escapeHtml(m.initial || "?")}</span>`;
        })
        .join("");

      return `
        <article class="home-trip-card">
          <a href="${href}" class="home-trip-card-link">
            <div class="home-trip-card-image">
              ${renderTripImage(trip)}
              <span class="home-trip-badge">
                <span class="home-trip-badge-dot home-trip-badge-dot--${status}"></span>
                ${statusLabel(status)}
              </span>
              ${count > 0 ? `<span class="home-trip-count"><svg viewBox="0 0 24 24"><path d="M12 2l2.4 7.2H22l-6 4.6 2.3 7.2L12 17l-6.3 4 2.3-7.2-6-4.6h7.6z"/></svg>${count}</span>` : ""}
            </div>
            <div class="home-trip-body">
              <h2 class="home-trip-name">${escapeHtml(trip.name)}</h2>
              <div class="home-trip-meta">
                <span class="home-trip-meta-row">
                  <svg viewBox="0 0 24 24"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
                  ${escapeHtml(trip.location || "")}
                </span>
                <span class="home-trip-meta-row">
                  <svg viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
                  ${escapeHtml(formatTripDates(trip))}
                </span>
              </div>
            </div>
          </a>
          <div class="home-trip-footer">
            <div class="home-trip-avatars">${avatars}</div>
            <div class="home-trip-actions">
              <button type="button" class="home-trip-delete" data-code="${escapeHtml(trip.code)}" data-name="${escapeHtml(trip.name)}" data-creator="${trip.isCreator ? "1" : "0"}" title="${trip.isCreator ? "Delete trip" : "Remove from list"}" aria-label="${trip.isCreator ? "Delete trip" : "Remove from list"}">
                <svg viewBox="0 0 24 24" aria-hidden="true"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>
              </button>
              <a href="${href}" class="home-trip-open home-trip-open--${theme}">Open ›</a>
            </div>
          </div>
        </article>`;
    });

    const newCard = `
      <button type="button" class="home-trip-card--new" data-action="new-trip">
        <span class="home-trip-new-icon">+</span>
        <span class="home-trip-new-label">Plan a new trip</span>
      </button>`;

    if (cards.length === 0 && filter !== "all") {
      gridEl.innerHTML = `<p class="home-empty-trips">No ${filter} trips yet.</p>` + newCard;
    } else {
      gridEl.innerHTML = cards.join("") + newCard;
    }

    gridEl.querySelector("[data-action='new-trip']")?.addEventListener("click", () => {
      document.querySelector("[data-modal='create']")?.click();
    });

    gridEl.querySelectorAll(".home-trip-delete").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        handleTripDelete(btn, onChange);
      });
    });
  }

  function renderTripList(listEl, emptyEl, options) {
    const { filterPublished, linkToPlan } = options;
    let trips = getTrips();
    if (filterPublished === true) {
      trips = trips.filter((t) => t.published);
    } else if (filterPublished === false) {
      trips = trips.filter((t) => !t.published);
    }

    const hasTrips = trips.length > 0;
    if (emptyEl) {
      emptyEl.classList.toggle("hidden", hasTrips);
    }
    if (!listEl) return;
    if (!hasTrips) {
      listEl.innerHTML = "";
      return;
    }

    listEl.innerHTML = trips
      .map((trip) => {
        const href = `/t/${encodeURIComponent(trip.code)}`;
        const badge = linkToPlan
          ? '<span class="text-xs font-medium rounded-full px-2.5 py-1 bg-emerald-100 text-emerald-700 shrink-0">Published</span>'
          : trip.isCreator
            ? '<span class="text-xs font-medium rounded-full px-2.5 py-1 bg-primary-badge text-primary shrink-0">Creator</span>'
            : "";
        return `
      <div class="flex items-stretch gap-1 bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
        <a href="${href}" class="flex-1 flex items-center justify-between gap-3 px-4 py-3.5 no-underline text-inherit hover:bg-gray-50">
          <div>
            <p class="font-semibold mb-0.5">${escapeHtml(trip.name)}</p>
            <p class="text-sm text-gray-500">${escapeHtml(formatTripDates(trip))} · ${escapeHtml(trip.location)}</p>
          </div>
          ${badge}
        </a>
        <button type="button" class="shrink-0 self-center mr-2 border border-gray-200 rounded-lg w-7 h-7 p-0 bg-white text-gray-500 cursor-pointer text-sm leading-none hover:bg-red-50 hover:text-red-600 hover:border-red-200" data-code="${escapeHtml(trip.code)}" title="Remove from your list" aria-label="Remove from your list">✕</button>
      </div>`;
      })
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
        if (options.onRemove) options.onRemove();
      });
    });
  }

  function renderYourTrips(listEl, sectionEl, emptyEl, onChange) {
    const trips = getTrips();
    if (sectionEl) {
      sectionEl.classList.toggle("hidden", trips.length === 0);
    }
    renderTripList(listEl, emptyEl, {
      filterPublished: null,
      linkToPlan: false,
      onRemove: () => {
        renderYourTrips(listEl, sectionEl, emptyEl, onChange);
        if (onChange) onChange();
      },
    });
  }

  function renderPublishedTrips(listEl, emptyEl, onChange) {
    renderTripList(listEl, emptyEl, {
      filterPublished: true,
      linkToPlan: true,
      onRemove: () => {
        renderPublishedTrips(listEl, emptyEl, onChange);
        if (onChange) onChange();
      },
    });
  }

  async function autoSaveTripFromPath() {
    const match = location.pathname.match(/^\/t\/([a-z0-9]+)/);
    if (!match) return;
    const code = match[1];
    const status = await fetchTripStatus(code).catch(() => null);
    if (!status || !status.exists) return;
    saveTrip({
      code,
      name: status.name,
      date: status.date,
      location: status.location,
      numDays: status.num_days || 1,
      isCreator: !!status.is_creator,
      published: !!status.published,
      activityCount: status.activity_count || 0,
      members: status.members || [],
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", autoSaveTripFromPath);
  } else {
    autoSaveTripFromPath();
  }

  window.gdpTrips = {
    tripImageFallback,
    renderTripImage,
    getTrips,
    saveTrip,
    removeTrip,
    discoverTripsFromServer,
    pruneStaleTrips,
    syncTripStatuses,
    renderYourTrips,
    renderPublishedTrips,
    renderTripGrid,
    getDisplayName,
    saveDisplayName,
    tripStatus,
    formatTripDates,
  };
})();
