// What the collector does with a request, apart from where it runs.
//
// The two Vercel functions in `api/` are thin: they hand the request and a
// store over to these. The store is two calls — keep a report, drop the
// old ones — so `tools/test_telemetry.py` can drive both functions under
// plain Node with a store of its own, without a database or a deployment.
//
// What is kept: the day a report arrived and the report. Not the address
// it came from, not the time of day; nothing here writes to the log. One
// report per installation per day. Everything older than RETAIN_DAYS goes
// every night, and the whole collector goes with 4.0.0 Stable (`4.0-S04`).

import { MAX_BYTES, validate } from "./validate.js";

export const RETAIN_DAYS = 180;

function day(now) {
  return new Date(now).toISOString().slice(0, 10);
}

// `POST /api/v1/report`. `store.keep(day, install, report)` must ignore a
// second report from one installation on one day: the program retries what
// it thinks did not arrive, and a retry is not an error.
export async function receive(request, store, now = Date.now()) {
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

  await store.keep(day(now), report.install, JSON.stringify(report));
  return new Response(null, { status: 204 });
}

// `GET /api/clean`, called by Vercel Cron once a day. Vercel sends the
// project's CRON_SECRET as a bearer token; anybody else is turned away, and
// so is everybody while the secret is not set — a clean-up anyone can call
// is harmless today, but it is still a way to make us touch the database.
export async function clean(request, store, secret, now = Date.now()) {
  if (!secret || request.headers.get("authorization") !== `Bearer ${secret}`) {
    return new Response(null, { status: 401 });
  }
  await store.dropBefore(day(now - RETAIN_DAYS * 86400 * 1000));
  return new Response(null, { status: 204 });
}
