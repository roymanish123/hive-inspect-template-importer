# Implementation notes

## What is implemented

The app imports HTML-text spreadsheets into editable templates, sections, items and comments. It supports section/item renames, comment names and HTML edits, explicit save, independent copies and real database persistence. A new workspace is seeded through the same importer used for uploads. The local seed contains 8 sections and 34 comments.

The selected improvement is **trust before commitment**. A company with years of tailored wording needs evidence that migration did not silently erase its work. Before import, the app shows counts, hierarchy, row accounting and specific warnings. After import, immutable source rows and exact upload bytes remain downloadable, and an independent audit checks checksum, original HTML, hierarchy and order. The improvement addresses migration confidence rather than expanding into unrelated inspection features.

## Data model and preservation

`workspaces` scopes sample sessions. `imports` retains the original file bytes, checksum, initial parsed snapshot and report. `source_rows` retains individual source values and their mapping status. `templates → sections → items → comments` forms the editable normalized hierarchy. Each child has a position and source worksheet/row. `comments.original_html` remains separate from editable `comments.html`. `edit_events` records saved patches with their revisions. PostgreSQL tables use the private `hive_workshop` schema, which must remain outside the default Supabase Data API exposure.

Copies insert a fresh template and every editable child in one transaction. They share only immutable original import evidence. Template revisions are independent. Save uses an atomic revision compare-and-increment; an invalid change batch is rejected before mutation. PostgreSQL copies lock the parent template, while SQLite reserves the write transaction. Import commits are idempotent and lock the preview record so double-clicks do not create duplicate templates.

Import mapping never asks a model to rewrite text or infer new sections. Names and comment strings are retained without trimming. Complete explicit numeric order controls comment order, with stable ties; incomplete order uses physical source order and a warning. Separate repeated occurrences stay separate instead of being silently merged. Source-only rows and unknown columns are retained and reported. The original binary file is the final preservation reference for workbook objects and annotations.

## Rich content

Original comment HTML is stored verbatim. Safe display is derived separately using Bleach, an allowlist of common text/table/image tags, safe link protocols and a restricted CSS property set. It is rendered inside a sandboxed frame. Unsupported tags, active attributes, unsafe/relative URLs, unsupported CSS and workbook objects produce review notes. Safe links retain destinations and open with opener isolation. External image URLs are preserved but do not load until explicitly selected; images are not downloaded or rehosted.

The preview is not a reproduction of Spectora's report renderer. Embedded active elements, arbitrary styles, source-specific widgets, spreadsheet formulas and answer-control behavior are outside the display/editor scope. Sanitization changes the preview only, never the original source. Text, entities and punctuation remain exact in the stored HTML; a browser may render equivalent HTML differently.

There are two separate kinds of limitation: (1) information absent from a file cannot be reconstructed, such as formatting excluded by a plain-text export or a remote asset that is no longer available; (2) information present but unsupported is retained as original bytes/cells/metadata and explicitly reported. The app does not label every missing field as a source-system defect.

## What was deliberately cut

- Report authoring, scheduling, payments and customer portals: excluded by the assessment's scope.
- AI mapping inside the product: a documented spreadsheet schema benefits from deterministic mapping and exact comparisons. There are no model credentials or runtime model costs.
- Arbitrary header guessing: narrow explicit aliases fail honestly when the schema changes.
- Rich visual editing, drag reordering, adding/removing hierarchy nodes and round-trip Spectora import export: they increase the chance of rewriting source markup and require additional behavior tests. The baseline editor exposes exact HTML with a safe formatted preview.
- Production accounts, cross-device recovery and team collaboration: the assessment uses per-browser sample workspaces. Clearing cookies loses the workspace capability; database records remain. This must be replaced with real authentication before importing customer information.
- Large/asynchronous migration jobs and cloud file storage: this synchronous assessment app has a 3 MB upload limit and retains sources in the database. Larger jobs should move to durable object storage and a background queue.
- Full answer types, default settings, severity behavior and remote assets: retained as source metadata rather than pretending to implement inspection/report semantics.

## Verification and honest limits

Automated checks pass locally; exact results are recorded in `docs/VERIFICATION.md` and `docs/http-smoke-results.json`. Tests use SQLite and generated binary XLSX fixtures, including an independent adversarial template. They prove persistence across new application instances, save/retrieve behavior, unchanged originals after copy edits, explicit import failures, and corruption detection. JavaScript syntax is checked with Node. A real HTTP smoke test separately exercises the running server.

Browser automation could not access a usable browser session: browser access was unavailable, and native app access timed out. No visual or interactive browser test is claimed. PostgreSQL pooler behavior, Vercel packaging and live performance need verification in the target deployment. XLS support is implemented with xlrd, but a genuine legacy XLS export has not been tested. Published spreadsheet columns are not a substitute for a genuine export from a Spectora trial.

## Required external work still outstanding

This implementation is **not yet a submission-complete assessment**. No authenticated Hive/Spectora trial was available. The required hands-on Hive inspection and published sample report, actual template-import experience, and Spectora template selection/export were not performed. The seed is clearly synthetic; its provenance is documented. Optional Binsr exploration was omitted to focus implementation time on the required migration baseline, and no firsthand comparison is claimed.

A real Spectora HTML-text export must be added with its template name, origin and checksum, then validated and imported in the live deployment. A Vercel URL backed by PostgreSQL and a hosted repository with reviewer access are still needed. The implementation includes local development commits; no remote repository or public deployment was fabricated. Product research is documentation-based and labeled accordingly in `docs/PRODUCT_RESEARCH.md`.

## Approximate effort and contribution

Approximately 1.5–2 hours of assisted implementation, research, setup and automated checking in this session; this is an estimate, not a timesheet. It excludes the outstanding product trials, authentic-export validation and deployment. The implementation, UI, schema, importer, source evidence and tests were authored here with AI coding assistance. No existing application starter was used.

Libraries: Flask/Werkzeug/Jinja for HTTP and sessions, openpyxl for XLSX reading, xlrd for XLS reading, Bleach/tinycss2 for HTML/CSS sanitization, defusedxml for safe XML handling, psycopg for PostgreSQL and pytest for testing. SQLite, CSV, hashing and JSON use Python's standard library. Dependencies are pinned in the requirements files.

Primary references:

- [Spectora export process](https://support.spectora.com/en/articles/2769896-how-to-export-a-template)
- [Spectora columns and comment ordering](https://support.spectora.com/en/articles/6198400-how-to-import-a-template-from-a-spreadsheet)
- [Hive documentation index](https://docs.hiveinspect.com/llms.txt)
- [Vercel Flask deployment and public assets](https://vercel.com/docs/frameworks/backend/flask)
