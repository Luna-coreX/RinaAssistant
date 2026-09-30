// The collector's store: Postgres on Neon, over its HTTP driver.
//
// DATABASE_URL is set on the Vercel project by the Neon integration. Each
// call opens nothing that outlives it: the driver sends one HTTP request per
// query, which suits a function that runs once a day per installation.

import { neon } from "@neondatabase/serverless";

export function store() {
  const sql = neon(process.env.DATABASE_URL);
  return {
    keep: (day, install, report) => sql`
      INSERT INTO reports (day, install, report)
      VALUES (${day}, ${install}, ${report}::jsonb)
      ON CONFLICT (install, day) DO NOTHING`,
    dropBefore: (day) => sql`DELETE FROM reports WHERE day < ${day}`,
  };
}
