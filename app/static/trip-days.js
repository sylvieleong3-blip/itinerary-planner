(function () {
  const sortable = document.querySelector("[data-days-sortable]");
  if (!sortable) return;

  const tripCode = sortable.dataset.tripCode;
  if (!tripCode) return;

  const isGrouped = sortable.dataset.multiGrouped === "1";

  let dragDay = null;
  let dragItem = null;
  let orderAtStart = null;

  function formatDayDate(startDate, position) {
    if (!startDate) return "Day " + position;
    const start = new Date(startDate + "T12:00:00");
    if (Number.isNaN(start.getTime())) return "Day " + position;
    const day = new Date(start);
    day.setDate(day.getDate() + position - 1);
    const weekday = day.toLocaleDateString("en-US", { weekday: "short" });
    const month = day.toLocaleDateString("en-US", { month: "short" });
    return weekday + ", " + month + " " + day.getDate();
  }

  function allManageItems() {
    return [...sortable.querySelectorAll(".trip-day-manage-item")];
  }

  function refreshSidebarLabels() {
    const startDate = sortable.dataset.tripStart || "";
    allManageItems().forEach((item, index) => {
      const position = index + 1;
      const labelEl = item.querySelector(".trip-day-label");
      const numEl = item.querySelector(".trip-day-num");
      const dateEl = item.querySelector(".trip-day-sub");
      if (labelEl) labelEl.textContent = "Day " + position;
      if (numEl) numEl.textContent = String(position);
      if (dateEl) dateEl.textContent = formatDayDate(startDate, position);
    });
  }

  function currentOrder() {
    return allManageItems().map((el) => parseInt(el.dataset.dayManage, 10));
  }

  function restoreOrder(order) {
    if (!order?.length) return;
    const items = allManageItems();
    const byDay = new Map(items.map((el) => [String(el.dataset.dayManage), el]));
    if (isGrouped) {
      sortable.innerHTML = "";
      order.forEach((day) => {
        const el = byDay.get(String(day));
        if (el) sortable.appendChild(el);
      });
      rebuildGroups();
    } else {
      order.forEach((day) => {
        const el = byDay.get(String(day));
        if (el) sortable.appendChild(el);
      });
    }
    refreshSidebarLabels();
  }

  function rebuildGroups() {
    if (!isGrouped) return;
    const items = allManageItems();
    const grouped = [];

    for (const item of items) {
      const code = item.dataset.dayCountryCode || "";
      const country = item.dataset.dayCountry || "Other";
      const city = item.dataset.dayCity || "Other";
      let countryGroup = grouped[grouped.length - 1];
      if (!countryGroup || countryGroup.code !== code) {
        countryGroup = { code, name: country, cities: [] };
        grouped.push(countryGroup);
      }
      let cityGroup = countryGroup.cities[countryGroup.cities.length - 1];
      if (!cityGroup || cityGroup.name !== city) {
        cityGroup = { name: city, items: [] };
        countryGroup.cities.push(cityGroup);
      }
      cityGroup.items.push(item);
    }

    sortable.innerHTML = "";
    for (const country of grouped) {
      const dayCount = country.cities.reduce((total, city) => total + city.items.length, 0);
      const countryDetails = document.createElement("details");
      countryDetails.className = "trip-days-country-group";
      countryDetails.open = true;
      countryDetails.innerHTML =
        '<summary class="trip-days-group-summary">' +
        '<span class="trip-days-group-chevron" aria-hidden="true"></span>' +
        '<span class="trip-days-group-heading">' +
        '<span class="trip-days-country-name"></span>' +
        '<span class="trip-days-group-meta"></span>' +
        "</span>" +
        (country.code
          ? '<button type="button" class="trip-days-group-delete" data-delete-country="' +
            country.code +
            '" data-country-name="' +
            country.name +
            '" aria-label="Remove ' +
            country.name +
            '">×</button>'
          : "") +
        "</summary>" +
        '<div class="trip-days-country-body"></div>';
      countryDetails.querySelector(".trip-days-country-name").textContent = country.name;
      countryDetails.querySelector(".trip-days-group-meta").textContent =
        dayCount + " day" + (dayCount === 1 ? "" : "s");
      const countryBody = countryDetails.querySelector(".trip-days-country-body");

      for (const city of country.cities) {
        const cityDetails = document.createElement("details");
        cityDetails.className = "trip-days-city-group";
        cityDetails.open = true;
        cityDetails.innerHTML =
          '<summary class="trip-days-group-summary trip-days-group-summary--city">' +
          '<span class="trip-days-group-chevron" aria-hidden="true"></span>' +
          '<span class="trip-days-group-heading">' +
          '<span class="trip-days-city-name"></span>' +
          '<span class="trip-days-group-meta"></span>' +
          "</span>" +
          (country.code
            ? '<button type="button" class="trip-days-group-delete" data-delete-city="' +
              city.name +
              '" data-country-code="' +
              country.code +
              '" aria-label="Remove ' +
              city.name +
              '">×</button>'
            : "") +
          "</summary>" +
          '<div class="trip-days-city-body"></div>';
        cityDetails.querySelector(".trip-days-city-name").textContent = city.name;
        const cityDays = city.items.length;
        cityDetails.querySelector(".trip-days-group-meta").textContent =
          cityDays + " day" + (cityDays === 1 ? "" : "s");
        const cityBody = cityDetails.querySelector(".trip-days-city-body");
        for (const item of city.items) {
          cityBody.appendChild(item);
        }
        countryBody.appendChild(cityDetails);
      }
      sortable.appendChild(countryDetails);
    }
  }

  function dragAfterElement(y) {
    const items = allManageItems().filter((el) => !el.classList.contains("dragging"));
    return items.reduce(
      (closest, child) => {
        const box = child.getBoundingClientRect();
        const offset = y - box.top - box.height / 2;
        if (offset < 0 && offset > closest.offset) {
          return { offset, element: child };
        }
        return closest;
      },
      { offset: Number.NEGATIVE_INFINITY, element: null }
    ).element;
  }

  function insertDragged(dragged, after) {
    if (after) {
      after.parentElement.insertBefore(dragged, after);
      return;
    }
    const others = allManageItems().filter((el) => el !== dragged);
    const last = others[others.length - 1];
    if (last) last.parentElement.appendChild(dragged);
    else if (isGrouped) {
      const body = sortable.querySelector(".trip-days-city-body");
      if (body) body.appendChild(dragged);
    } else {
      sortable.appendChild(dragged);
    }
  }

  async function persistOrder() {
    const order = currentOrder();
    try {
      const res = await fetch(`/t/${tripCode}/days/reorder`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ order }),
      });
      if (res.ok) {
        location.reload();
        return;
      }
      const data = await res.json().catch(() => ({}));
      restoreOrder(orderAtStart);
      alert(data.error || "Could not reorder days.");
    } catch (_) {
      restoreOrder(orderAtStart);
      alert("Could not reorder days.");
    }
  }

  allManageItems().forEach((item) => {
    const handle = item.querySelector(".trip-day-drag-handle");
    if (handle) handle.draggable = true;
  });

  sortable.addEventListener("dragstart", (event) => {
    const handle = event.target.closest(".trip-day-drag-handle");
    if (!handle) return;
    const item = handle.closest(".trip-day-manage-item");
    if (!item) return;
    dragItem = item;
    dragDay = item.dataset.dayManage;
    orderAtStart = currentOrder();
    item.classList.add("dragging");
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", dragDay || "");
    event.stopPropagation();
  });

  sortable.addEventListener("dragend", () => {
    if (dragItem) dragItem.classList.remove("dragging");
    sortable.querySelectorAll(".trip-day-drop-target").forEach((el) => {
      el.classList.remove("trip-day-drop-target");
    });
    if (isGrouped) rebuildGroups();
    refreshSidebarLabels();
    const order = currentOrder();
    if (orderAtStart && JSON.stringify(order) !== JSON.stringify(orderAtStart)) {
      persistOrder();
    }
    dragDay = null;
    dragItem = null;
    orderAtStart = null;
  });

  sortable.addEventListener("dragover", (event) => {
    event.preventDefault();
    if (!dragDay || !dragItem) return;

    const after = dragAfterElement(event.clientY);
    sortable.querySelectorAll(".trip-day-drop-target").forEach((el) => {
      el.classList.remove("trip-day-drop-target");
    });
    if (after) {
      after.classList.add("trip-day-drop-target");
      insertDragged(dragItem, after);
    } else {
      insertDragged(dragItem, null);
    }
    refreshSidebarLabels();
  });

  sortable.addEventListener("dragleave", (event) => {
    if (!sortable.contains(event.relatedTarget)) {
      sortable.querySelectorAll(".trip-day-drop-target").forEach((el) => {
        el.classList.remove("trip-day-drop-target");
      });
    }
  });

  sortable.addEventListener("drop", (event) => {
    event.preventDefault();
    sortable.querySelectorAll(".trip-day-drop-target").forEach((el) => {
      el.classList.remove("trip-day-drop-target");
    });
  });

  sortable.querySelectorAll("[data-delete-day]").forEach((btn) => {
    btn.addEventListener("click", async (event) => {
      event.stopPropagation();
      const item = btn.closest(".trip-day-manage-item");
      const day = btn.dataset.deleteDay;
      const count = parseInt(item?.dataset.dayActivities || "0", 10);
      const message =
        count > 0
          ? `Remove Day ${day}? ${count} activit${count === 1 ? "y" : "ies"} on this day will be deleted.`
          : `Remove Day ${day}?`;
      const ok = await showConfirm(message);
      if (!ok) return;
      try {
        const res = await fetch(`/t/${tripCode}/days/${day}/delete`, {
          method: "POST",
          credentials: "same-origin",
        });
        if (res.ok) {
          location.reload();
          return;
        }
        const data = await res.json().catch(() => ({}));
        alert(data.error || "Could not delete day.");
      } catch (_) {
        alert("Could not delete day.");
      }
    });
  });

  sortable.addEventListener("click", async (event) => {
    const countryBtn = event.target.closest("[data-delete-country]");
    if (countryBtn) {
      event.stopPropagation();
      event.preventDefault();
      const code = countryBtn.dataset.deleteCountry;
      const name = countryBtn.dataset.countryName || "this country";
      const ok = await showConfirm(
        `Remove ${name} and all its days from the trip? Activities on those days will be deleted.`
      );
      if (!ok) return;
      try {
        const res = await fetch(`/t/${tripCode}/countries/${encodeURIComponent(code)}/delete`, {
          method: "POST",
          credentials: "same-origin",
        });
        if (res.ok) {
          location.reload();
          return;
        }
        const data = await res.json().catch(() => ({}));
        alert(data.error || "Could not remove country.");
      } catch (_) {
        alert("Could not remove country.");
      }
      return;
    }

    const cityBtn = event.target.closest("[data-delete-city]");
    if (!cityBtn) return;
    event.stopPropagation();
    event.preventDefault();
    const city = cityBtn.dataset.deleteCity;
    const countryCode = cityBtn.dataset.countryCode;
    const ok = await showConfirm(
      `Remove ${city} and all its days from the trip? Activities on those days will be deleted.`
    );
    if (!ok) return;
    try {
      const res = await fetch(`/t/${tripCode}/cities/delete`, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ country_code: countryCode, city }),
      });
      if (res.ok) {
        location.reload();
        return;
      }
      const data = await res.json().catch(() => ({}));
      alert(data.error || "Could not remove city.");
    } catch (_) {
      alert("Could not remove city.");
    }
  });
})();
