/**
 * Sticky month rail: scroll-to-section and active state when a month heading
 * intersects the upper region of the viewport.
 * Scoped to [data-glance-timeline] on the home At a glance section.
 */
(function () {
  var root = document.querySelector("[data-glance-timeline]");
  if (!root) {
    return;
  }

  var buttons = root.querySelectorAll(".glance-rail-item");
  if (!buttons.length) {
    return;
  }

  var headings = root.querySelectorAll(".glance-month-heading");
  if (!headings.length) {
    return;
  }

  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function behaviorScroll() {
    return reduced ? "auto" : "smooth";
  }

  function setActiveHeading(el) {
    if (!el || !el.id) {
      return;
    }
    var want = "#" + el.id;
    buttons.forEach(function (b) {
      var t = b.getAttribute("data-scroll-target");
      var on = t === want;
      b.classList.toggle("is-active", on);
      if (on) {
        b.setAttribute("aria-current", "true");
      } else {
        b.removeAttribute("aria-current");
      }
    });
  }

  buttons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      var sel = btn.getAttribute("data-scroll-target");
      if (!sel) {
        return;
      }
      var el = document.querySelector(sel);
      if (el) {
        el.scrollIntoView({ behavior: behaviorScroll(), block: "start" });
        setActiveHeading(el);
      }
    });
  });

  if (!("IntersectionObserver" in window)) {
    if (headings[0]) {
      setActiveHeading(headings[0]);
    }
    return;
  }

  var obs = new IntersectionObserver(
    function (entries) {
      var inside = entries.filter(function (e) {
        return e.isIntersecting;
      });
      if (!inside.length) {
        return;
      }
      inside.sort(function (a, b) {
        return a.boundingClientRect.top - b.boundingClientRect.top;
      });
      setActiveHeading(inside[0].target);
    },
    { root: null, rootMargin: "-8% 0px -70% 0px", threshold: [0, 0.01, 0.1] }
  );

  Array.prototype.forEach.call(headings, function (h) {
    obs.observe(h);
  });
})();
