// `POST /api/v1/report` — the one thing the collector accepts. Other methods
// are not exported, so Vercel answers them itself.

import { receive } from "../../collector.js";
import { store } from "../../store.js";

export function POST(request) {
  return receive(request, store());
}
