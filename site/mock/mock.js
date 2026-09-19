/*
 * The window on the page: what makes it move.
 *
 * This and `flow.js`, `figure.js` are the only scripts on the site, and
 * they live on the only page that says so. They read nothing, store
 * nothing and send nothing — there is no network call and no storage of
 * any kind in any of the three, which is what lets the rest of the site
 * keep the promise whole.
 *
 * The data is generated: `cases.js` from `docs/golden/utterances.json`,
 * the phrases and the parse that pin the real program down;
 * `flow-ramps.js` from `tools/nebula.py`, the palettes of the living
 * background. Only the wording of her replies is the mock's own, and
 * the page says so.
 */
(function () {
  "use strict";

  var cases = window.RINA_CASES || [];
  var chips = window.RINA_CHIPS || [];
  var palettes = window.RINA_FLOW || {};

  var stage = document.getElementById("stage");
  var win = document.getElementById("win");
  var rail = document.getElementById("rail");
  var talk = document.getElementById("talk");
  var line = document.getElementById("line");
  var send = document.getElementById("send");
  var chipsBox = document.getElementById("chips");
  var besides = document.getElementById("besides");
  var ready = document.getElementById("ready");
  var knobs = document.getElementById("knobs");
  var level = win.querySelector(".win-level");

  var FINISHES = ["silver", "black", "graphite"];
  var ACCENTS = ["amber", "ember", "brass", "moss", "steel", "orchid"];

  /* ---- the window is drawn full size and scaled whole -------------- */
  var WIDE = 1180;
  var HIGH = 780;

  function fit() {
    var room = stage.clientWidth;
    var scale = Math.min(1, room / WIDE);
    win.style.setProperty("--fit", scale);
    stage.style.height = Math.round(HIGH * scale) + "px";
  }

  fit();
  window.addEventListener("resize", fit);

  /* ---- the flow ----------------------------------------------------- */
  var field = new window.RinaFlow.Field(document.getElementById("flow"),
                                        document.getElementById("calm"));
  var orb = new window.RinaFigure.Orb(document.getElementById("orb"));

  function dress() {
    var finish = FINISHES.find(function (one) {
      return win.classList.contains(one);
    }) || "graphite";
    var accent = ACCENTS.find(function (one) {
      return win.classList.contains(one);
    }) || "amber";
    var shades = palettes[finish] || {};
    var stops = (shades.accents || {})[accent];
    if (!stops) { return; }
    field.scale = shades.scale;
    field.warp = shades.warp;
    field.period = shades.period;
    field.drift = shades.drift;
    field.palette(stops.vivid, stops.calm);
  }

  dress();

  /* One clock for everything that moves at the flow's pace. A second
     one would be a second place to remember every reason this stops,
     which is a second place to forget it. */
  var still = window.matchMedia("(prefers-reduced-motion: reduce)");
  var seen = true;
  if ("IntersectionObserver" in window) {
    new IntersectionObserver(function (rows) {
      seen = rows[0].isIntersecting;
    }).observe(stage);
  }

  /* The program computes the field on several cores; a page has one.
     Measured here: 29 ms for the field and 35 for the figure, which at
     every frame would be fifteen a second and jerky. So the drawing is
     paced and the *motion* is not: the field advances by the real time
     elapsed, so the flow travels at the program's speed and is simply
     drawn less often. The number is the one thing about the background
     that is deliberately not 1:1, and the page says so. */
  var PACE = 1 / 24;
  var owed = 0;

  var last = 0;
  var painted = false;
  function tick(now) {
    requestAnimationFrame(tick);
    if (document.hidden || !seen) { last = now; return; }
    var gap = last ? Math.min((now - last) / 1000, 0.25) : 0;
    last = now;
    if (!field.ramp.length) { return; }
    if (still.matches) {
      if (!painted) {
        field.paint();
        orb.advance(0);
        orb.paint();
        painted = true;
      }
      return;
    }
    field.advance(gap);
    if (win.dataset.section === "home") { orb.advance(gap); }

    owed += gap;
    if (owed < PACE) { return; }
    owed = 0;
    field.paint();
    if (win.dataset.section === "home") { orb.paint(); }
  }
  requestAnimationFrame(tick);

  /* ---- sections ----------------------------------------------------- */
  var pages = {};
  [].forEach.call(document.querySelectorAll(".win-page"), function (one) {
    pages[one.dataset.page] = one;
  });

  function show(name) {
    if (!pages[name]) { return; }
    [].forEach.call(rail.children, function (one) {
      if (one.dataset.go === name) { one.setAttribute("aria-current", "page"); }
      else { one.removeAttribute("aria-current"); }
    });
    Object.keys(pages).forEach(function (one) {
      if (one === name) { pages[one].setAttribute("data-open", ""); }
      else { pages[one].removeAttribute("data-open"); }
    });
    win.dataset.section = name;
  }

  rail.addEventListener("click", function (event) {
    var button = event.target.closest("[data-go]");
    if (button) { show(button.dataset.go); }
  });

  /* ---- what she heard ------------------------------------------------ */
  function plain(text) {
    return String(text).toLowerCase().replace(/\s+/g, " ").trim();
  }

  var known = new Map();
  cases.forEach(function (one) {
    var key = plain(one.say);
    if (!known.has(key)) { known.set(key, []); }
    known.get(key).push(one);
  });

  function when() {
    var now = new Date();
    return ("0" + now.getHours()).slice(-2) + ":"
         + ("0" + now.getMinutes()).slice(-2);
  }

  function say(who, text) {
    var bubble = document.createElement("div");
    bubble.className = "win-said";
    bubble.dataset.who = who;
    bubble.appendChild(document.createTextNode(text));
    var stamp = document.createElement("time");
    stamp.className = "win-meta";
    stamp.textContent = when();
    bubble.appendChild(stamp);
    talk.appendChild(bubble);
    while (talk.children.length > 8) { talk.removeChild(talk.firstChild); }
  }

  function state(name) {
    win.dataset.state = name;
    orb.be(name);
    if (ready) {
      ready.textContent = name === "listening" ? "Слушаю."
        : name === "thinking" ? "Думаю."
        : name === "answering" ? "Отвечаю." : "Готова помочь.";
    }
  }

  /* The level bar does not switch between off and on: after a phrase is
     heard the trace fades over a second. The afterglow is a signature of
     direction, not decoration. */
  function heard(much) {
    level.style.setProperty("--heard", much);
  }

  function alsoSays(one) {
    var all = known.get(plain(one.say)) || [];
    var rest = all.filter(function (other) { return other.id !== one.id; });
    besides.hidden = !rest.length;
    if (!rest.length) { return; }
    besides.textContent = "Эта же фраза записана в наборе ещё "
      + rest.length + " раз" + (rest.length === 1 ? "" : "а") + ": "
      + rest.map(function (other) {
          return other.intent + (other.note ? " — " + other.note : "");
        }).join("; ") + ".";
  }

  var waiting = [];
  function later(what, delay) {
    waiting.push(setTimeout(what, delay));
  }

  function run(one, text) {
    waiting.forEach(clearTimeout);
    waiting = [];
    besides.hidden = true;
    show("dialog");

    state("listening");
    heard(0.72);
    say("me", text);

    later(function () {
      state("thinking");
      heard(0);
    }, 420);

    later(function () {
      if (!one) {
        state("answering");
        say("her", "Этой фразы нет в записанном наборе. "
                 + "Возьмите одну из готовых.");
      } else {
        alsoSays(one);
        state(one.heavy ? "asking" : "answering");
        say("her", one.said || "…");
      }
      later(function () { state("idle"); }, 1600);
    }, 900);
  }

  function ask(text) {
    var all = known.get(plain(text));
    run(all ? all[0] : null, text);
  }

  send.addEventListener("click", function () {
    var text = line.value.trim();
    if (text) { ask(text); line.value = ""; }
  });

  line.addEventListener("keydown", function (event) {
    if (event.key === "Enter") { send.click(); }
  });

  chips.forEach(function (id) {
    var one = cases.find(function (c) { return c.id === id; });
    if (!one) { return; }
    var button = document.createElement("button");
    button.type = "button";
    button.className = "press chip";
    button.textContent = one.say;
    /* The chip runs its own recorded case, not a lookup by phrase: the
       phrase may have several readings, and the chip means this one. */
    button.addEventListener("click", function () { run(one, one.say); });
    chipsBox.appendChild(button);
  });

  /* ---- finish and accent --------------------------------------------- */
  knobs.addEventListener("change", function (event) {
    var name = event.target.name;
    if (name !== "finish" && name !== "accent") { return; }
    (name === "finish" ? FINISHES : ACCENTS).forEach(function (one) {
      win.classList.remove(one);
    });
    win.classList.add(event.target.value);
    dress();
  });

  /* ---- switches ------------------------------------------------------ */
  document.addEventListener("click", function (event) {
    var toggle = event.target.closest(".win-toggle");
    if (!toggle) { return; }
    var on = toggle.getAttribute("aria-pressed") === "true";
    toggle.setAttribute("aria-pressed", on ? "false" : "true");
  });

  /* Sliders are drawn at the value they hold; the markup carries it. */
  [].forEach.call(document.querySelectorAll("[style-at]"), function (one) {
    one.style.setProperty("--at", one.getAttribute("style-at"));
  });
})();
