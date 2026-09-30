// The shape of a telemetry report, as the collector accepts it (`4.0b-D05`).
//
// The check here is as strict as the building in `core/telemetry.py`, and
// for the same reason: a field this side accepts is a field somebody could
// fill with a phrase, a path or a name, and the promise on the product page
// is that nothing of the kind is ever received.
//
// No dependencies and no platform: `tools/test_telemetry.py` runs this file
// under plain Node against the reports the core really builds.

export const SCHEMA = 1;
export const MAX_BYTES = 16 * 1024;

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

// Why a report was refused, or "" if it is acceptable.
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
