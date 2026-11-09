# Verification record

Checked on 9 November 2026 using Python 3.12 on Windows.

## Automated test suite

Command: `.venv\Scripts\python.exe -m pytest -q`

Result at the implementation checkpoint: **41 passed**. Coverage includes:

- Exact source HTML, names, whitespace, Unicode, escaped entities, multiline and quoted CSV cells.
- Actual binary XLSX parsing, multiple sheets, preambles, additional settings and unmapped-sheet evidence.
- Hierarchy continuation warnings, orphan rejection, explicit order, stable ties and repeated section occurrences.
- Missing headers, duplicate aliases, unsupported extensions, corrupt workbooks, expanded-archive limits and formulas.
- Script/active-markup isolation, link protocol restrictions, retained safe formatting and inactive external images.
- Preview before commit, mandatory warning acknowledgement and idempotent commits.
- Section/item/comment changes and independently edited copies, with fresh IDs throughout.
- Retrieval through a new application instance and database connection using the persisted browser session.
- Workspace ownership, cross-origin writes, CSRF checks, stale revision conflicts and atomic invalid edit batches.
- Malformed JSON and invalid edit targets returning controlled failures.
- An audit detecting deliberate database ordering corruption.

JavaScript syntax: `node --check public/static/app.js` passed.

## Real HTTP checks

Command: `.venv\Scripts\python.exe scripts/http_smoke.py --output docs/http-smoke-results.json`

Result: **15 passed, 0 failed** against the running local server and SQLite database. These checks separately fetched the actual application page/assets, opened a fresh sample workspace, copied and edited a template, retrieved the saved data, verified the original was unchanged, checked source evidence, uploaded/committed the adversarial fixture, and confirmed a bad import did not modify the library. The JSON result is retained alongside this file.

## Verification not performed

- Browser rendering, accessibility navigation and interactive file chooser: browser automation was unavailable and native app access timed out. HTML/CSS/JavaScript were reviewed, but visual quality is not verified by an actual browser screenshot.
- Genuine Spectora export: none was supplied or obtained from an authenticated trial. Generated XLSX tests and synthetic CSV examples are explicitly not presented as genuine exports.
- Real legacy XLS parsing: code path exists but no genuine XLS fixture was exercised.
- PostgreSQL/Supabase runtime: no connected database was available. Database SQL portability and transaction code were reviewed; PostgreSQL behavior remains unverified.
- Vercel build and public deployment: configuration was checked against Vercel's official Flask documentation; no deployment was created.
- Hands-on Hive trial and published sample report: no authenticated trial session was available.

The code and local behavior are delivered. The unverified external requirements remain necessary before a final assessment submission.
