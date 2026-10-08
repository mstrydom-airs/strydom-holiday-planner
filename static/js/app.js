/**
 * Sync "to" date inputs with "from" dates: min and default value.
 * Uses event delegation so dynamically added legs work without rebinding.
 * Also navigates when the holiday type dropdown changes.
 */
(function () {
  function syncDateRangePair(pair) {
    if (!pair) {
      return;
    }
    var from = pair.querySelector(".date-from");
    var to = pair.querySelector(".date-to");
    if (!from || !to) {
      return;
    }
    if (!from.value) {
      to.removeAttribute("min");
      return;
    }
    to.min = from.value;
    if (!to.value || to.value < from.value) {
      to.value = from.value;
    }
  }

  /** Used by extended-legs.js after adding a new leg row. */
  window.syncDateRangePair = syncDateRangePair;

  function initDatePairs() {
    document.querySelectorAll(".date-range-pair").forEach(syncDateRangePair);
    if (window._datePairDelegationBound) {
      return;
    }
    window._datePairDelegationBound = true;
    document.body.addEventListener("change", function (e) {
      var t = e.target;
      if (t.classList && t.classList.contains("date-from")) {
        var pair = t.closest(".date-range-pair");
        if (pair) {
          syncDateRangePair(pair);
        }
      }
    });
    document.body.addEventListener("input", function (e) {
      var t = e.target;
      if (t.classList && t.classList.contains("date-from")) {
        var pair = t.closest(".date-range-pair");
        if (pair) {
          syncDateRangePair(pair);
        }
      }
    });
  }

  function initTripTypeSelect() {
    document.querySelectorAll(".trip-type-select").forEach(function (sel) {
      sel.addEventListener("change", function () {
        var v = sel.value;
        if (v) {
          window.location.href = v;
        }
      });
    });
  }

  function initThingsToDoTabs() {
    document.querySelectorAll(".things-to-do-tabs").forEach(function (root) {
      var tabs = root.querySelectorAll('[role="tab"]');
      var panels = root.querySelectorAll('[role="tabpanel"]');
      if (!tabs.length || !panels.length || tabs.length !== panels.length) {
        return;
      }
      function select(i) {
        tabs.forEach(function (t, j) {
          var on = j === i;
          t.setAttribute("aria-selected", on ? "true" : "false");
          t.classList.toggle("is-active", on);
        });
        panels.forEach(function (p, j) {
          p.hidden = j !== i;
        });
      }
      tabs.forEach(function (tab, i) {
        tab.addEventListener("click", function () {
          select(i);
        });
      });
    });
  }

  function initStaySizeToggle() {
    var stayTypes = ["Accor Unit", "Hotel", "Beachhouse", "Beachcomber", "Noosa Spa"];
    document.querySelectorAll('select[name="plan_category"]').forEach(function (categorySelect) {
      var form = categorySelect.closest("form") || document;
      var field = form.querySelector("[data-stay-size-field]");
      if (!field) {
        return;
      }
      var sizeSelect = field.querySelector('select[name="stay_unit_size"]');
      function update() {
        var shouldShow = stayTypes.indexOf(categorySelect.value) !== -1;
        field.hidden = !shouldShow;
        if (sizeSelect) {
          sizeSelect.disabled = !shouldShow;
          if (!shouldShow) {
            sizeSelect.value = "";
          }
        }
      }
      categorySelect.addEventListener("change", update);
      update();
    });
  }

  function initDateRangePickers() {
    document.querySelectorAll("[data-date-range-picker]").forEach(function (root) {
      var trigger = root.querySelector("[data-range-trigger]");
      var popover = root.querySelector("[data-range-popover]");
      var grid = root.querySelector("[data-range-grid]");
      var monthLabel = root.querySelector("[data-range-month]");
      var startInput = root.querySelector("[data-range-start]");
      var endInput = root.querySelector("[data-range-end]");
      var label = root.querySelector("[data-range-label]");
      var prev = root.querySelector("[data-range-prev]");
      var next = root.querySelector("[data-range-next]");
      if (!trigger || !popover || !grid || !monthLabel || !startInput || !endInput || !label || !prev || !next) {
        return;
      }

      var today = new Date();
      var start = isoToDate(startInput.value) || stripTime(today);
      var end = isoToDate(endInput.value) || stripTime(today);
      var visible = new Date(start.getFullYear(), start.getMonth(), 1);
      var selectingEnd = false;

      function stripTime(date) {
        return new Date(date.getFullYear(), date.getMonth(), date.getDate());
      }

      function toIso(date) {
        var y = date.getFullYear();
        var m = String(date.getMonth() + 1).padStart(2, "0");
        var d = String(date.getDate()).padStart(2, "0");
        return y + "-" + m + "-" + d;
      }

      function isoToDate(value) {
        if (!value) {
          return null;
        }
        var parts = value.split("-").map(Number);
        if (parts.length !== 3 || parts.some(isNaN)) {
          return null;
        }
        return new Date(parts[0], parts[1] - 1, parts[2]);
      }

      function labelDate(date) {
        return date.toLocaleDateString(undefined, {
          day: "2-digit",
          month: "short",
          year: "numeric"
        });
      }

      function syncInputs() {
        startInput.value = toIso(start);
        endInput.value = toIso(end);
        label.textContent = labelDate(start) + " to " + labelDate(end);
      }

      function sameDay(a, b) {
        return toIso(a) === toIso(b);
      }

      function inRange(date) {
        return date >= start && date <= end;
      }

      function render() {
        monthLabel.textContent = visible.toLocaleDateString(undefined, {
          month: "long",
          year: "numeric"
        });
        grid.innerHTML = "";
        var first = new Date(visible.getFullYear(), visible.getMonth(), 1);
        var startOffset = (first.getDay() + 6) % 7;
        var cursor = new Date(first);
        cursor.setDate(first.getDate() - startOffset);
        for (var i = 0; i < 42; i += 1) {
          var day = new Date(cursor);
          var button = document.createElement("button");
          button.type = "button";
          button.className = "date-range-day";
          button.textContent = String(day.getDate());
          if (day.getMonth() !== visible.getMonth()) {
            button.classList.add("is-muted");
          }
          if (inRange(day)) {
            button.classList.add("is-in-range");
          }
          if (sameDay(day, start) || sameDay(day, end)) {
            button.classList.add("is-selected");
          }
          button.addEventListener("click", function (selectedDay) {
            return function () {
              if (!selectingEnd || (start && end && !sameDay(start, end))) {
                start = selectedDay;
                end = selectedDay;
                selectingEnd = true;
              } else if (selectedDay < start) {
                end = start;
                start = selectedDay;
                selectingEnd = false;
                popover.hidden = true;
              } else {
                end = selectedDay;
                selectingEnd = false;
                popover.hidden = true;
              }
              trigger.setAttribute("aria-expanded", popover.hidden ? "false" : "true");
              syncInputs();
              render();
            };
          }(day));
          grid.appendChild(button);
          cursor.setDate(cursor.getDate() + 1);
        }
      }

      trigger.addEventListener("click", function () {
        popover.hidden = !popover.hidden;
        trigger.setAttribute("aria-expanded", popover.hidden ? "false" : "true");
        if (!popover.hidden) {
          render();
        }
      });
      prev.addEventListener("click", function () {
        visible.setMonth(visible.getMonth() - 1);
        render();
      });
      next.addEventListener("click", function () {
        visible.setMonth(visible.getMonth() + 1);
        render();
      });
      document.addEventListener("click", function (event) {
        if (!root.contains(event.target)) {
          popover.hidden = true;
          trigger.setAttribute("aria-expanded", "false");
        }
      });
      syncInputs();
      render();
    });
  }

  function splitChecklistHeader(text) {
    var lines = String(text || "").split("\n");
    var marker = "--- Trip selections (auto) ---";
    if (!lines.length || lines[0].trim() !== marker) {
      return { header: "", body: String(text || "") };
    }
    var bodyStart = 1;
    while (bodyStart < lines.length && lines[bodyStart].trim()) {
      bodyStart += 1;
    }
    if (bodyStart < lines.length) {
      bodyStart += 1;
    }
    return {
      header: lines.slice(0, bodyStart).join("\n").trimEnd(),
      body: lines.slice(bodyStart).join("\n")
    };
  }

  function cleanChecklistItem(line) {
    return String(line || "").trim().replace(/^(\d+[\.)]|[-*])\s*/, "").trim();
  }

  function numberChecklistBody(body) {
    var items = [];
    String(body || "").split("\n").forEach(function (line) {
      var item = cleanChecklistItem(line);
      if (item) {
        items.push(item);
      }
    });
    return items.map(function (item, index) {
      return (index + 1) + ". " + item;
    }).join("\n");
  }

  function normalizeChecklistTextarea(textarea) {
    var parts = splitChecklistHeader(textarea.value);
    var numbered = numberChecklistBody(parts.body);
    if (parts.header && numbered) {
      textarea.value = parts.header + "\n\n" + numbered;
      return;
    }
    textarea.value = parts.header || numbered;
  }

  function nextChecklistNumberBeforeCursor(textarea) {
    var before = textarea.value.slice(0, textarea.selectionStart);
    var parts = splitChecklistHeader(before);
    var count = 0;
    String(parts.body || "").split("\n").forEach(function (line) {
      if (cleanChecklistItem(line)) {
        count += 1;
      }
    });
    return count + 1;
  }

  function insertAtCursor(textarea, text) {
    var start = textarea.selectionStart;
    var end = textarea.selectionEnd;
    textarea.value = textarea.value.slice(0, start) + text + textarea.value.slice(end);
    textarea.selectionStart = start + text.length;
    textarea.selectionEnd = textarea.selectionStart;
  }

  function initChecklistNumbering() {
    function isNumberedTextarea(textarea) {
      return textarea && (textarea.name === "checklist_content" || textarea.name === "transport_extra");
    }

    document.body.addEventListener("keydown", function (e) {
      var textarea = e.target;
      if (!isNumberedTextarea(textarea) || e.key !== "Enter" || e.shiftKey) {
        return;
      }
      var lineStart = textarea.value.lastIndexOf("\n", textarea.selectionStart - 1) + 1;
      var currentLine = textarea.value.slice(lineStart, textarea.selectionStart);
      if (!cleanChecklistItem(currentLine)) {
        return;
      }
      e.preventDefault();
      insertAtCursor(textarea, "\n" + nextChecklistNumberBeforeCursor(textarea) + ". ");
    });

    document.body.addEventListener("blur", function (e) {
      var textarea = e.target;
      if (isNumberedTextarea(textarea)) {
        normalizeChecklistTextarea(textarea);
      }
    }, true);
  }

  function initHouseholdTabs() {
    var root = document.querySelector("[data-household-tabs]");
    if (!root) {
      return;
    }
    var buttons = root.querySelectorAll("[data-household-tab]");
    var panels = root.querySelectorAll("[data-household-panel]");
    buttons.forEach(function (button) {
      button.addEventListener("click", function () {
        var name = button.getAttribute("data-household-tab");
        buttons.forEach(function (item) {
          var on = item === button;
          item.classList.toggle("is-active", on);
          item.setAttribute("aria-selected", on ? "true" : "false");
        });
        panels.forEach(function (panel) {
          panel.hidden = panel.getAttribute("data-household-panel") !== name;
        });
      });
    });
  }

  function run() {
    initDatePairs();
    initTripTypeSelect();
    initThingsToDoTabs();
    initStaySizeToggle();
    initDateRangePickers();
    initChecklistNumbering();
    initHouseholdTabs();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", run);
  } else {
    run();
  }
})();
