/**
 * Smart trip workspace tabs and repeatable booking/link rows.
 */
(function () {
  function initTabs() {
    var tabs = document.querySelectorAll("[data-workspace-tab]");
    var panels = document.querySelectorAll("[data-workspace-panel]");
    if (!tabs.length || !panels.length) {
      return;
    }
    var shell = document.querySelector(".workspace-shell");
    var activeTabInput = document.querySelector("[data-active-tab-input]");
    function activateTab(key) {
      var hasMatch = Array.prototype.some.call(tabs, function (item) {
        return item.getAttribute("data-workspace-tab") === key;
      });
      if (!hasMatch) {
        return;
      }
      tabs.forEach(function (item) {
        var active = item.getAttribute("data-workspace-tab") === key;
        item.classList.toggle("is-active", active);
      });
      panels.forEach(function (panel) {
        var active = panel.getAttribute("data-workspace-panel") === key;
        panel.classList.toggle("is-active", active);
        panel.hidden = !active;
      });
      if (shell) {
        shell.setAttribute("data-active-tab", key);
      }
      if (activeTabInput) {
        activeTabInput.value = key;
      }
      if (key === "budget") {
        refreshBudgetExtract();
      }
    }

    tabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        var key = tab.getAttribute("data-workspace-tab");
        activateTab(key);
      });
    });
    if (window.location.hash) {
      activateTab(window.location.hash.slice(1));
    } else {
      activateTab("overview");
    }
  }

  function restorePendingBookingImport() {
    var input = document.querySelector("[name='booking_import_text']");
    if (!input) {
      return;
    }
    var pending = window.localStorage.getItem("pendingBookingImport");
    if (!pending) {
      return;
    }
    input.value = input.value ? input.value + "\n\n" + pending : pending;
    window.localStorage.removeItem("pendingBookingImport");
    if (window.tripWorkspaceAutosave) {
      window.tripWorkspaceAutosave();
    }
  }

  function rowHasAnyValue(row) {
    return Array.prototype.some.call(row.querySelectorAll("input, textarea, select"), function (field) {
      return field.value;
    });
  }

  function fillBookingRow(row, booking) {
    Object.keys(booking).forEach(function (key) {
      var field = row.querySelector("[name='booking_" + key + "']");
      if (field && booking[key]) {
        field.value = booking[key];
      }
    });
  }

  function normaliseBookingDate(value) {
    var text = value.trim();
    var iso = text.match(/\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b/);
    if (iso) {
      return iso[1] + "-" + iso[2].padStart(2, "0") + "-" + iso[3].padStart(2, "0");
    }
    var slash = text.match(/\b(\d{1,2})[/-](\d{1,2})[/-](20\d{2})\b/);
    if (slash) {
      return slash[3] + "-" + slash[2].padStart(2, "0") + "-" + slash[1].padStart(2, "0");
    }
    var month = text.match(/\b(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(20\d{2})\b/i);
    if (!month) {
      return "";
    }
    var months = {
      jan: "01", feb: "02", mar: "03", apr: "04", may: "05", jun: "06",
      jul: "07", aug: "08", sep: "09", oct: "10", nov: "11", dec: "12"
    };
    return month[3] + "-" + months[month[2].slice(0, 3).toLowerCase()] + "-" + month[1].padStart(2, "0");
  }

  function extractBookingFromText(text) {
    var lines = text.split(/\r?\n/).map(function (line) {
      return line.trim();
    }).filter(Boolean);
    var category = "Other";
    if (/\bflight|airline|departure|arrival|boarding|airport\b/i.test(text)) {
      category = "Flight";
    } else if (/\bhotel|resort|accommodation|check-?in|room\b/i.test(text)) {
      category = "Accommodation";
    } else if (/\bcaravan|powered site|site number|holiday park\b/i.test(text)) {
      category = "Caravan stand";
    } else if (/\bmovie|cinema\b/i.test(text)) {
      category = "Movie";
    } else if (/\btheatre|show|ticket|seat\b/i.test(text)) {
      category = "Theatre / show";
    } else if (/\brestaurant|dinner|reservation|table\b/i.test(text)) {
      category = "Restaurant";
    }

    var reference = (text.match(/\b(?:confirmation|reference|reservation|booking|conf)\s*(?:number|no|#|:)?\s*([A-Z0-9-]{4,})\b/i) || [])[1] || "";
    var website = (text.match(/https?:\/\/[^\s)]+/i) || [])[0] || "";
    var phone = (text.match(/(?:\+?\d[\d\s().-]{7,}\d)/) || [])[0] || "";
    var date = normaliseBookingDate(text);
    var timeMatch = text.match(/\b([01]?\d|2[0-3])[:.]([0-5]\d)\b/);
    var addressLine = lines.find(function (line) {
      return /\b(address|street|st\b|road|rd\b|avenue|ave\b|drive|dr\b|lane|ln\b|place|pl\b|boulevard|blvd)\b/i.test(line);
    }) || "";
    var name = lines.find(function (line) {
      return !/^(dear|hello|hi|thank you|booking|confirmation|reservation|address|phone|email|date|time)[:\s]/i.test(line);
    }) || "Imported booking";
    if (category === "Flight") {
      var flightNo = (text.match(/\b([A-Z]{2}\s?\d{2,4})\b/) || [])[1];
      name = flightNo ? "Flight " + flightNo.replace(/\s+/, "") : name;
    }
    return {
      category: category,
      name: name,
      date: date,
      end_date: "",
      time: timeMatch ? timeMatch[1].padStart(2, "0") + ":" + timeMatch[2] : "",
      website: website,
      reference: reference,
      address: addressLine.replace(/^address\s*:\s*/i, ""),
      notes: (phone ? "Phone: " + phone + "\n" : "") + text
    };
  }

  function initBookingImport() {
    var button = document.querySelector("[data-extract-booking]");
    var input = document.querySelector("[name='booking_import_text']");
    var status = document.querySelector("[data-booking-import-status]");
    if (!button || !input) {
      return;
    }
    button.addEventListener("click", function () {
      var text = input.value.trim();
      if (!text) {
        if (status) {
          status.textContent = "Paste the booking email first.";
        }
        return;
      }
      var rows = document.querySelectorAll("#booking-rows .booking-row");
      var target = Array.prototype.find.call(rows, function (row) {
        return !rowHasAnyValue(row);
      });
      var addButton = document.querySelector("[data-add-booking]");
      if (!target && addButton) {
        addButton.click();
        rows = document.querySelectorAll("#booking-rows .booking-row");
        target = rows[rows.length - 1];
      }
      if (!target) {
        return;
      }
      fillBookingRow(target, extractBookingFromText(text));
      if (status) {
        status.textContent = "Booking details added.";
      }
      if (window.tripWorkspaceAutosave) {
        window.tripWorkspaceAutosave();
      }
    });
  }

  function initDocumentImport() {
    var panel = document.querySelector("[data-document-import-url]");
    if (!panel) {
      return;
    }
    var fileInput = panel.querySelector("[data-document-import-file]");
    var noteInput = panel.querySelector("[data-document-import-note]");
    var button = panel.querySelector("[data-document-import-btn]");
    var status = panel.querySelector("[data-document-import-status]");
    if (!fileInput || !button) {
      return;
    }
    button.addEventListener("click", function () {
      var file = fileInput.files[0];
      if (!file) {
        if (status) {
          status.textContent = "Choose a document first.";
        }
        return;
      }
      var form = new FormData();
      form.append("file", file);
      form.append("note", noteInput ? noteInput.value.trim() : "");
      button.disabled = true;
      if (status) {
        status.textContent = "Scanning document and filling tabs...";
      }
      window.fetch(panel.getAttribute("data-document-import-url"), {
        method: "POST",
        body: form
      }).then(function (response) {
        return response.json();
      }).then(function (payload) {
        if (!payload.ok) {
          throw new Error(payload.error || "Import failed");
        }
        window.location.href = payload.redirect + "#documents";
      }).catch(function (error) {
        if (status) {
          status.textContent = error.message || "Could not scan document.";
        }
        button.disabled = false;
      });
    });
  }

  function initPlaceLookup() {
    var panel = document.querySelector("[data-place-lookup-url]");
    if (!panel) {
      return;
    }
    var button = panel.querySelector("[data-place-lookup-btn]");
    var status = panel.querySelector("[data-place-lookup-status]");
    if (!button) {
      return;
    }
    button.addEventListener("click", function () {
      button.disabled = true;
      if (status) {
        status.textContent = "Looking up phone and website...";
      }
      window.fetch(panel.getAttribute("data-place-lookup-url"), {
        method: "POST"
      }).then(function (response) {
        return response.json();
      }).then(function (payload) {
        if (!payload.ok) {
          throw new Error(payload.error || "Lookup failed");
        }
        window.location.href = payload.redirect;
      }).catch(function (error) {
        if (status) {
          status.textContent = error.message || "Could not look this up.";
        }
        button.disabled = false;
      });
    });
  }

  function restorePendingBookingRows() {
    var raw = window.localStorage.getItem("pendingBookingRows");
    if (!raw) {
      return;
    }
    var bookings;
    try {
      bookings = JSON.parse(raw);
    } catch (error) {
      window.localStorage.removeItem("pendingBookingRows");
      return;
    }
    if (!Array.isArray(bookings) || !bookings.length) {
      window.localStorage.removeItem("pendingBookingRows");
      return;
    }
    var addButton = document.querySelector("[data-add-booking]");
    bookings.forEach(function (booking) {
      var rows = document.querySelectorAll("#booking-rows .booking-row");
      var target = Array.prototype.find.call(rows, function (row) {
        return !rowHasAnyValue(row);
      });
      if (!target && addButton) {
        addButton.click();
        rows = document.querySelectorAll("#booking-rows .booking-row");
        target = rows[rows.length - 1];
      }
      if (target) {
        fillBookingRow(target, booking);
      }
    });
    window.localStorage.removeItem("pendingBookingRows");
    if (window.tripWorkspaceAutosave) {
      window.tripWorkspaceAutosave();
    }
  }

  function restorePendingRows(storageKey, rowSelector, fieldPrefix, addButtonSelector) {
    var raw = window.localStorage.getItem(storageKey);
    if (!raw) {
      return;
    }
    var items;
    try {
      items = JSON.parse(raw);
    } catch (error) {
      window.localStorage.removeItem(storageKey);
      return;
    }
    var addButton = addButtonSelector ? document.querySelector(addButtonSelector) : null;
    items.forEach(function (item) {
      var rows = document.querySelectorAll(rowSelector);
      var target = Array.prototype.find.call(rows, function (row) {
        return !rowHasAnyValue(row);
      });
      if (!target && addButton) {
        addButton.click();
        rows = document.querySelectorAll(rowSelector);
        target = rows[rows.length - 1];
      }
      if (!target) {
        return;
      }
      Object.keys(item).forEach(function (key) {
        var field = target.querySelector("[name='" + fieldPrefix + "_" + key + "']");
        if (field && item[key]) {
          field.value = item[key];
        }
      });
    });
    window.localStorage.removeItem(storageKey);
    if (window.tripWorkspaceAutosave) {
      window.tripWorkspaceAutosave();
    }
  }

  function initTripOverviewFilters() {
    var typeFilter = document.querySelector("[data-trip-filter-type]");
    var dateFilter = document.querySelector("[data-trip-filter-date]");
    var rows = document.querySelectorAll(".compact-trip-row");
    if (!typeFilter || !dateFilter || !rows.length) {
      return;
    }
    function categoryMatch(type, category, isKey) {
      if (type === "all") {
        return true;
      }
      if (type === "key") {
        return isKey;
      }
      var value = (category || "").toLowerCase();
      if (type === "Flight") {
        return value === "flight" || value === "flights";
      }
      if (type === "Accommodation") {
        return value === "accommodation" || value === "stay" || value === "caravan stand";
      }
      if (type === "Activity") {
        return value === "activity";
      }
      return value === type.toLowerCase();
    }
    function applyFilters() {
      var type = typeFilter.value;
      var date = dateFilter.value;
      rows.forEach(function (row) {
        var category = row.getAttribute("data-row-category");
        var rowDate = row.getAttribute("data-row-date");
        var isKey = row.getAttribute("data-row-key") === "1";
        var typeMatch = categoryMatch(type, category, isKey);
        var dateMatch = !date || rowDate === date;
        row.hidden = !(typeMatch && dateMatch);
      });
      document.querySelectorAll("[data-trip-day]").forEach(function (day) {
        var visibleRows = Array.prototype.some.call(
          day.querySelectorAll(".compact-trip-row"),
          function (row) {
            return !row.hidden;
          }
        );
        day.hidden = !visibleRows;
      });
    }
    typeFilter.addEventListener("change", applyFilters);
    dateFilter.addEventListener("change", applyFilters);
    applyFilters();
  }

  function initDetailsPopovers() {
    document.querySelectorAll(".compact-trip-more").forEach(function (details) {
      var close = details.querySelector("[data-close-details]");
      if (close) {
        close.addEventListener("click", function (event) {
          event.preventDefault();
          details.open = false;
        });
      }
    });
  }

  function initBackButton() {
    var button = document.querySelector("[data-back-button]");
    if (!button) {
      return;
    }
    button.addEventListener("click", function () {
      if (window.history.length > 1) {
        window.history.back();
      } else {
        var home = document.querySelector("a.logo");
        window.location.href = home ? home.getAttribute("href") : "/";
      }
    });
  }

  function initTaskCheckboxes() {
    var form = document.querySelector("[data-task-autosave-url]");
    var autosaveUrl = form ? form.getAttribute("data-task-autosave-url") : "";
    var saveStatus = document.querySelector("[data-task-save-status]");
    var taskList = document.querySelector(".task-compact-list");
    function showSaveStatus(message) {
      if (saveStatus) {
        saveStatus.textContent = message;
      }
    }

    function saveTaskStatus(row, checkbox, taskText) {
      var text = taskText ? taskText.value.trim() : "";
      var status = row ? row.querySelector("[data-task-status-hidden]") : null;
      if (!autosaveUrl || !text) {
        return Promise.resolve(null);
      }
      if (status) {
        status.value = checkbox && checkbox.checked ? "Done" : "To do";
      }
      if (checkbox) {
        checkbox.disabled = true;
      }
      showSaveStatus("Saving...");
      return window.fetch(autosaveUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Accept": "application/json"
        },
        body: JSON.stringify({
          index: row ? row.getAttribute("data-task-row") : "",
          text: text,
          done: checkbox ? checkbox.checked : false
        })
      }).then(function (response) {
        if (!response.ok) {
          throw new Error("Task autosave failed");
        }
        return response.json();
      }).then(function (data) {
        if (row && data.index !== undefined && data.index !== null) {
          row.setAttribute("data-task-row", data.index);
        }
        showSaveStatus("Saved");
        return data;
      }).finally(function () {
        if (checkbox) {
          checkbox.disabled = false;
        }
      });
    }

    function bindTaskCheckbox(checkbox) {
      var row = checkbox.closest(".task-compact-row");
      var status = row ? row.querySelector("[data-task-status-hidden]") : null;
      var taskText = row ? row.querySelector("[name='task_text']") : null;
      function syncStatus() {
        if (status) {
          status.value = checkbox.checked ? "Done" : "To do";
        }
      }
      function autosaveStatus() {
        syncStatus();
        saveTaskStatus(row, checkbox, taskText).catch(function () {
          checkbox.checked = !checkbox.checked;
          syncStatus();
          showSaveStatus("Could not save tick. Try again.");
        });
      }
      checkbox.addEventListener("change", autosaveStatus);
      syncStatus();
    }

    function addTaskRow(text, index) {
      if (!taskList) {
        return;
      }
      var existing = Array.prototype.some.call(
        taskList.querySelectorAll("[name='task_text']"),
        function (field) {
          return field.value.trim().toLowerCase() === text.toLowerCase();
        }
      );
      if (existing) {
        return;
      }
      var row = document.createElement("div");
      row.className = "task-compact-row";
      row.setAttribute("data-task-row", index);
      row.innerHTML = [
        '<input type="hidden" name="task_owner" value="">',
        '<input type="hidden" name="task_due" value="">',
        '<input type="hidden" name="task_status" value="To do" data-task-status-hidden>',
        '<input type="checkbox" data-task-done aria-label="Task done">',
        '<input type="hidden" name="task_text">',
        '<span class="task-compact-label"></span>'
      ].join("");
      row.querySelector("[name='task_text']").value = text;
      row.querySelector(".task-compact-label").textContent = text;
      var quickAdd = taskList.querySelector(".task-quick-add");
      taskList.insertBefore(row, quickAdd || null);
      bindTaskCheckbox(row.querySelector("[data-task-done]"));
    }

    function moveSuggestionToTasks(checkbox) {
      var label = checkbox.closest(".check");
      var text = checkbox.value.trim();
      if (!checkbox.checked || !text || checkbox.getAttribute("data-saving") === "1") {
        return;
      }
      checkbox.setAttribute("data-saving", "1");
      checkbox.disabled = true;
      saveTaskStatus(null, null, { value: text }).then(function (data) {
        if (data && data.ok) {
          addTaskRow(text, data.index);
          if (label) {
            label.remove();
          }
        }
      }).catch(function () {
        checkbox.checked = false;
        checkbox.disabled = false;
        checkbox.removeAttribute("data-saving");
        showSaveStatus("Could not add item. Try again.");
      });
    }

    document.querySelectorAll("[data-task-done]").forEach(function (checkbox) {
      if (checkbox.hasAttribute("data-inline-autosave")) {
        return;
      }
      bindTaskCheckbox(checkbox);
    });

    document.querySelectorAll("[data-task-suggestion]").forEach(function (checkbox) {
      if (checkbox.hasAttribute("data-inline-autosave")) {
        return;
      }
      checkbox.addEventListener("change", function () {
        moveSuggestionToTasks(checkbox);
      });
      if (checkbox.checked) {
        moveSuggestionToTasks(checkbox);
      }
    });
  }

  function initWorkspaceAutosave() {
    var form = document.querySelector(".workspace-shell");
    var status = document.querySelector("[data-workspace-save-status]");
    if (!form) {
      return;
    }
    var timer = null;
    var request = null;
    function saveNow() {
      if (request) {
        request.abort();
      }
      request = new AbortController();
      if (status) {
        status.textContent = "Saving...";
      }
      var data = new FormData(form);
      data.set("autosave", "1");
      window.fetch(form.action, {
        method: "POST",
        body: data,
        signal: request.signal
      }).then(function (response) {
        return response.json();
      }).then(function (payload) {
        if (!payload.ok) {
          throw new Error("Save failed");
        }
        if (status) {
          status.textContent = "Saved";
        }
      }).catch(function (error) {
        if (error && error.name === "AbortError") {
          return;
        }
        if (status) {
          status.textContent = "Could not save. Use Save now.";
        }
      });
    }
    function schedule() {
      window.clearTimeout(timer);
      timer = window.setTimeout(saveNow, 700);
    }
    function onEdit(event) {
      if (event.target && event.target.closest("[data-inline-autosave], [data-no-autosave]")) {
        return;
      }
      schedule();
    }
    form.addEventListener("input", onEdit);
    form.addEventListener("change", onEdit);
    window.tripWorkspaceAutosave = schedule;
  }

  function addTemplate(buttonSelector, targetSelector, templateSelector) {
    var button = document.querySelector(buttonSelector);
    var target = document.querySelector(targetSelector);
    var template = document.querySelector(templateSelector);
    if (!button || !target || !template) {
      return;
    }
    button.addEventListener("click", function () {
      target.appendChild(template.content.cloneNode(true));
    });
  }

  function refreshBudgetExtract() {
    var inputs = document.querySelectorAll(".booking-row [name='booking_cost']");
    var lines = document.querySelectorAll("[data-budget-line]");
    var total = 0;
    inputs.forEach(function (input, index) {
      var amount = parseFloat(input.value);
      if (!isNaN(amount)) {
        total += amount;
      }
      var line = lines[index];
      var slot = line ? line.querySelector("[data-budget-amount]") : null;
      if (slot) {
        slot.textContent = input.value ? "$" + Number(input.value).toFixed(2) : "No cost yet";
      }
    });
    var totalNode = document.querySelector("[data-budget-total]");
    if (totalNode) {
      totalNode.textContent = "Total: $" + total.toFixed(2);
    }
  }

  function run() {
    initTabs();
    initWorkspaceAutosave();
    restorePendingBookingImport();
    addTemplate("[data-add-booking]", "#booking-rows", "#booking-row-template");
    addTemplate("[data-add-link]", "#link-rows", "#link-row-template");
    initBookingImport();
    initDocumentImport();
    initPlaceLookup();
    restorePendingBookingRows();
    restorePendingRows("pendingLinkRows", ".link-row", "link", "[data-add-link]");
    restorePendingRows("pendingDocumentRows", ".document-row", "document", "");
    initTripOverviewFilters();
    initDetailsPopovers();
    initBackButton();
    initTaskCheckboxes();
    document.addEventListener("input", function (event) {
      if (event.target && event.target.name === "booking_cost") {
        refreshBudgetExtract();
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", run);
  } else {
    run();
  }
})();
