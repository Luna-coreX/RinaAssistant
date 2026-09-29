/*
 * The room of the first screen: the program's living field in the opening
 * and Rina's figure standing in it.
 *
 * Both are drawn by ../mock/flow.js and ../mock/figure.js — ports of
 * `Flow.cs` and `Figure.cs`, value for value — so what the visitor sees is
 * the program's own picture, not an illustration of it. Two things are
 * this file's own: how often the drawing runs, and three phrases she
 * answers the way the program answers them.
 *
 * Nothing here reaches the network, and it could not: the page's policy
 * is `default-src 'none'` with `script-src 'self'` and no `connect-src`.
 * Without scripts the opening keeps a still gradient of the same colours
 * and the page reads the same.
 */
(function () {
  "use strict";

  var flowCanvas = document.getElementById("flow");
  var orbCanvas = document.getElementById("orb");
  var arch = document.querySelector(".arch");
  var speech = document.querySelector(".speech");
  if (!flowCanvas || !orbCanvas || !window.RinaFlow || !window.RinaFigure
      || !window.RINA_FLOW) {
    return;
  }

  var shades = window.RINA_FLOW.graphite;
  var stops = shades && shades.accents && shades.accents.amber;
  if (!stops) { return; }

  var field = new window.RinaFlow.Field(flowCanvas);
  field.scale = shades.scale;
  field.warp = shades.warp;
  field.period = shades.period;
  field.drift = shades.drift;
  field.palette(stops.vivid, stops.calm);

  var orb = new window.RinaFigure.Orb(orbCanvas);
  var still = window.matchMedia("(prefers-reduced-motion: reduce)");

  /* --- pacing ---------------------------------------------------------
   *
   * Both are computed on the CPU, as in the program, and a page has one
   * thread for them and for everything the visitor does. So the drawing
   * is paced by what it costs on this machine and the motion is not: each
   * advances by the real time elapsed, so the flow travels at the
   * program's speed and is drawn as often as a share of the thread
   * allows. Measured, not assumed — the mock-up's own note puts the field
   * at 29 ms and the figure at 35 on a slow machine, and on a fast one
   * both are a fraction of that.
   */
  var SHARE_FIELD = 0.14;
  var SHARE_ORB = 0.2;
  var fieldCost = 0.02;
  var orbCost = 0.02;
  var fieldOwed = 0;
  var orbOwed = 0;
  var fieldGap = 0;
  var orbGap = 0;

  function timed(paint, cost) {
    var began = performance.now();
    paint();
    var spent = (performance.now() - began) / 1000;
    return cost * 0.8 + spent * 0.2;
  }

  function paintField() {
    fieldCost = timed(function () { field.paint(); }, fieldCost);
  }

  function paintOrb() {
    orbCost = timed(function () { orb.paint(); }, orbCost);
  }

  var seen = true;
  if ("IntersectionObserver" in window) {
    new IntersectionObserver(function (rows) {
      seen = rows[0].isIntersecting;
    }).observe(arch);
  }

  var last = 0;
  var lit = false;

  function light() {
    if (lit) { return; }
    lit = true;
    document.documentElement.classList.add("lit");
  }

  /* Still, for a visitor who asked for less motion: one frame of each,
     and a new one only when the figure's state changes. */
  function settle() {
    for (var i = 0; i < 90; i++) { orb.advance(1 / 60 / field.period); }
    paintOrb();
  }

  function tick(now) {
    requestAnimationFrame(tick);
    if (document.hidden || !seen) { last = now; return; }
    var gap = last ? Math.min((now - last) / 1000, 0.25) : 0;
    last = now;

    if (still.matches) {
      if (!lit) {
        field.advance(0);
        paintField();
        settle();
        light();
      }
      return;
    }

    field.advance(gap);
    /* The figure takes the flow's step, as in the program. */
    orb.advance(gap / field.period);
    fieldGap = Math.max(1 / 24, fieldCost / SHARE_FIELD);
    orbGap = Math.max(1 / 40, orbCost / SHARE_ORB);
    fieldOwed += gap;
    orbOwed += gap;

    if (!lit || fieldOwed >= fieldGap) {
      fieldOwed = 0;
      paintField();
    }
    if (!lit || orbOwed >= orbGap) {
      orbOwed = 0;
      paintOrb();
    }
    light();
  }

  requestAnimationFrame(tick);

  /* --- three phrases ----------------------------------------------------
   *
   * The replies are the program's own lines, word for word: «Запускаю
   * Блокнот.», «Засекла 10 мин.», «Получается 180.». The figure goes
   * through the states it goes through in the program — hearing, then
   * thinking, then speaking — for about as long as they take on a machine
   * where recognition and the reply are local.
   */
  var buttons = Array.prototype.slice.call(
    document.querySelectorAll(".phrases button"));
  var timers = [];

  function later(ms, work) {
    timers.push(window.setTimeout(work, ms));
  }

  function become(state) {
    orb.be(state);
    if (still.matches) { settle(); }
  }

  function say(button) {
    timers.forEach(window.clearTimeout);
    timers = [];
    buttons.forEach(function (one) {
      one.toggleAttribute("data-speaking", one === button);
    });
    speech.classList.remove("said");

    become("listening");
    later(1100, function () { become("thinking"); });
    later(1650, function () {
      become("answering");
      speech.textContent = button.getAttribute("data-reply");
      speech.classList.add("said");
    });
    later(3900, function () { become("idle"); });
    later(6200, function () {
      speech.classList.remove("said");
      button.removeAttribute("data-speaking");
    });
  }

  buttons.forEach(function (button) {
    button.addEventListener("click", function () { say(button); });
  });
}());
