(function () {
  const DEBOUNCE_MS = 280;
  const MIN_CHARS = 2;

  function ensureHiddenCoordInputs(input) {
    if (input.name !== "location") return { lat: null, lng: null };

    const scope = input.parentElement;
    if (!scope) return { lat: null, lng: null };

    let lat = scope.querySelector('input[data-location-lat]');
    let lng = scope.querySelector('input[data-location-lng]');
    if (!lat) {
      lat = document.createElement("input");
      lat.type = "hidden";
      lat.name = "latitude";
      lat.dataset.locationLat = "1";
      scope.appendChild(lat);
    }
    if (!lng) {
      lng = document.createElement("input");
      lng.type = "hidden";
      lng.name = "longitude";
      lng.dataset.locationLng = "1";
      scope.appendChild(lng);
    }
    return { lat, lng };
  }

  function clearCoords(latInput, lngInput) {
    if (latInput) latInput.value = "";
    if (lngInput) lngInput.value = "";
  }

  function positionList(input, list) {
    const rect = input.getBoundingClientRect();
    list.style.position = "fixed";
    list.style.left = rect.left + "px";
    list.style.top = rect.bottom + 4 + "px";
    list.style.width = rect.width + "px";
    list.style.zIndex = "10050";
  }

  function createDropdown(input) {
    let list = input._locationAutocompleteList;
    if (!list) {
      list = document.createElement("ul");
      list.className = "location-autocomplete-list hidden";
      list.setAttribute("role", "listbox");
      document.body.appendChild(list);
      input._locationAutocompleteList = list;
    }
    return list;
  }

  async function fetchSuggestions(input) {
    const q = input.value.trim();
    if (q.length < MIN_CHARS) return [];

    const params = new URLSearchParams({ q });
    const country = input.dataset.locationCountry;
    const type = input.dataset.locationType;
    const biasLat = input.dataset.locationBiasLat;
    const biasLng = input.dataset.locationBiasLng;
    if (country) params.set("country", country);
    if (type) params.set("type", type);
    if (biasLat) params.set("lat", biasLat);
    if (biasLng) params.set("lon", biasLng);

    const res = await fetch("/api/location-search?" + params.toString());
    if (!res.ok) return [];
    const data = await res.json();
    return data.results || [];
  }

  function initInput(input) {
    if (input.dataset.locationReady) return;
    input.dataset.locationReady = "1";
    input.setAttribute("autocomplete", "off");
    input.setAttribute("role", "combobox");
    input.setAttribute("aria-expanded", "false");
    input.setAttribute("aria-autocomplete", "list");

    const { lat: latInput, lng: lngInput } = ensureHiddenCoordInputs(input);
    const list = createDropdown(input);

    let timer = null;
    let activeIndex = -1;
    let items = [];

    function closeList() {
      list.classList.add("hidden");
      list.innerHTML = "";
      activeIndex = -1;
      items = [];
      input.setAttribute("aria-expanded", "false");
    }

    function selectItem(item) {
      input.value = item.label;
      if (latInput) latInput.value = String(item.latitude);
      if (lngInput) lngInput.value = String(item.longitude);
      closeList();
      input.dispatchEvent(
        new CustomEvent("gdp:location-selected", {
          bubbles: true,
          detail: {
            label: item.label,
            country: item.country || "",
            countrycode: item.countrycode || "",
            name: item.name || "",
            latitude: item.latitude,
            longitude: item.longitude,
          },
        })
      );
    }

    function renderList(results) {
      items = results;
      list.innerHTML = "";
      if (!results.length) {
        closeList();
        return;
      }
      results.forEach((item, idx) => {
        const li = document.createElement("li");
        li.className = "location-autocomplete-item";
        li.setAttribute("role", "option");
        li.textContent = item.label;
        li.addEventListener("mousedown", (e) => {
          e.preventDefault();
          selectItem(item);
        });
        li.addEventListener("mouseenter", () => {
          activeIndex = idx;
          [...list.children].forEach((el, i) => {
            el.classList.toggle("is-active", i === activeIndex);
          });
        });
        list.appendChild(li);
      });
      positionList(input, list);
      list.classList.remove("hidden");
      input.setAttribute("aria-expanded", "true");
      activeIndex = -1;
    }

    function scheduleSearch() {
      clearTimeout(timer);
      clearCoords(latInput, lngInput);
      timer = setTimeout(async () => {
        try {
          const results = await fetchSuggestions(input);
          renderList(results);
        } catch (_) {
          closeList();
        }
      }, DEBOUNCE_MS);
    }

    input.addEventListener("input", scheduleSearch);
    input.addEventListener("focus", () => {
      if (input.value.trim().length >= MIN_CHARS) scheduleSearch();
    });
    input.addEventListener("blur", () => {
      setTimeout(closeList, 150);
    });
    input.addEventListener("keydown", (e) => {
      if (list.classList.contains("hidden") || !items.length) return;
      if (e.key === "ArrowDown") {
        e.preventDefault();
        activeIndex = Math.min(activeIndex + 1, items.length - 1);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        activeIndex = Math.max(activeIndex - 1, 0);
      } else if (e.key === "Enter" && activeIndex >= 0) {
        e.preventDefault();
        selectItem(items[activeIndex]);
        return;
      } else if (e.key === "Escape") {
        closeList();
        return;
      } else {
        return;
      }
      [...list.children].forEach((el, i) => {
        el.classList.toggle("is-active", i === activeIndex);
      });
    });

    window.addEventListener(
      "scroll",
      () => {
        if (!list.classList.contains("hidden")) positionList(input, list);
      },
      true
    );
    window.addEventListener("resize", () => {
      if (!list.classList.contains("hidden")) positionList(input, list);
    });
  }

  function initAll() {
    document.querySelectorAll("[data-location-autocomplete]").forEach(initInput);
  }

  window.gdpInitLocationAutocomplete = initAll;

  document.addEventListener("DOMContentLoaded", () => {
    initAll();
    const observer = new MutationObserver(initAll);
    observer.observe(document.body, { childList: true, subtree: true });
  });
})();
