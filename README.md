# Template Workshop

A working desktop web app for importing inspection templates, reviewing preservation evidence, editing their contents and making independent copies.

**Implementation status:** local app and SQLite persistence are verified. Vercel/PostgreSQL deployment, a genuine Spectora account export and hands-on product trials remain outstanding. The included seed is explicitly synthetic. See `NOTES.md` and `examples/PROVENANCE.md` before treating this as a completed submission.

## Run locally

Requires Python 3.12 or newer. No Node build is needed.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe scripts/init_db.py
.\.venv\Scripts\python.exe app.py
```

Open **http://127.0.0.1:5000**. Dependencies have already been installed in this workspace; `START_APP.cmd` also starts the app. If the server is already running, use the existing address.

macOS/Linux equivalents:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python app.py
```

The schema initializes automatically and idempotently. Local data lives in `.data/templates.db`, with a stable local signing secret in `.data/session-secret`. Neither is committed. Browser cookies identify a private sample workspace; the template content is stored in the database. Closing/reopening the app with the same cookies preserves access. A new browser gets its own seeded workspace. No login is required. This is a sample assessment app, not an account system for customer records.

## Use the app

1. The library opens on a sample template with 8 sections and 34 comments.
2. Choose **Import a template** and upload an XLSX, XLS or UTF-8 CSV containing HTML-valued comment cells.
3. Review the hierarchy, row reconciliation and warnings. Acknowledge warnings, name the template, and import.
4. Change a section/item name directly. Select a comment to change its name or HTML text. **Formatted preview** shows sanitized formatting; **Original source** retains the exact initial HTML.
5. Select **Save changes** or press Ctrl+S. The database saves a new revision. Saving from a stale tab returns a conflict instead of overwriting someone else's changes; unsaved edits can be downloaded before reloading.
6. Select **Duplicate template**, then edit and save the copy. Every editable entity has a new ID.
7. **View import evidence** checks the saved source checksum, row accounting, original HTML, hierarchy and order. Download the exact original upload, the current structured JSON, or full evidence.

Try `examples/edge-cases.html-text.csv` for an import containing warnings. Try `examples/invalid-missing-parent.csv` to see an import blocked without adding a partial template.

## Supported input

Required headers are `Section Name`, `Item Name`, `Comment Name`, and `Comment Text`. Header case, surrounding whitespace and documented parenthesized hints are normalized; cell content is not trimmed. Common explicit aliases are in `hive_importer/importer.py`.

Sections and items retain their source occurrence order. Repeated consecutive names identify the same parent. A name that reappears after another parent becomes a new occurrence, preserving ordering without merging unrelated records. Blank hierarchy cells inherit a preceding parent only within the same sheet and section; every inference is reported. Orphan comments are rejected.

Within each item, complete numeric `Order (w/i item)` values control comment order. Ties retain source row order. Missing/invalid order values preserve all comments in their physical row order and produce a warning. Duplicate comments are never deduplicated.

Every nonempty non-header row becomes either a mapped tree row or retained evidence. Non-template sheets and preambles are reported and retained. Additional settings remain in comment metadata and raw cells, with a warning that their behavior is not implemented. Workbook bytes are stored unchanged so source-only features can still be inspected.

Limits: 3 MB upload, 12,000 total worksheet rows, 100 columns, 25 worksheets, 200,000 characters per cell, and 40 MB expanded XLSX archive. XLSX formulas/error cells are blocked. XLS reads cached values and explicitly warns about limited formula/object detection. Plain text cannot restore formatting that was excluded by an earlier export.

## Environment and deployment

Copy `.env.example` to `.env` for local PostgreSQL configuration, or set variables in the host. Do not commit credentials.

- `DATABASE_URL`: PostgreSQL connection URI for deployment. Use the Supabase transaction pooler connection string with TLS (`sslmode=require`); the driver disables prepared statements for pooler compatibility. An empty URL selects local SQLite only.
- `APP_SECRET`: stable random value of at least 32 characters. Generate with `python -c "import secrets; print(secrets.token_hex(32))"` and save it only in hosting settings or the ignored `.env`.
- `COOKIE_SECURE`: `1` when serving HTTPS outside Vercel. Vercel automatically enables secure cookies.
- `PORT`: optional local port; defaults to 5000.

Vercel setup:

1. Create a PostgreSQL database, retain its connection URI privately, and set `DATABASE_URL` and `APP_SECRET` in Vercel for the intended environment.
2. Push this repository to your Git host and import it into Vercel, or run `vercel` / `vercel --prod` from an authenticated CLI. Select Flask; there is no frontend build command or output directory.
3. Python 3.12 is pinned in `.python-version`. `app.py` exports the Flask WSGI app. CDN assets are under `public/static`; SQL and seed files are included in the function configuration.
4. Schema initialization uses `migrations/001_initial.sql`. PostgreSQL tables live in the `hive_workshop` schema, outside Supabase's default exposed `public` schema; do not add it to the Data API's exposed schemas. Cold starts serialize initialization with an advisory lock. The database role needs permission to create this schema and its tables. For a production service, apply migrations using a separate deployment role and reduce runtime privileges.
5. Confirm `/api/health` reports `postgresql`, import the genuine Spectora export, save an edit and independent copy, and reopen the app. Check the public URL in a browser without your Vercel session. If deployment protection is enabled, provide reviewer access or configure the intended public assessment deployment.

On Vercel, startup refuses to fall back to local SQLite or an empty signing secret. Serverless filesystem storage would not provide durable persistence.

Deployment was not performed in this session: Vercel, Supabase and GitHub connections were not authenticated. No public URL or hosted repository is claimed.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/validate_export.py examples/edge-cases.html-text.csv
.\.venv\Scripts\python.exe scripts/http_smoke.py --base-url http://127.0.0.1:5000
```

Tests cover exact HTML/text, hierarchy, ordering, second-template generalization, metadata retention, XLSX uploads, invalid inputs, safe rendering, durable edits across fresh application instances, deep-copy isolation, workspace boundaries, CSRF, stale revision conflicts and atomic failure. Test-only XLSX workbooks are generated in memory; this is not evidence of validating a genuine account export.

## Source layout

- `app.py`: HTTP routes, session isolation, CSRF and application configuration.
- `hive_importer/importer.py`: deterministic workbook parsing, validation and evidence.
- `hive_importer/rich_text.py`: separate safe HTML derivative and rich-content warnings.
- `hive_importer/db.py`: transactional SQLite/PostgreSQL persistence and independent tree copies.
- `migrations/001_initial.sql`: normalized schema.
- `public/static/`: plain JavaScript/CSS interface; no frontend build dependencies.
- `examples/`: seed, adversarial example, failure example and honest provenance.
- `tests/`: preservation and backend integration tests.
- `scripts/`: seed generation, standalone validation, database initialization and HTTP checks.
- `docs/`: implementation decisions, verification evidence and product research.

No starter code was copied. Dependencies and primary documentation are credited in `NOTES.md`.

## Packaged handoff

`output/Hive_Template_Workshop_Solution.zip` contains the tracked source plus `repository-history.bundle` and a readable commit list. It excludes dependencies, local database contents, session secrets, credentials and the supplied assignment PDF. To restore the actual development history from the extracted package, run `git clone repository-history.bundle restored-repository`. The original workspace also retains its `.git` repository.
