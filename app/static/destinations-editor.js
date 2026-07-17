(function () {
  const MAX_DESTINATIONS = 8;

  const COUNTRY_HINTS = [
    ["france", "France"],
    ["paris", "France"],
    ["lyon", "France"],
    ["marseille", "France"],
    ["nice", "France"],
    ["bordeaux", "France"],
    ["toulouse", "France"],
    ["corsica", "France"],
    ["corse", "France"],
    ["london", "United Kingdom"],
    ["edinburgh", "United Kingdom"],
    ["manchester", "United Kingdom"],
    ["england", "United Kingdom"],
    ["scotland", "United Kingdom"],
    ["wales", "United Kingdom"],
    ["uk", "United Kingdom"],
    ["spain", "Spain"],
    ["barcelona", "Spain"],
    ["madrid", "Spain"],
    ["seville", "Spain"],
    ["sevilla", "Spain"],
    ["valencia", "Spain"],
    ["italy", "Italy"],
    ["rome", "Italy"],
    ["roma", "Italy"],
    ["milan", "Italy"],
    ["milano", "Italy"],
    ["florence", "Italy"],
    ["firenze", "Italy"],
    ["venice", "Italy"],
    ["naples", "Italy"],
    ["napoli", "Italy"],
    ["portugal", "Portugal"],
    ["lisbon", "Portugal"],
    ["lisboa", "Portugal"],
    ["porto", "Portugal"],
    ["germany", "Germany"],
    ["berlin", "Germany"],
    ["munich", "Germany"],
    ["hamburg", "Germany"],
    ["netherlands", "Netherlands"],
    ["amsterdam", "Netherlands"],
    ["rotterdam", "Netherlands"],
    ["belgium", "Belgium"],
    ["brussels", "Belgium"],
    ["bruges", "Belgium"],
    ["switzerland", "Switzerland"],
    ["zurich", "Switzerland"],
    ["geneva", "Switzerland"],
    ["austria", "Austria"],
    ["vienna", "Austria"],
    ["greece", "Greece"],
    ["athens", "Greece"],
    ["ireland", "Ireland"],
    ["dublin", "Ireland"],
    ["japan", "Japan"],
    ["tokyo", "Japan"],
    ["kyoto", "Japan"],
    ["osaka", "Japan"],
    ["usa", "United States"],
    ["united states", "United States"],
    ["new york", "United States"],
    ["nyc", "United States"],
    ["san francisco", "United States"],
    ["los angeles", "United States"],
    ["california", "United States"],
    ["chicago", "United States"],
    ["canada", "Canada"],
    ["toronto", "Canada"],
    ["vancouver", "Canada"],
    ["montreal", "Canada"],
    ["australia", "Australia"],
    ["sydney", "Australia"],
    ["melbourne", "Australia"],
    ["thailand", "Thailand"],
    ["bangkok", "Thailand"],
    ["koh tao", "Thailand"],
    ["phuket", "Thailand"],
    ["chiang mai", "Thailand"],
    ["malaysia", "Malaysia"],
    ["kuala lumpur", "Malaysia"],
    ["malacca", "Malaysia"],
    ["melaka", "Malaysia"],
    ["penang", "Malaysia"],
    ["langkawi", "Malaysia"],
    ["johor bahru", "Malaysia"],
    ["kota kinabalu", "Malaysia"],
    ["vietnam", "Vietnam"],
    ["viet nam", "Vietnam"],
    ["hanoi", "Vietnam"],
    ["ha noi", "Vietnam"],
    ["ho chi minh", "Vietnam"],
    ["saigon", "Vietnam"],
    ["ninh binh", "Vietnam"],
    ["hoa lu", "Vietnam"],
    ["da nang", "Vietnam"],
    ["hoi an", "Vietnam"],
  ];

  function inferCountry(text) {
    const loc = (text || "").toLowerCase();
    if (!loc) return "";
    for (const [hint, name] of COUNTRY_HINTS) {
      if (loc.includes(hint)) return name;
    }
    const parts = loc.split(",").map((s) => s.trim()).filter(Boolean);
    if (parts.length >= 2) {
      const last = parts[parts.length - 1];
      for (const [hint, name] of COUNTRY_HINTS) {
        if (last === hint || last === name.toLowerCase()) return name;
      }
    }
    return "";
  }

  function shortCity(name, country) {
    const text = (name || "").trim();
    if (!text) return "";
    const parts = text.split(",").map((p) => p.trim()).filter(Boolean);
    if (parts.length <= 1) return text;
    const countryFold = (country || "").toLowerCase();
    while (
      parts.length > 1 &&
      countryFold &&
      parts[parts.length - 1].toLowerCase() === countryFold
    ) {
      parts.pop();
    }
    return parts[0];
  }

  function pinIconSvg() {
    return (
      '<span class="home-field-icon" aria-hidden="true">' +
      '<svg viewBox="0 0 24 24"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>' +
      "</span>"
    );
  }

  function isHomeEditor(editor) {
    return editor.classList.contains("home-destinations") || !!editor.closest(".home-modal");
  }

  function ensureRowStructure(row, isHome) {
    let main = row.querySelector("[data-destination-main]");
    if (!main) {
      main = document.createElement(isHome ? "span" : "div");
      main.dataset.destinationMain = "";
      main.className = isHome ? "home-destination-main" : "edit-destination-main";

      const wrap = row.querySelector(".home-field-wrap") || row.querySelector("input[name='locations']")?.parentElement;
      const input = row.querySelector("input[name='locations']");
      const removeBtn = row.querySelector("[data-destination-remove]");

      if (isHome && wrap) {
        main.appendChild(wrap);
      } else if (input) {
        const field = document.createElement("div");
        field.className = "edit-destination-field";
        field.appendChild(input);
        main.appendChild(field);
      }

      let chip = row.querySelector("[data-destination-country]");
      if (!chip) {
        chip = document.createElement("span");
        chip.className = "destination-country-chip hidden";
        chip.dataset.destinationCountry = "";
        main.appendChild(chip);
      }

      row.insertBefore(main, removeBtn || null);
    }

    let chip = main.querySelector("[data-destination-country]");
    if (!chip) {
      chip = document.createElement("span");
      chip.className = "destination-country-chip hidden";
      chip.dataset.destinationCountry = "";
      main.appendChild(chip);
    }

    let label = row.querySelector("[data-destination-label]");
    if (!label) {
      label = document.createElement("span");
      label.className = "destination-city-label hidden";
      label.dataset.destinationLabel = "";
      row.insertBefore(label, main);
    }

    return { main, chip, label, input: row.querySelector("input[name='locations']") };
  }

  function createHomeRow() {
    const row = document.createElement("span");
    row.className = "home-destination-row";
    row.dataset.destinationRow = "";
    row.innerHTML =
      '<span class="destination-city-label hidden" data-destination-label></span>' +
      '<span class="home-destination-main" data-destination-main>' +
      '<span class="home-field-wrap">' +
      pinIconSvg() +
      '<input name="locations" required placeholder="City or region" class="home-field-input home-field-input--icon" data-location-autocomplete data-location-type="city">' +
      "</span>" +
      '<span class="destination-country-chip hidden" data-destination-country></span>' +
      "</span>" +
      '<input type="hidden" name="location_countries" value="">' +
      '<button type="button" class="home-destination-remove" data-destination-remove aria-label="Remove city">×</button>';
    return row;
  }

  function createEditRow(value) {
    const row = document.createElement("div");
    row.className = "edit-destination-row";
    row.dataset.destinationRow = "";
    row.innerHTML =
      '<span class="destination-city-label hidden" data-destination-label></span>' +
      '<div class="edit-destination-main" data-destination-main>' +
      '<div class="edit-destination-field">' +
      '<input name="locations" required placeholder="City or region" class="border border-gray-200 rounded-xl px-3 py-2.5 w-full" data-location-autocomplete data-location-type="city"' +
      (value ? ' value="' + String(value).replace(/"/g, "&quot;") + '"' : "") +
      ">" +
      "</div>" +
      '<span class="destination-country-chip hidden" data-destination-country></span>' +
      "</div>" +
      '<input type="hidden" name="location_countries" value="">' +
      '<button type="button" class="edit-destination-remove" data-destination-remove aria-label="Remove city">×</button>';
    return row;
  }

  function ensureCountryInput(row) {
    let input = row.querySelector("input[name='location_countries']");
    if (!input) {
      input = document.createElement("input");
      input.type = "hidden";
      input.name = "location_countries";
      row.appendChild(input);
    }
    return input;
  }

  function updateCountryChip(row, country) {
    const chip = row.querySelector("[data-destination-country]");
    const hidden = ensureCountryInput(row);
    const name = (country || "").trim();
    if (chip) {
      chip.textContent = name;
      chip.classList.toggle("hidden", !name);
      chip.dataset.country = name;
    }
    if (hidden) hidden.value = name;
  }

  function refreshCountryForRow(row) {
    const input = row.querySelector("input[name='locations']");
    if (!input) return;
    const selected = (input.dataset.selectedCountry || "").trim();
    const inferred = selected || inferCountry(input.value);
    updateCountryChip(row, inferred);
  }

  function collectCities(editor) {
    const rows = Array.from(editor.querySelectorAll("[data-destination-row]"));
    return rows
      .map((row) => {
        const input = row.querySelector("input[name='locations']");
        const raw = (input?.value || "").trim();
        if (!raw) return null;
        const country =
          (row.querySelector("[data-destination-country]")?.dataset.country || "").trim() ||
          inferCountry(raw);
        return { raw, city: shortCity(raw, country) || raw, country: country || "Other" };
      })
      .filter(Boolean);
  }

  function groupByCountry(cities) {
    const groups = [];
    const sorted = cities.slice().sort((a, b) => {
      const ca = a.country.localeCompare(b.country);
      if (ca) return ca;
      return a.city.localeCompare(b.city);
    });
    for (const item of sorted) {
      const last = groups[groups.length - 1];
      if (last && last.country === item.country) {
        if (!last.cities.includes(item.city)) last.cities.push(item.city);
      } else {
        groups.push({ country: item.country, cities: [item.city] });
      }
    }
    return groups;
  }

  function updatePreview(editor) {
    const preview = editor.querySelector("[data-destinations-preview]");
    if (!preview) return;
    const toggle = editor.querySelector("[data-multi-city-toggle]");
    const cities = collectCities(editor);
    const groups = groupByCountry(cities);
    const show = !!(toggle?.checked && cities.length >= 2);

    preview.classList.toggle("hidden", !show);
    if (!show) {
      preview.innerHTML = "";
      return;
    }

    preview.innerHTML =
      '<div class="destinations-preview-label">Your route</div>' +
      groups
        .map(
          (g) =>
            '<div class="destinations-preview-group">' +
            '<span class="destinations-preview-country">' +
            g.country +
            "</span>" +
            '<span class="destinations-preview-cities">' +
            g.cities.join(", ") +
            "</span>" +
            "</div>"
        )
        .join("");
  }

  function syncEditor(editor) {
    const list = editor.querySelector("[data-destinations-list]");
    const toggle = editor.querySelector("[data-multi-city-toggle]");
    const addBtn = editor.querySelector("[data-destination-add]");
    const labelEl = editor.querySelector("[data-destinations-heading]");
    if (!list || !toggle || !addBtn) return;

    const isHome = isHomeEditor(editor);
    const multi = toggle.checked;
    let rows = Array.from(list.querySelectorAll("[data-destination-row]"));

    rows.forEach((row, index) => {
      ensureRowStructure(row, isHome);
      if (!multi && index > 0) row.remove();
    });

    rows = Array.from(list.querySelectorAll("[data-destination-row]"));
    if (!rows.length) {
      list.appendChild(isHome ? createHomeRow() : createEditRow());
      rows = Array.from(list.querySelectorAll("[data-destination-row]"));
    }

    if (multi && rows.length < 2) {
      list.appendChild(isHome ? createHomeRow() : createEditRow());
      rows = Array.from(list.querySelectorAll("[data-destination-row]"));
    }

    addBtn.classList.toggle("hidden", !multi);
    addBtn.disabled = rows.length >= MAX_DESTINATIONS;
    if (labelEl) {
      labelEl.textContent = multi ? "Cities" : "Destination";
    }

    rows.forEach((row, index) => {
      ensureRowStructure(row, isHome);
      const removeBtn = row.querySelector("[data-destination-remove]");
      const label = row.querySelector("[data-destination-label]");
      const input = row.querySelector("input[name='locations']");
      if (removeBtn) removeBtn.classList.toggle("hidden", !multi || rows.length <= 1);
      if (label) {
        label.textContent = multi ? "City " + (index + 1) : "";
        label.classList.toggle("hidden", !multi);
      }
      if (input) {
        input.placeholder = multi ? "Add a city" : "City or region";
        input.required = true;
      }
      refreshCountryForRow(row);
    });

    updatePreview(editor);
    if (window.gdpInitLocationAutocomplete) window.gdpInitLocationAutocomplete();
  }

  function bindRowEvents(editor, row) {
    const input = row.querySelector("input[name='locations']");
    if (!input || input.dataset.destinationBound) return;
    input.dataset.destinationBound = "1";

    input.addEventListener("input", () => {
      delete input.dataset.selectedCountry;
      refreshCountryForRow(row);
      updatePreview(editor);
    });

    input.addEventListener("gdp:location-selected", (event) => {
      const country = (event.detail && event.detail.country) || "";
      if (country) input.dataset.selectedCountry = country;
      refreshCountryForRow(row);
      updatePreview(editor);
    });

    input.addEventListener("blur", () => {
      refreshCountryForRow(row);
      updatePreview(editor);
    });
  }

  function initEditor(editor) {
    if (editor.dataset.destinationsReady) return;
    editor.dataset.destinationsReady = "1";

    const list = editor.querySelector("[data-destinations-list]");
    const toggle = editor.querySelector("[data-multi-city-toggle]");
    const addBtn = editor.querySelector("[data-destination-add]");
    if (!list || !toggle || !addBtn) return;

    const isHome = isHomeEditor(editor);

    // Upgrade any existing static rows
    list.querySelectorAll("[data-destination-row]").forEach((row) => {
      ensureRowStructure(row, isHome);
      bindRowEvents(editor, row);
      refreshCountryForRow(row);
    });

    toggle.addEventListener("change", () => {
      syncEditor(editor);
      list.querySelectorAll("[data-destination-row]").forEach((row) => bindRowEvents(editor, row));
      if (toggle.checked) {
        const inputs = list.querySelectorAll("input[name='locations']");
        const empty = Array.from(inputs).find((el) => !el.value.trim());
        (empty || inputs[inputs.length - 1])?.focus();
      }
    });

    addBtn.addEventListener("click", () => {
      if (list.querySelectorAll("[data-destination-row]").length >= MAX_DESTINATIONS) return;
      toggle.checked = true;
      const row = isHome ? createHomeRow() : createEditRow();
      list.appendChild(row);
      bindRowEvents(editor, row);
      syncEditor(editor);
      row.querySelector("input[name='locations']")?.focus();
    });

    list.addEventListener("click", (event) => {
      const btn = event.target.closest("[data-destination-remove]");
      if (!btn) return;
      const row = btn.closest("[data-destination-row]");
      if (!row) return;
      const rows = list.querySelectorAll("[data-destination-row]");
      if (rows.length <= 1) return;
      row.remove();
      syncEditor(editor);
    });

    editor.addEventListener("gdp:location-selected", () => updatePreview(editor));

    syncEditor(editor);
    list.querySelectorAll("[data-destination-row]").forEach((row) => bindRowEvents(editor, row));
  }

  function initAll() {
    document.querySelectorAll("[data-destinations-editor]").forEach(initEditor);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initAll);
  } else {
    initAll();
  }
})();
