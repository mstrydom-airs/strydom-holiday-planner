/**
 * Extended trip: one leg to start, "Add leg" for more.
 * First leg start follows overall trip start; each next leg's start defaults to the previous leg's end.
 */
(function () {
  var container = document.getElementById("legs-container");
  var tripStart = document.querySelector("#extended-form [name=trip_start]");
  var tpl = document.getElementById("leg-block-template");
  var addBtn = document.getElementById("add-leg");

  if (!container || !tpl || !addBtn) {
    return;
  }

  function getLegBlocks() {
    return container.querySelectorAll(".leg-block");
  }

  function renumberLegs() {
    getLegBlocks().forEach(function (block, i) {
      var n = block.querySelector(".leg-num");
      if (n) {
        n.textContent = String(i + 1);
      }
      var rm = block.querySelector(".btn-remove-leg");
      if (rm) {
        rm.hidden = getLegBlocks().length <= 1;
      }
    });
  }

  function applyTripStartToFirstLeg() {
    if (!tripStart || !tripStart.value) {
      return;
    }
    var first = getLegBlocks()[0];
    if (!first) {
      return;
    }
    var from = first.querySelector(".date-range-pair .date-from");
    if (from) {
      from.value = tripStart.value;
      var pair = from.closest(".date-range-pair");
      if (pair && window.syncDateRangePair) {
        window.syncDateRangePair(pair);
      }
    }
  }

  function chainNextLegStart(prevBlock) {
    var toInput = prevBlock.querySelector(".date-range-pair .date-to");
    if (!toInput || !toInput.value) {
      return;
    }
    var blocks = Array.prototype.slice.call(getLegBlocks());
    var idx = blocks.indexOf(prevBlock);
    var next = blocks[idx + 1];
    if (!next) {
      return;
    }
    var nextFrom = next.querySelector(".date-range-pair .date-from");
    if (nextFrom) {
      nextFrom.value = toInput.value;
      var pair = nextFrom.closest(".date-range-pair");
      if (pair && window.syncDateRangePair) {
        window.syncDateRangePair(pair);
      }
    }
  }

  if (tripStart) {
    tripStart.addEventListener("change", applyTripStartToFirstLeg);
    tripStart.addEventListener("input", applyTripStartToFirstLeg);
  }

  container.addEventListener("change", function (e) {
    var t = e.target;
    if (t.classList && t.classList.contains("date-to")) {
      var pair = t.closest(".date-range-pair");
      var block = pair && pair.closest(".leg-block");
      if (block) {
        chainNextLegStart(block);
      }
    }
  });

  container.addEventListener("input", function (e) {
    var t = e.target;
    if (t.classList && t.classList.contains("date-to")) {
      var pair = t.closest(".date-range-pair");
      var block = pair && pair.closest(".leg-block");
      if (block) {
        chainNextLegStart(block);
      }
    }
  });

  addBtn.addEventListener("click", function () {
    var blocks = getLegBlocks();
    var last = blocks[blocks.length - 1];
    var clone = tpl.content.cloneNode(true);
    container.appendChild(clone);
    var newBlock = getLegBlocks()[getLegBlocks().length - 1];
    var prevTo = last ? last.querySelector(".date-range-pair .date-to") : null;
    var newFrom = newBlock.querySelector(".date-range-pair .date-from");
    if (prevTo && prevTo.value && newFrom) {
      newFrom.value = prevTo.value;
    }
    var newPair = newBlock.querySelector(".date-range-pair");
    if (newPair && window.syncDateRangePair) {
      window.syncDateRangePair(newPair);
    }
    renumberLegs();
  });

  container.addEventListener("click", function (e) {
    var btn = e.target.closest(".btn-remove-leg");
    if (!btn || btn.hidden) {
      return;
    }
    if (getLegBlocks().length <= 1) {
      return;
    }
    btn.closest(".leg-block").remove();
    renumberLegs();
  });

  renumberLegs();
  if (tripStart && tripStart.value) {
    var firstFrom = getLegBlocks()[0] && getLegBlocks()[0].querySelector(".date-range-pair .date-from");
    if (firstFrom && !firstFrom.value) {
      applyTripStartToFirstLeg();
    }
  }
})();
