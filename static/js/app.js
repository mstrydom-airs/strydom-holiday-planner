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

  function run() {
    initDatePairs();
    initTripTypeSelect();
    initThingsToDoTabs();
    initChecklistNumbering();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", run);
  } else {
    run();
  }
})();
