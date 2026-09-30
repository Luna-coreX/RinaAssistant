/*
 * The figure, ported from `shell/Rina.Shell/Figure.cs`.
 *
 * The same flow gathered into a disc — one field, seen twice — with a
 * thin film of colour over a nearly black core. The maths is the
 * program's: the wound surface point, the three terms of light, the
 * crest window, the hue that runs mostly with the flow and only a
 * little with the grazing angle, the rim that fades rather than cutting
 * a circle.
 *
 * Everything is followed rather than assigned: the first edition of the
 * program eased only the swell and switched the rest the instant the
 * state changed, and a person saw the sphere's insides jump while its
 * outside grew smoothly.
 *
 * **The state table is `Figure.cs`'s, and it was not until 2026-09-29.**
 * The first port swapped two columns: idle stood at swell 0.35 and no
 * spin, where the program has no swell and a spin of 0.35. The sphere came
 * out 1.21 times the canvas — clipped by its edges into a rounded square —
 * and stood still; the other states were not the program's at all. They
 * are now, in the program's order of meaning, with one allowance: the
 * program swells and bursts with the loudness of real sound, and a page
 * has none, so `LOUD` stands in for a person speaking at a middle level.
 *
 * Time is the program's too: `advance` takes the flow's step — seconds
 * divided by the flow's period — and every value follows by the power of
 * the tuning tick, so a transition takes the same time at any frame rate.
 * The film's hue is the accent's, as in the program, and does not drift.
 */
window.RinaFigure = (function () {
  "use strict";

  var SIDE = 200;
  var GRAIN = 2.3;

  /* A sixtieth of a second of a nine-second period: the tick the paces
     below were tuned on (`Figure.TunedStep`). */
  var TUNED_STEP = 1 / 540;

  /* How loud a person is taken to be while listening and talking. */
  var LOUD = 0.35;

  /* swell, spin, twist, churn, burst, gloss, lamp — `Figure.cs`, with
     `_loud` replaced by LOUD. «asking» is a reply that asks for
     confirmation: the program has no state of its own for it and talks. */
  var TALKING = [0.05 + LOUD * 0.16, 0.9, 1.4, 1.6, 0.10 + LOUD * 0.55,
                 70 + LOUD * 120, 0.48 + LOUD * 0.22];
  var STATES = {
    idle:      [0.00, 0.35, 0.90, 0.80, 0.00, 70, 0.42],
    listening: [0.09 + LOUD * 0.20, 0.5, 1.1, 1.3, LOUD * 0.30, 95, 0.74],
    thinking:  [0.04, 2.1, 2.6, 2.2, 0.16, 240, 0.26],
    answering: TALKING,
    asking:    TALKING
  };

  /* The accent's hue, as `Figure.Hue` takes it: amber, #f2731c. */
  var AMBER_HUE = (function () {
    var r = 0xf2 / 255, g = 0x73 / 255, b = 0x1c / 255;
    var high = Math.max(r, g, b), low = Math.min(r, g, b), span = high - low;
    var hue = high === r ? (g - b) / span
      : high === g ? 2 + (b - r) / span : 4 + (r - g) / span;
    return (hue / 6 + 1) % 1;
  }());

  function follow(have, want, pace, ticks) {
    return have + (want - have) * (1 - Math.pow(1 - pace, ticks));
  }

  function fromHue(hue, sat, value) {
    hue -= Math.floor(hue);
    var sector = hue * 6;
    var step = sector - Math.floor(sector);
    var p = value * (1 - sat);
    var q = value * (1 - sat * step);
    var t = value * (1 - sat * (1 - step));
    switch (Math.floor(sector)) {
      case 0: return [value, t, p];
      case 1: return [q, value, p];
      case 2: return [p, value, t];
      case 3: return [p, q, value];
      case 4: return [t, p, value];
      default: return [value, p, q];
    }
  }

  function Orb(canvas) {
    this.canvas = canvas;
    canvas.width = SIDE;
    canvas.height = SIDE;
    this.ink = canvas.getContext("2d");
    this.frame = this.ink.createImageData(SIDE, SIDE);
    this.state = "idle";

    this.shown = 0;
    this.spin = 0.35;
    this.twist = 0.9;
    this.churn = 0.8;
    this.burst = 0;
    this.gloss = 70;
    this.lamp = 0.42;

    this.turn = 0;
    this.breath = 0;
    this.churned = 13.37;
    this.hue = AMBER_HUE;
  }

  Orb.prototype.be = function (state) {
    if (STATES[state]) { this.state = state; }
  };

  /* `step` is the flow's: seconds divided by the flow's period. */
  Orb.prototype.advance = function (step) {
    var want = STATES[this.state] || STATES.idle;
    var ticks = step / TUNED_STEP;
    this.shown = follow(this.shown, want[0],
                        want[0] > this.shown ? 0.16 : 0.05, ticks);
    this.spin = follow(this.spin, want[1], 0.06, ticks);
    this.twist = follow(this.twist, want[2], 0.06, ticks);
    this.churn = follow(this.churn, want[3], 0.06, ticks);
    this.burst = follow(this.burst, want[4],
                        want[4] > this.burst ? 0.22 : 0.06, ticks);
    this.gloss = follow(this.gloss, want[5], 0.06, ticks);
    this.lamp = follow(this.lamp, want[6], 0.06, ticks);

    this.turn += step * this.spin;
    this.breath += step * (this.state === "idle" ? 0.5 : 1.2);
    this.churned += step * this.churn;
    this.swell = this.shown + Math.sin(this.breath * 2 * Math.PI) * 0.028;
  };

  Orb.prototype.paint = function () {
    var fbm = window.RinaFlow.fbm;
    var pixels = this.frame.data;
    var half = SIDE / 2;
    var radius = half * (0.86 + this.swell);
    var z = this.churned;
    var hue = this.hue;
    var turn = this.turn;
    var twist = this.twist;
    var burst = this.burst;
    var gloss = this.gloss;

    /* Upper left, and as far towards the eye as the state asks. The
       light is fixed and the surface turns under it. */
    var depth = Math.min(0.95, Math.max(0.05, this.lamp));
    var across = Math.sqrt(1 - depth * depth);
    var lightX = -0.68 * across;
    var lightY = -0.73 * across;
    var lightZ = depth;
    var halfLen = Math.sqrt(lightX * lightX + lightY * lightY
                            + (lightZ + 1) * (lightZ + 1));
    var hx = lightX / halfLen;
    var hy = lightY / halfLen;
    var hz = (lightZ + 1) / halfLen;

    for (var y = 0; y < SIDE; y++) {
      var dy = y - half;
      var row = y * SIDE * 4;
      for (var x = 0; x < SIDE; x++) {
        var dx = x - half;
        var reachOut = Math.sqrt(dx * dx + dy * dy);
        var at = row + x * 4;

        var about = Math.atan2(dy, dx);
        var scatter = burst <= 0.001 ? 0
          : fbm(Math.cos(about) * 1.7, Math.sin(about) * 1.7, z * 1.6, 4)
            * burst;
        var far = reachOut / (radius * (1 + scatter));

        if (far >= 1.06) { pixels[at + 3] = 0; continue; }

        var inside = Math.min(far, 1);
        var face = Math.sqrt(Math.max(0, 1 - inside * inside));
        var graze = 1 - face;
        var nx = dx / (radius * (1 + scatter));
        var ny = dy / (radius * (1 + scatter));
        if (inside >= 1) {
          var back = 1 / Math.max(inside, 0.0001);
          nx *= back;
          ny *= back;
        }

        var wind = turn + twist * face;
        var cw = Math.cos(wind);
        var sw = Math.sin(wind);
        var sx = nx * cw - ny * sw;
        var sy = nx * sw + ny * cw;

        var qx = fbm(sx * GRAIN, sy * GRAIN, face * GRAIN + z, 4);
        var field = fbm(sx * GRAIN + qx, sy * GRAIN, face * GRAIN + z, 4);

        var shade = hue + field * 1.05 + graze * 0.46 + z * 0.02;

        var diffuse = Math.max(0, nx * lightX + ny * lightY + face * lightZ);
        var spec = Math.pow(Math.max(0, nx * hx + ny * hy + face * hz), gloss);
        var rim = graze * graze * graze;

        var wave = field * 0.5 + 0.5;
        var crest = Math.min(1, Math.max(0, (wave - 0.42) / 0.34));
        crest *= crest * (3 - 2 * crest);
        var band = Math.exp(-(inside - 0.72) * (inside - 0.72) * 6);

        var lit = 0.02
                + crest * band * (0.18 + 0.92 * diffuse) * 1.05
                + diffuse * diffuse * 0.13
                + rim * 0.26
                + spec * 0.32;

        var sat = Math.min(1, Math.max(0, 0.60 + 0.28 * crest - spec * 0.30));
        var lamp = fromHue(shade, sat, Math.min(1, Math.max(0, lit)));

        var alpha = inside < 0.86 ? 1
          : Math.min(1, Math.max(0, (1.06 - far) / 0.20));

        pixels[at] = lamp[0] * 255;
        pixels[at + 1] = lamp[1] * 255;
        pixels[at + 2] = lamp[2] * 255;
        pixels[at + 3] = alpha * 255;
      }
    }

    this.ink.putImageData(this.frame, 0, 0);
  };

  return { Orb: Orb, SIDE: SIDE };
})();
