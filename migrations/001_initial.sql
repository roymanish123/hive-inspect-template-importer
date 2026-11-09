CREATE TABLE IF NOT EXISTS workspaces (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS imports (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id),
    filename TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    source_base64 TEXT NOT NULL,
    parsed_json TEXT NOT NULL,
    report_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    committed_template_id TEXT
);
CREATE INDEX IF NOT EXISTS imports_workspace ON imports(workspace_id);
CREATE TABLE IF NOT EXISTS templates (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id),
    import_id TEXT NOT NULL REFERENCES imports(id),
    name TEXT NOT NULL,
    copied_from TEXT,
    revision INTEGER NOT NULL DEFAULT 1 CHECK(revision > 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS templates_workspace ON templates(workspace_id);
CREATE TABLE IF NOT EXISTS sections (
    id TEXT PRIMARY KEY,
    template_id TEXT NOT NULL REFERENCES templates(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    position INTEGER NOT NULL,
    source_sheet TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    UNIQUE(template_id, position)
);
CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY,
    section_id TEXT NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    position INTEGER NOT NULL,
    source_sheet TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    UNIQUE(section_id, position)
);
CREATE TABLE IF NOT EXISTS comments (
    id TEXT PRIMARY KEY,
    item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    html TEXT NOT NULL,
    original_html TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    position INTEGER NOT NULL,
    source_sheet TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    UNIQUE(item_id, position)
);
CREATE TABLE IF NOT EXISTS source_rows (
    import_id TEXT NOT NULL REFERENCES imports(id),
    source_sheet TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    status TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    PRIMARY KEY(import_id, source_sheet, source_row)
);
CREATE TABLE IF NOT EXISTS edit_events (
    id TEXT PRIMARY KEY,
    template_id TEXT NOT NULL REFERENCES templates(id),
    revision INTEGER NOT NULL,
    changes_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
