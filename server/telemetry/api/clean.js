// `GET /api/clean` — the nightly clean-up, scheduled in vercel.json.

import { clean } from "../collector.js";
import { store } from "../store.js";

export function GET(request) {
  return clean(request, store(), process.env.CRON_SECRET);
}
