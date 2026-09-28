// The beta's telemetry collector (`4.0b-D05`), on Cloudflare Workers.
//
// It takes one thing — a report in the shape `core/telemetry.py` builds —
// and refuses everything else. The check here is as strict as the building
// there, and for the same reason: a field this side accepts is a field
// somebody could fill with a phrase, a path or a name, and the promise on
// the product page is that nothing of the kind is ever received.
//
// What is kept: the day it arrived and the report. Not the address it came
// from, not the time of day. One report per installation per day.
// Everything older than RETAIN_DAYS is deleted every night, and the whole
// collector goes with 4.0.0 Stable (`4.0-S04`).

const SCHEMA = 1;
const MAX_BYTES = 16 * 1024;
const RETAIN_DAYS = 180;

const FIELDS = ["schema", "install", "app", "os", "language", "days",
  "engines", "features", "tools", "errors", "reasons", "timings"];
const ENGINE_FIELDS = ["stt_engine", "tts_engine", "model", "always_listen",
  "personality"];
const COUNTED = ["features", "tools", "errors", "reasons"];
const TIMED = ["recognition", "first_sound"];

// A word from the program's own vocabulary: an intent, a tool, a tool and
// its error code or reason. Lower-case Latin, digits, `_`, `.`, `:`.
const WORD = /^[a-z][a-z0-9_.:]{0,63}$/;
const INSTALL = /^[0-9a-f]{32}$/;
const VERSION = /^[0-9A-Za-z.+-]{1,32}$/;
const WINDOWS = /^(windows \d+(\.\d+){0,3}|other)$/;

function sameKeys(value, keys) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const have = Object.keys(value).sort();
  const want = [...keys].sort();
  return have.length === want.length && have.every((k, i) => k === want[i]);
}

function isCount(n) {
  return Number.isInteger(n) && n >= 0 && n <= 1_000_000;
}

// Why a report was refused, or "" if it is acceptable. Exported for the
// check, which feeds it the reports the core really builds.
export function validate(report) {
  if (!sameKeys(report, FIELDS)) return "fields";
  if (report.schema !== SCHEMA) return "schema";
  if (typeof report.install !== "string" || !INSTALL.test(report.install)) return "install";
  if (typeof report.app !== "string" || !(VERSION.test(report.app) || report.app === "other")) return "app";
  if (typeof report.os !== "string" || !WINDOWS.test(report.os)) return "os";
  if (report.language !== "ru" && report.language !== "en") return "language";
  if (!Number.isInteger(report.days) || report.days < 1 || report.days > 400) return "days";

  const engines = report.engines;
  if (!sameKeys(engines, ENGINE_FIELDS)) return "engines";
  for (const key of ["stt_engine", "tts_engine"]) {
    if (typeof engines[key] !== "string" || !WORD.test(engines[key])) return "engines";
  }
  for (const key of ["model", "always_listen"]) {
    if (typeof engines[key] !== "boolean") return "engines";
  }
  if (engines.personality !== "rina" && engines.personality !== "own") return "engines";

  for (const group of COUNTED) {
    const counts = report[group];
    if (!counts || typeof counts !== "object" || Array.isArray(counts)) return group;
    const words = Object.keys(counts);
    if (words.length > 200) return group;
    for (const word of words) {
      if (!WORD.test(word) || !isCount(counts[word])) return group;
    }
  }

  const timings = report.timings;
  if (!timings || typeof timings !== "object" || Array.isArray(timings)) return "timings";
  for (const what of Object.keys(timings)) {
    if (!TIMED.includes(what)) return "timings";
    if (!sameKeys(timings[what], ["n", "p50_ms", "p90_ms"])) return "timings";
    for (const key of ["n", "p50_ms", "p90_ms"]) {
      if (!isCount(timings[what][key])) return "timings";
    }
  }
  return "";
}

function today() {
  return new Date().toISOString().slice(0, 10);
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method !== "POST" || url.pathname !== "/v1/report") {
      return new Response(null, { status: 404 });
    }
    const body = await request.text();
    if (body.length > MAX_BYTES) return new Response(null, { status: 413 });

    let report;
    try {
      report = JSON.parse(body);
    } catch {
      return new Response(null, { status: 400 });
    }
    const refused = validate(report);
    if (refused) return new Response(refused, { status: 400 });

    // One a day from one installation: a second is ignored, not an error —
    // the program retries what it thinks did not arrive.
    await env.DB.prepare(
      "INSERT OR IGNORE INTO reports (day, install, report) VALUES (?, ?, ?)"
    ).bind(today(), report.install, JSON.stringify(report)).run();
    return new Response(null, { status: 204 });
  },

  async scheduled(event, env) {
    const cutoff = new Date(Date.now() - RETAIN_DAYS * 86400 * 1000)
      .toISOString().slice(0, 10);
    await env.DB.prepare("DELETE FROM reports WHERE day < ?").bind(cutoff).run();
  },
};
