/*
 * The flow, ported from `shell/Rina.Shell/Flow.cs` and the field loop of
 * `Backdrop.cs`.
 *
 * **A port, not an impression.** The living background of the program is
 * fractal noise whose own coordinates are bent by more noise; an
 * approximation with drifting gradients was tried in the program first
 * and could not produce a filament or an eddy, which is exactly why the
 * program does it this way. A mock-up that faked the background would
 * be showing something the program does not have.
 *
 * So the arithmetic is the same, value for value: the hash, the
 * smoothstep, the four octaves with their 2.03 in space and 1.27 in
 * time, three octaves in the warp, the 0.44 centre and 2.6 gain of the
 * ramp mapping, the 208 by 117 field. The palettes come from
 * `tools/nebula.py` through `flow-ramps.js`, generated — they are not
 * written here, because they are not this file's to invent.
 *
 * **What differs, and why.** The program computes on the CPU in C# and
 * enlarges with smoothing; here the same field is written into a small
 * canvas and enlarged by the browser, which does the same thing. The
 * program's own comment says the field has no detail finer than its own
 * features, so this is the picture, not a reduction of it.
 *
 * One number is deliberately not the same: the frame rate. The program
 * asks the tokens (twenty by default) and stops when nobody is looking.
 * Here it follows the display and stops when the page is hidden or the
 * canvas is off screen — the same rule, kept by what a browser has.
 */
window.RinaFlow = (function () {
  "use strict";

  /* Where the field sits and how far it is stretched to fill the ramp.
     Fractal noise does not fill its own range: measured, the field's
     fifth-to-ninety-fifth percentile is 0.27 to 0.61, a third of the
     palette clustered on the centre. */
  var CENTRE = 0.44;
  var GAIN = 2.6;

  /* A repeatable number in [0, 1) from three whole coordinates. The C#
     is `unchecked` 32-bit arithmetic, so the multiplications are
     `Math.imul` and the shifts keep the sign the same way. */
  function hash(x, y, z) {
    var n = (Math.imul(x, 374761393) + Math.imul(y, 668265263)
             + Math.imul(z, 1274126177)) | 0;
    n = Math.imul(n ^ (n >> 13), 1274126177) | 0;
    return ((n ^ (n >> 16)) & 0x7fffffff) / 0x7fffffff;
  }

  function plane(xi, yi, zi, u, v) {
    var c00 = hash(xi, yi, zi);
    var c10 = hash(xi + 1, yi, zi);
    var c01 = hash(xi, yi + 1, zi);
    var c11 = hash(xi + 1, yi + 1, zi);
    return (c00 * (1 - u) + c10 * u) * (1 - v)
         + (c01 * (1 - u) + c11 * u) * v;
  }

  /* Smooth value noise on a three-dimensional lattice. Two coordinates
     are the place, the third is time, and all three are interpolated —
     without the third the field stands still inside a cell and snaps
     when it leaves one. */
  function noise(x, y, z) {
    var xi = Math.floor(x), yi = Math.floor(y), zi = Math.floor(z);
    var xf = x - xi, yf = y - yi, zf = z - zi;
    var u = xf * xf * (3 - 2 * xf);
    var v = yf * yf * (3 - 2 * yf);
    var w = zf * zf * (3 - 2 * zf);
    var near = plane(xi, yi, zi, u, v);
    var far = plane(xi, yi, zi + 1, u, v);
    return near * (1 - w) + far * w;
  }

  /* Four octaves, each finer and quieter. Time speeds up with them, but
     far less than space does: at the same factor the fine detail boils
     while the large forms barely move. */
  function fbm(x, y, z, octaves) {
    var sum = 0;
    var weight = 0.5;
    for (var at = 0; at < (octaves || 4); at++) {
      sum += weight * noise(x, y, z);
      x *= 2.03;
      y *= 2.03;
      z *= 1.27;
      weight *= 0.5;
    }
    return sum * 2 - 1;
  }

  function shade(ramp, value) {
    value = (value * 0.5 + 0.5 - CENTRE) * GAIN + 0.5;
    value = value < 0 ? 0 : (value > 0.999 ? 0.999 : value);
    var place = value * (ramp.length - 1);
    var low = Math.floor(place);
    var mix = place - low;
    var a = ramp[low];
    var b = ramp[Math.min(low + 1, ramp.length - 1)];
    return [a[0] + (b[0] - a[0]) * mix,
            a[1] + (b[1] - a[1]) * mix,
            a[2] + (b[2] - a[2]) * mix];
  }

  function parse(stops) {
    return stops.map(function (one) {
      return [parseInt(one.slice(1, 3), 16),
              parseInt(one.slice(3, 5), 16),
              parseInt(one.slice(5, 7), 16)];
    });
  }

  /* The same size the program computes at, and for the same reason. */
  var WIDE = 208;
  var HIGH = 117;

  function Field(canvas, calmCanvas) {
    this.canvas = canvas;
    this.calmCanvas = calmCanvas || null;
    canvas.width = WIDE;
    canvas.height = HIGH;
    this.ink = canvas.getContext("2d", { alpha: false });
    this.frame = this.ink.createImageData(WIDE, HIGH);
    if (this.calmCanvas) {
      this.calmCanvas.width = WIDE;
      this.calmCanvas.height = HIGH;
      this.calmInk = this.calmCanvas.getContext("2d", { alpha: false });
      this.calmFrame = this.calmInk.createImageData(WIDE, HIGH);
    }
    this.field = new Float32Array(WIDE * HIGH);

    /* The same values the program carries, including the offset: at a
       whole number every octave sits on a lattice plane at once and the
       flow very nearly stops, so starting at zero would give the
       stillest moment it has at the moment a person first looks. */
    this.elapsed = 13.37;

    /* The program's values, from `docs/design/tokens.json` through
       `flow-ramps.js`: period 9 seconds for a full rebuild, drift 3.0,
       scale 3.2, warp 1.1. Written here as defaults only so the file
       runs on its own; the page hands over the generated ones. */
    this.scale = 3.2;
    this.warp = 1.1;
    this.drift = 3.0;
    this.period = 9;
    this.wanderX = 0;
    this.wanderY = 0;
    this.churnX = 0;
    this.churnY = 0;
    this.ramp = [];
    this.calmRamp = [];
    this.running = false;
  }

  Field.prototype.palette = function (stops, calmStops) {
    this.ramp = parse(stops);
    this.calmRamp = parse(calmStops || stops);
  };

  /* Time is counted in periods, not in seconds: the step is the frame's
     own interval divided by the period, so a late frame moves the flow
     further instead of slowing it down. `elapsed` is where the field is
     and only grows.

     The field travels as well as morphing in place, and the travelling
     is what makes it read as moving at all — a feature that stays put
     while changing shape is a still picture being redrawn. Two headings
     on periods that do not divide into one another, applied at
     different depths of the warp, is what makes the parts disagree. */
  Field.prototype.advance = function (seconds) {
    var step = seconds / this.period;
    this.elapsed += step;

    var oneWay = this.elapsed * 0.37 + Math.sin(this.elapsed * 0.61) * 1.7;
    var other = this.elapsed * -0.23
                + Math.sin(this.elapsed * 0.41 + 2.1) * 2.3;

    this.wanderX += step * this.drift * Math.cos(oneWay);
    this.wanderY += step * this.drift * Math.sin(oneWay) * 0.8;
    this.churnX += step * this.drift * Math.cos(other) * 1.4;
    this.churnY += step * this.drift * Math.sin(other) * 1.4;
  };

  Field.prototype.paint = function () {
    if (!this.ramp.length) { return; }
    var z = this.elapsed;
    var slide = this.wanderX;
    var lift = this.wanderY;
    var aspect = WIDE / HIGH;
    var data = this.frame.data;
    var calmData = this.calmFrame ? this.calmFrame.data : null;

    for (var y = 0; y < HIGH; y++) {
      var v = y / HIGH * this.scale + lift;
      var row = y * WIDE;
      for (var x = 0; x < WIDE; x++) {
        var u = x / WIDE * this.scale * aspect + slide;

        /* Domain warping, twice. One level gives clouds; two give the
           filaments and eddies that read as liquid. Three octaves
           here, as in the background — the fourth is detail an
           enlarged field cannot show. */
        var qx = fbm(u, v, z, 3);
        var qy = fbm(u + 5.2, v + 1.3, z, 3);
        var rx = fbm(u + this.warp * qx + 1.7 + this.churnX,
                     v + this.warp * qy + 9.2 + this.churnY, z, 3);
        var ry = fbm(u + this.warp * qx + 8.3 + this.churnX,
                     v + this.warp * qy + 2.8 + this.churnY, z, 3);
        var value = fbm(u + this.warp * rx, v + this.warp * ry, z, 3);

        this.field[row + x] = value;
        var at = (row + x) * 4;
        var lit = shade(this.ramp, value);
        data[at] = lit[0];
        data[at + 1] = lit[1];
        data[at + 2] = lit[2];
        data[at + 3] = 255;
        if (calmData) {
          var dim = shade(this.calmRamp, value);
          calmData[at] = dim[0];
          calmData[at + 1] = dim[1];
          calmData[at + 2] = dim[2];
          calmData[at + 3] = 255;
        }
      }
    }

    this.ink.putImageData(this.frame, 0, 0);
    if (this.calmInk) { this.calmInk.putImageData(this.calmFrame, 0, 0); }
  };

  /* It stops when nobody is looking — the program's rule, kept with
     what a browser has: the page hidden, or the canvas off screen. */
  Field.prototype.start = function () {
    var self = this;
    var last = 0;
    var seen = true;

    if ("IntersectionObserver" in window) {
      new IntersectionObserver(function (rows) {
        seen = rows[0].isIntersecting;
      }).observe(this.canvas);
    }

    var still = window.matchMedia("(prefers-reduced-motion: reduce)");

    function tick(now) {
      requestAnimationFrame(tick);
      if (document.hidden || !seen) { last = now; return; }
      var gap = last ? Math.min((now - last) / 1000, 0.25) : 0;
      last = now;
      if (still.matches) {
        if (!self.running) { self.paint(); self.running = true; }
        return;
      }
      self.advance(gap);
      self.paint();
      self.running = true;
    }

    requestAnimationFrame(tick);
  };

  return { Field: Field, fbm: fbm, shade: shade, WIDE: WIDE, HIGH: HIGH };
})();
