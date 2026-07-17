(function () {
  const MAX_CITIES = 8;
  const MAX_COUNTRIES = 6;
  const CD = () => window.gdpCountryData || {};

  function inferCountry(text) {
    return CD().inferCountry ? CD().inferCountry(text) : { name: "", code: "" };
  }

  function countryFlag(code) {
    return CD().countryFlag ? CD().countryFlag(code) : "🌍";
  }

  function countryNameToCode(name) {
    return CD().countryNameToCode ? CD().countryNameToCode(name) : "";
  }

  function pinIconSvg() {
    return (
      '<span class="home-field-icon" aria-hidden="true">' +
      '<svg viewBox="0 0 24 24"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>' +
      "</span>"
    );
  }

  function parseInitialData(root) {
    const raw = root.dataset.routePlan;
    if (!raw) return null;
    try {
      return JSON.parse(raw);
    } catch (_e) {
      return null;
    }
  }

  function isShortMode(root) {
    return root && root.classList.contains("route-planner--short");
  }

  function defaultPlan(root) {
    if (root && root.classList.contains("route-planner--full")) {
      return {
        countries: [{ name: "", code: null, cities: [{ name: "", days: 3 }] }],
      };
    }
    const days = isShortMode(root) ? 1 : 3;
    return { mode: "simple", cities: [{ name: "", days }] };
  }

  function isMultiMode(root) {
    return root.dataset.routeMode === "multi";
  }

  function setMultiMode(root, multi) {
    root.dataset.routeMode = multi ? "multi" : "simple";
    const toggle = root.querySelector("[data-route-multi-toggle]");
    if (toggle) toggle.checked = multi;
    const simpleEl = root.querySelector("[data-route-simple]");
    const multiEl = root.querySelector("[data-route-multi]");
    if (simpleEl) simpleEl.classList.toggle("hidden", multi);
    if (multiEl) multiEl.classList.toggle("hidden", !multi);
  }

  function syncCityCountryScope(countryEl) {
    if (!countryEl) return;
    const code = (countryEl.dataset.countryCode || "").trim();
    countryEl.querySelectorAll("[data-route-city-name]").forEach((input) => {
      if (code) input.dataset.locationCountry = code;
      else delete input.dataset.locationCountry;
    });
  }

  function dayValueEl(cityEl) {
    if (!cityEl) return null;
    return (
      cityEl.querySelector("[data-route-city-days-wrap] [data-route-city-days]") ||
      cityEl.querySelector("[data-route-city-days]")
    );
  }

  function writeCityDaysDisplay(cityEl, days, valEl) {
    const el = valEl || dayValueEl(cityEl);
    if (!el) return;
    const text = String(days);
    if (el.tagName === "INPUT") {
      if (el.value !== text) el.value = text;
    } else if (el.textContent !== text) {
      el.textContent = text;
    }
  }

  function readCityDays(cityEl) {
    if (!cityEl) return 1;
    const valEl = dayValueEl(cityEl);
    let days = NaN;
    if (valEl) {
      const raw = valEl.tagName === "INPUT" ? valEl.value : valEl.textContent;
      days = parseInt(String(raw).trim(), 10);
    }
    if (!Number.isFinite(days) || days < 1) {
      days = parseInt(cityEl.dataset.cityDays || "", 10);
    }
    if (!Number.isFinite(days) || days < 1) days = 1;
    days = Math.max(1, Math.min(30, days));
    cityEl.dataset.cityDays = String(days);
    writeCityDaysDisplay(cityEl, days, valEl);
    return days;
  }

  function setCityDays(cityEl, days) {
    const n = Math.max(1, Math.min(30, days));
    cityEl.dataset.cityDays = String(n);
    writeCityDaysDisplay(cityEl, n);
  }

  function syncAllCityDayDisplays(root) {
    cityRowsInDom(root).forEach((cityEl) => {
      const n = parseInt(cityEl.dataset.cityDays || "1", 10);
      writeCityDaysDisplay(cityEl, Number.isFinite(n) && n >= 1 ? n : 1);
    });
  }

  function cityRowsInDom(root) {
    const selector = isMultiMode(root)
      ? "[data-route-multi] [data-route-city]"
      : "[data-route-simple] [data-route-city]";
    return root.querySelectorAll(selector);
  }

  function sumDaysFromDom(root) {
    let total = 0;
    cityRowsInDom(root).forEach((cityEl) => {
      const name = (cityEl.querySelector("[data-route-city-name]")?.value || "").trim();
      if (!name) return;
      total += readCityDays(cityEl);
    });
    return total;
  }

  function collectPlan(root) {
    if (isMultiMode(root)) {
      const countries = [];
      root.querySelectorAll("[data-route-country]").forEach((countryEl) => {
        const nameInput = countryEl.querySelector("[data-route-country-name]");
        const code = (countryEl.dataset.countryCode || "").trim() || null;
        const name = (nameInput?.value || "").trim();
        const cities = [];
        countryEl.querySelectorAll("[data-route-city]").forEach((cityEl) => {
          const input = cityEl.querySelector("[data-route-city-name]");
          const cityName = (input?.value || "").trim();
          if (!cityName) return;
          const days = readCityDays(cityEl);
          cities.push({ name: cityName, days });
        });
        if (cities.length) {
          countries.push({
            name: name || inferCountry(cities[0].name).name,
            code,
            cities,
          });
        }
      });
      return { mode: "multi", countries };
    }

    const cities = [];
    root.querySelectorAll("[data-route-simple] [data-route-city]").forEach((cityEl) => {
      const input = cityEl.querySelector("[data-route-city-name]");
      const cityName = (input?.value || "").trim();
      if (!cityName) return;
      const days = readCityDays(cityEl);
      cities.push({ name: cityName, days });
    });
    return { mode: "simple", cities };
  }

  function planForSubmit(plan) {
    if (plan.mode === "simple" && plan.cities?.length) {
      return { mode: "simple", cities: plan.cities };
    }
    return { countries: plan.countries || [] };
  }

  function computeTimeline(plan) {
    const rows = [];
    let day = 1;
    const groups =
      plan.mode === "simple"
        ? [{ name: "", code: null, cities: plan.cities || [] }]
        : plan.countries || [];

    for (const country of groups) {
      for (const city of country.cities || []) {
        const days = Math.max(1, city.days || 1);
        const start = day;
        const end = day + days - 1;
        rows.push({
          city: city.name,
          country: country.name || inferCountry(city.name).name,
          countryCode: country.code || inferCountry(city.name).code,
          start,
          end,
          days,
        });
        day = end + 1;
      }
    }
    return { rows, totalDays: Math.max(0, day - 1) };
  }

  function formatDayRange(start, end) {
    if (start === end) return "Day " + start;
    return "Days " + start + "–" + end;
  }

  function countStats(root, plan) {
    const { rows } = computeTimeline(plan);
    const countries = new Set(rows.map((r) => r.country).filter(Boolean));
    const domDays = sumDaysFromDom(root);
    return {
      countries: countries.size || (plan.mode === "simple" ? 0 : (plan.countries || []).length),
      cities: rows.length,
      totalDays: domDays > 0 ? domDays : computeTimeline(plan).totalDays,
    };
  }

  function applyFormNumDays(root) {
    if (!isShortMode(root) || isMultiMode(root)) return;
    const form = root.closest("form");
    const numDaysInput = form?.querySelector("[data-route-num-days]");
    const n = parseInt(numDaysInput?.value || "", 10);
    if (!Number.isFinite(n) || n < 1) return;
    const cities = root.querySelectorAll("[data-route-simple] [data-route-city]");
    if (cities.length === 1) {
      setCityDays(cities[0], n);
    }
  }

  function syncHiddenInput(root) {
    const input = root.querySelector("[data-route-plan-input]");
    if (!input) return;
    const plan = collectPlan(root);
    input.value = JSON.stringify(planForSubmit(plan));
    return plan;
  }

  function syncNumDays(root, totalDays) {
    const form = root.closest("form");
    if (!form) return;
    const numDaysInput = form.querySelector('input[name="num_days"], [data-route-num-days]');
    if (numDaysInput && totalDays > 0) {
      numDaysInput.value = String(totalDays);
      if (numDaysInput.dataset.routeNumDays !== undefined && !isShortMode(root)) {
        numDaysInput.readOnly = true;
      }
    }
  }

  function renderSummary(root, plan) {
    const summary = root.querySelector("[data-route-summary]");
    if (!summary) return;
    const stats = countStats(root, plan);
    if (!stats.cities) {
      summary.innerHTML = '<span class="route-planner-timeline-empty">Add cities to see your route</span>';
      return;
    }
    summary.innerHTML =
      "<strong>" +
      stats.totalDays +
      " day" +
      (stats.totalDays === 1 ? "" : "s") +
      "</strong>" +
      '<span class="route-planner-summary-dot">·</span>' +
      (stats.countries || 1) +
      " countr" +
      ((stats.countries || 1) === 1 ? "y" : "ies") +
      '<span class="route-planner-summary-dot">·</span>' +
      stats.cities +
      " cit" +
      (stats.cities === 1 ? "y" : "ies");
    syncNumDays(root, stats.totalDays);
  }

  function renderTimeline(root, plan) {
    const timeline = root.querySelector("[data-route-timeline]");
    if (!timeline) return;
    const { rows } = computeTimeline(plan);
    if (!rows.length) {
      timeline.innerHTML =
        '<div class="route-planner-timeline-label">Route preview</div>' +
        '<div class="route-planner-timeline-empty">Your day-by-day route appears here</div>';
      return;
    }
    timeline.innerHTML =
      '<div class="route-planner-timeline-label">Route preview</div>' +
      '<div class="route-planner-timeline-track">' +
      rows
        .map(
          (row, idx) =>
            '<button type="button" class="route-planner-timeline-row" data-timeline-idx="' +
            idx +
            '">' +
            '<span class="route-planner-timeline-marker" aria-hidden="true"></span>' +
            '<span class="route-planner-timeline-body">' +
            '<span class="route-planner-timeline-days">' +
            formatDayRange(row.start, row.end) +
            "</span>" +
            '<span class="route-planner-timeline-city">' +
            row.city +
            (row.country
              ? '<span class="route-planner-timeline-country"> · ' + row.country + "</span>"
              : "") +
            "</span>" +
            "</span>" +
            "</button>"
        )
        .join("") +
      "</div>";
  }

  function renderWarnings(root, plan) {
    const warn = root.querySelector("[data-route-warnings]");
    if (!warn) return;
    const names = [];
    const dupes = [];
    const groups =
      plan.mode === "simple"
        ? [{ cities: plan.cities || [] }]
        : plan.countries || [];
    for (const g of groups) {
      for (const c of g.cities || []) {
        const n = (c.name || "").trim().toLowerCase();
        if (!n) continue;
        if (names.includes(n)) dupes.push(c.name);
        else names.push(n);
      }
    }
    if (dupes.length) {
      warn.textContent = "Note: duplicate city — " + dupes.join(", ");
      warn.classList.remove("hidden");
    } else {
      warn.textContent = "";
      warn.classList.add("hidden");
    }
  }

  function refreshShortUI(root) {
    const cities = root.querySelectorAll("[data-route-simple] [data-route-city]");
    cities.forEach((row) => {
      const removeBtn = row.querySelector("[data-route-city-remove]");
      if (removeBtn) removeBtn.classList.toggle("hidden", cities.length <= 1);
    });
    const addBtn = root.querySelector("[data-route-simple-add-city]");
    if (addBtn) addBtn.classList.toggle("hidden", cities.length >= MAX_CITIES);
  }

  function refreshUI(root) {
    const plan = syncHiddenInput(root);
    if (!isShortMode(root)) {
      renderSummary(root, plan);
      renderTimeline(root, plan);
      renderWarnings(root, plan);
    } else {
      refreshShortUI(root);
      syncNumDays(root, countStats(root, plan).totalDays);
    }
    if (window.gdpInitLucide) window.gdpInitLucide(root);
    syncAllCityDayDisplays(root);
  }

  function applyCountryMeta(countryEl, name, code) {
    const nameInput = countryEl.querySelector("[data-route-country-name]");
    const flagEl = countryEl.querySelector("[data-route-country-flag]");
    if (name && nameInput && !nameInput.value.trim()) nameInput.value = name;
    if (code) {
      countryEl.dataset.countryCode = code;
      if (flagEl) flagEl.textContent = countryFlag(code);
    }
    syncCityCountryScope(countryEl);
  }

  function handleCitySelected(root, row, detail) {
    const countryName = (detail && detail.country) || "";
    const countryCode = (detail && detail.countrycode) || countryNameToCode(countryName) || "";
    const inferred = countryCode
      ? { name: countryName || (CD().COUNTRY_CODES || {})[countryCode], code: countryCode }
      : inferCountry((detail && detail.label) || row.querySelector("[data-route-city-name]")?.value || "");

    if (isMultiMode(root)) {
      const countryEl = row.closest("[data-route-country]");
      if (!countryEl) return;
      const currentCode = (countryEl.dataset.countryCode || "").trim();
      if (!currentCode && inferred.code) {
        applyCountryMeta(countryEl, inferred.name, inferred.code);
      } else if (inferred.code && currentCode && inferred.code !== currentCode) {
        moveCityToCountry(root, row, inferred);
      }
      return;
    }

    refreshUI(root);
  }

  function moveCityToCountry(root, row, inferred) {
    let target = null;
    root.querySelectorAll("[data-route-country]").forEach((el) => {
      if ((el.dataset.countryCode || "") === inferred.code) target = el;
    });
    if (!target) {
      const countriesEl = root.querySelector("[data-route-countries]");
      if (!countriesEl || root.querySelectorAll("[data-route-country]").length >= MAX_COUNTRIES) return;
      target = createCountryCard(root, { name: inferred.name, code: inferred.code, cities: [] }, root.classList.contains("route-planner--edit"));
      countriesEl.appendChild(target);
    }
    const citiesEl = target.querySelector("[data-route-cities]");
    citiesEl.appendChild(row);
    applyCountryMeta(target, inferred.name, inferred.code);
    refreshUI(root);
  }

  function bindCityRow(root, row, isEdit) {
    const input = row.querySelector("[data-route-city-name]");
    const countryEl = row.closest("[data-route-country]");

    input?.addEventListener("input", () => refreshUI(root));
    input?.addEventListener("gdp:location-selected", (event) => {
      handleCitySelected(root, row, event.detail);
      refreshUI(root);
      focusNextCityOrCreate(root, row);
    });
    input?.addEventListener("blur", () => {
      if (countryEl) {
        const val = input?.value || "";
        if (!countryEl.dataset.countryCode) {
          const inf = inferCountry(val);
          if (inf.code) applyCountryMeta(countryEl, inf.name, inf.code);
        }
      }
      refreshUI(root);
    });
    input?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        focusNextCityOrCreate(root, row);
      }
    });

    row.querySelector("[data-route-day-dec]")?.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      setCityDays(row, readCityDays(row) - 1);
      refreshUI(root);
    });
    row.querySelector("[data-route-day-inc]")?.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      setCityDays(row, readCityDays(row) + 1);
      refreshUI(root);
    });
    const daysInput = row.querySelector("[data-route-city-days]");
    daysInput?.addEventListener("input", () => {
      readCityDays(row);
      refreshUI(root);
    });
    daysInput?.addEventListener("change", () => {
      readCityDays(row);
      refreshUI(root);
    });
    row.querySelector("[data-route-city-remove]")?.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      const container = row.parentElement;
      const rows = container?.querySelectorAll("[data-route-city]") || [];
      if (rows.length <= 1) return;
      row.remove();
      refreshUI(root);
    });

    if (!isShortMode(root)) bindCityDrag(root, row);
    if (countryEl) syncCityCountryScope(countryEl);
  }

  function createCityRow(root, city, isEdit) {
    const row = document.createElement("div");
    const short = isShortMode(root);
    row.className = "route-planner-city" + (short ? " route-planner-city--short" : "");
    row.dataset.routeCity = "";
    row.draggable = false;
    row.dataset.cityDays = String(city?.days || (short ? 1 : 3));
    const inputClass = isEdit ? "route-planner-city-input route-planner-city-input--plain" : "route-planner-city-input";
    const days = city?.days || (short ? 1 : 3);
    const name = city?.name || "";
    const placeholder = short ? "e.g. Lisbon" : "City name";
    row.innerHTML =
      (short
        ? ""
        : '<span class="route-planner-drag-handle" data-route-drag-handle aria-hidden="true" title="Drag to reorder">⠿</span>') +
      '<div class="route-planner-city-input-wrap">' +
      (isEdit ? "" : pinIconSvg()) +
      '<input type="text" class="' +
      inputClass +
      '" data-route-city-name data-location-autocomplete data-location-type="city" placeholder="' +
      placeholder +
      '" value="' +
      String(name).replace(/"/g, "&quot;") +
      '">' +
      "</div>" +
      '<div class="route-planner-city-days" data-route-city-days-wrap>' +
      (short ? '<span class="route-planner-day-label">Days</span>' : "") +
      '<button type="button" class="route-planner-day-btn" data-route-day-dec aria-label="Fewer days">−</button>' +
      '<input type="number" class="route-planner-day-value" data-route-city-days min="1" max="30" value="' +
      days +
      '" inputmode="numeric" aria-label="Days in city">' +
      '<button type="button" class="route-planner-day-btn" data-route-day-inc aria-label="More days">+</button>' +
      "</div>" +
      '<button type="button" class="route-planner-city-remove' +
      (short ? " hidden" : "") +
      '" data-route-city-remove aria-label="Remove ' +
      (short ? "stop" : "city") +
      '">×</button>';

    bindCityRow(root, row, isEdit);
    return row;
  }

  function focusNextCityOrCreate(root, row) {
    const next = row.nextElementSibling;
    if (next && next.matches("[data-route-city]")) {
      next.querySelector("[data-route-city-name]")?.focus();
      return;
    }
    const addBtn = row
      .closest("[data-route-simple], [data-route-country]")
      ?.querySelector("[data-route-add-city], [data-route-simple-add-city]");
    if (addBtn) addBtn.click();
  }

  function bindCityDrag(root, row) {
    const handle = row.querySelector("[data-route-drag-handle]");
    if (!handle) return;
    let dragRow = null;

    handle.draggable = true;
    handle.addEventListener("dragstart", (e) => {
      dragRow = row;
      row.classList.add("is-dragging");
      e.dataTransfer.effectAllowed = "move";
      if (e.dataTransfer) e.dataTransfer.setData("text/plain", "city");
    });
    handle.addEventListener("dragend", () => {
      row.classList.remove("is-dragging");
      dragRow = null;
      root.querySelectorAll(".route-drop-target").forEach((el) => el.classList.remove("route-drop-target"));
    });
    row.addEventListener("dragover", (e) => {
      if (!dragRow || dragRow === row) return;
      if (dragRow.parentElement !== row.parentElement) return;
      e.preventDefault();
      row.classList.add("route-drop-target");
    });
    row.addEventListener("dragleave", () => row.classList.remove("route-drop-target"));
    row.addEventListener("drop", (e) => {
      e.preventDefault();
      row.classList.remove("route-drop-target");
      if (!dragRow || dragRow === row) return;
      const parent = row.parentElement;
      if (!parent) return;
      const rect = row.getBoundingClientRect();
      const before = e.clientY < rect.top + rect.height / 2;
      if (before) parent.insertBefore(dragRow, row);
      else parent.insertBefore(dragRow, row.nextSibling);
      refreshUI(root);
    });
  }

  function bindCountryDrag(root, card) {
    const handle = card.querySelector("[data-route-country-drag]");
    if (!handle) return;
    let dragCard = null;
    handle.draggable = true;
    handle.addEventListener("dragstart", (e) => {
      dragCard = card;
      card.classList.add("is-dragging");
      e.dataTransfer.effectAllowed = "move";
      if (e.dataTransfer) e.dataTransfer.setData("text/plain", "country");
    });
    handle.addEventListener("dragend", () => {
      card.classList.remove("is-dragging");
      dragCard = null;
    });
    card.addEventListener("dragover", (e) => {
      if (!dragCard || dragCard === card) return;
      e.preventDefault();
      card.classList.add("route-drop-target");
    });
    card.addEventListener("dragleave", () => card.classList.remove("route-drop-target"));
    card.addEventListener("drop", (e) => {
      e.preventDefault();
      card.classList.remove("route-drop-target");
      if (!dragCard || dragCard === card) return;
      const parent = card.parentElement;
      if (!parent) return;
      const rect = card.getBoundingClientRect();
      const before = e.clientY < rect.top + rect.height / 2;
      if (before) parent.insertBefore(dragCard, card);
      else parent.insertBefore(dragCard, card.nextSibling);
      refreshUI(root);
    });
  }

  function createCountryCard(root, country, isEdit) {
    const card = document.createElement("div");
    card.className = "route-planner-country";
    card.dataset.routeCountry = "";
    card.draggable = false;
    const code = country?.code || "";
    const name = country?.name || "";
    if (code) card.dataset.countryCode = code;
    card.innerHTML =
      '<div class="route-planner-country-header">' +
      '<span class="route-planner-drag-handle route-planner-country-drag" data-route-country-drag aria-hidden="true" title="Drag country">⠿</span>' +
      '<span class="route-planner-country-flag" data-route-country-flag>' +
      countryFlag(code) +
      "</span>" +
      '<input type="text" class="route-planner-country-name" data-route-country-name data-location-autocomplete data-location-type="country" placeholder="Country" value="' +
      String(name).replace(/"/g, "&quot;") +
      '">' +
      '<button type="button" class="route-planner-country-remove" data-route-country-remove aria-label="Remove country">×</button>' +
      "</div>" +
      '<div class="route-planner-cities" data-route-cities></div>' +
      '<div class="route-planner-country-footer">' +
      '<button type="button" class="route-planner-add-city" data-route-add-city>+ Add city</button>' +
      "</div>";

    const citiesEl = card.querySelector("[data-route-cities]");
    const cities = country?.cities?.length ? country.cities : [{ name: "", days: 3 }];
    cities.forEach((city) => citiesEl.appendChild(createCityRow(root, city, isEdit)));

    const nameInput = card.querySelector("[data-route-country-name]");
    nameInput?.addEventListener("gdp:location-selected", (event) => {
      const cname = (event.detail && event.detail.country) || event.detail?.label || "";
      const ccode = (event.detail && event.detail.countrycode) || countryNameToCode(cname);
      applyCountryMeta(card, cname, ccode);
      refreshUI(root);
    });
    nameInput?.addEventListener("input", () => {
      const inferred = inferCountry(nameInput.value || "");
      if (inferred.code) applyCountryMeta(card, inferred.name, inferred.code);
      refreshUI(root);
    });

    card.querySelector("[data-route-add-city]")?.addEventListener("click", () => {
      if (root.querySelectorAll("[data-route-city]").length >= MAX_CITIES) return;
      citiesEl.appendChild(createCityRow(root, { name: "", days: 2 }, isEdit));
      reinitAutocomplete();
      citiesEl.lastElementChild?.querySelector("[data-route-city-name]")?.focus();
      refreshUI(root);
    });

    card.querySelector("[data-route-country-remove]")?.addEventListener("click", () => {
      if (root.querySelectorAll("[data-route-country]").length <= 1) return;
      card.remove();
      refreshUI(root);
    });

    bindCountryDrag(root, card);
    syncCityCountryScope(card);
    return card;
  }

  function reinitAutocomplete() {
    if (window.gdpInitLocationAutocomplete) window.gdpInitLocationAutocomplete();
  }

  function renderSimple(root, cities, isEdit) {
    const list = root.querySelector("[data-route-simple-list]");
    if (!list) return;
    list.innerHTML = "";
    const fallbackDays = isShortMode(root) ? 1 : 3;
    (cities || [{ name: "", days: fallbackDays }]).forEach((city) => {
      list.appendChild(createCityRow(root, city, isEdit));
    });
  }

  function renderMulti(root, countries, isEdit) {
    const countriesEl = root.querySelector("[data-route-countries]");
    if (!countriesEl) return;
    countriesEl.innerHTML = "";
    (countries || [{ name: "", code: null, cities: [{ name: "", days: 3 }] }]).forEach((country) => {
      countriesEl.appendChild(createCountryCard(root, country, isEdit));
    });
  }

  function renderPlan(root, data) {
    const isEdit = root.classList.contains("route-planner--edit");
    const plan = data || defaultPlan(root);
    if (isShortMode(root) && (plan.countries?.length || plan.mode === "multi")) {
      const allCities = [];
      (plan.countries || []).forEach((c) => allCities.push(...(c.cities || [])));
      setMultiMode(root, false);
      renderSimple(root, allCities.length ? allCities : [{ name: "", days: 1 }], isEdit);
    } else if (plan.mode === "simple" || (!plan.countries && plan.cities)) {
      setMultiMode(root, false);
      renderSimple(root, plan.cities || [{ name: "", days: isShortMode(root) ? 1 : 3 }], isEdit);
    } else {
      setMultiMode(root, true);
      renderMulti(root, plan.countries, isEdit);
    }
    reinitAutocomplete();
    refreshUI(root);
  }

  function resetShort(root) {
    if (!isShortMode(root)) return;
    setMultiMode(root, false);
    const form = root.closest("form");
    const numDaysInput = form?.querySelector("[data-route-num-days]");
    if (numDaysInput) {
      numDaysInput.readOnly = false;
      numDaysInput.value = "1";
    }
    renderPlan(root, defaultPlan(root));
  }

  function validate(root) {
    const plan = collectPlan(root);
    const stats = countStats(root, plan);
    if (!stats.cities) {
      const firstInput = root.querySelector("[data-route-city-name]");
      if (firstInput) {
        firstInput.setCustomValidity(isShortMode(root) ? "Enter a destination." : "Add at least one city.");
        firstInput.reportValidity();
        firstInput.addEventListener("input", () => firstInput.setCustomValidity(""), { once: true });
      }
      return false;
    }
    if (isMultiMode(root)) {
      const missing = (plan.countries || []).some((c) => !(c.name || "").trim() && !(c.code || ""));
      const warn = root.querySelector("[data-route-warnings]");
      if (missing && warn) {
        warn.textContent = "Enter a country name for each group, or pick a city to auto-detect.";
        warn.classList.remove("hidden");
      }
    }
    return true;
  }

  function saveDraft(root) {
    try {
      const form = root.closest("form");
      const name = form?.querySelector('input[name="name"]')?.value || "";
      sessionStorage.setItem(
        "gdp_route_draft",
        JSON.stringify({ name, plan: collectPlan(root) })
      );
    } catch (_e) {}
  }

  function loadDraft(root) {
    try {
      const raw = sessionStorage.getItem("gdp_route_draft");
      if (!raw) return false;
      const draft = JSON.parse(raw);
      if (draft.plan) renderPlan(root, draft.plan);
      const form = root.closest("form");
      const nameInput = form?.querySelector('input[name="name"]');
      if (nameInput && draft.name && !nameInput.value) nameInput.value = draft.name;
      return true;
    } catch (_e) {
      return false;
    }
  }

  function initPlanner(root) {
    if (root.dataset.routePlannerReady) return;
    root.dataset.routePlannerReady = "1";

    const initial = parseInitialData(root);
    const params = new URLSearchParams(location.search);
    const fromDraft = params.get("from") === "route" || root.dataset.loadDraft === "1";

    if (fromDraft && loadDraft(root)) {
      sessionStorage.removeItem("gdp_route_draft");
    } else {
      renderPlan(root, initial || defaultPlan(root));
    }

    root.querySelector("[data-route-multi-toggle]")?.addEventListener("change", (e) => {
      const multi = e.target.checked;
      if (multi) {
        const plan = collectPlan(root);
        const cities = plan.cities || [];
        setMultiMode(root, true);
        const inferred = cities.length ? inferCountry(cities[0].name) : { name: "", code: "" };
        renderMulti(
          root,
          [{ name: inferred.name, code: inferred.code || null, cities: cities.length ? cities : [{ name: "", days: 3 }] }],
          root.classList.contains("route-planner--edit")
        );
      } else {
        const plan = collectPlan(root);
        const allCities = [];
        (plan.countries || []).forEach((c) => allCities.push(...(c.cities || [])));
        setMultiMode(root, false);
        renderSimple(root, allCities.length ? allCities : [{ name: "", days: 3 }], root.classList.contains("route-planner--edit"));
      }
      reinitAutocomplete();
      refreshUI(root);
    });

    root.querySelector("[data-route-simple-add-city]")?.addEventListener("click", () => {
      const list = root.querySelector("[data-route-simple-list]");
      if (!list || root.querySelectorAll("[data-route-city]").length >= MAX_CITIES) return;
      const extraDays = isShortMode(root) ? 1 : 2;
      list.appendChild(createCityRow(root, { name: "", days: extraDays }, root.classList.contains("route-planner--edit")));
      reinitAutocomplete();
      list.lastElementChild?.querySelector("[data-route-city-name]")?.focus();
      refreshUI(root);
    });

    root.querySelectorAll("[data-route-add-country]").forEach((btn) => {
      btn.addEventListener("click", () => {
        if (isShortMode(root)) {
          saveDraft(root);
          const form = root.closest("form");
          const name = encodeURIComponent(form?.querySelector('input[name="name"]')?.value || "");
          window.location.href = "/create/route?name=" + name;
          return;
        }
        setMultiMode(root, true);
        const countriesEl = root.querySelector("[data-route-countries]");
        if (!countriesEl || root.querySelectorAll("[data-route-country]").length >= MAX_COUNTRIES) return;
        countriesEl.appendChild(
          createCountryCard(root, { name: "", code: null, cities: [{ name: "", days: 2 }] }, root.classList.contains("route-planner--edit"))
        );
        reinitAutocomplete();
        countriesEl.lastElementChild?.querySelector("[data-route-city-name]")?.focus();
        refreshUI(root);
      });
    });

    root.querySelector("[data-route-longer-link]")?.addEventListener("click", () => {
      saveDraft(root);
      const form = root.closest("form");
      const name = encodeURIComponent(form?.querySelector('input[name="name"]')?.value || "");
      window.location.href = "/create/route?name=" + name;
    });

    root.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-timeline-idx]");
      if (!btn) return;
      const idx = parseInt(btn.dataset.timelineIdx, 10);
      const rows = root.querySelectorAll("[data-route-city]");
      if (rows[idx]) {
        rows[idx].scrollIntoView({ behavior: "smooth", block: "nearest" });
        rows[idx].classList.add("route-highlight");
        setTimeout(() => rows[idx].classList.remove("route-highlight"), 1200);
      }
    });

    const form = root.closest("form");
    if (form && !form.dataset.routePlanBound) {
      form.dataset.routePlanBound = "1";
      form.addEventListener("submit", (e) => {
        applyFormNumDays(root);
        syncHiddenInput(root);
        if (!validate(root)) e.preventDefault();
      });
    }
  }

  function initAll() {
    document.querySelectorAll("[data-route-planner]").forEach(initPlanner);
  }

  window.gdpRoutePlanner = {
    validate,
    refresh: refreshUI,
    collectPlan,
    saveDraft,
    renderPlan,
    resetShort,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initAll);
  } else {
    initAll();
  }
})();
