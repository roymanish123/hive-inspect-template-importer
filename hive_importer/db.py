"""One transactional repository for SQLite locally and PostgreSQL on Vercel."""
import base64
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def uid():
    return str(uuid4())


def now():
    return datetime.now(timezone.utc).isoformat()


class Connection:
    def __init__(self, raw, postgres=False):
        self.raw, self.postgres = raw, postgres

    def execute(self, sql, args=()):
        return self.raw.execute(sql.replace("?", "%s") if self.postgres else sql, args)

    def one(self, sql, args=()):
        row = self.execute(sql, args).fetchone()
        return dict(row) if row is not None else None

    def all(self, sql, args=()):
        return [dict(row) for row in self.execute(sql, args).fetchall()]


class Database:
    def __init__(self, url=None, sqlite_path=None):
        self.url = url if url is not None else os.getenv("DATABASE_URL", "")
        self.path = Path(sqlite_path or ROOT / ".data" / "templates.db")
        if not self.url:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self):
        if self.url:
            import psycopg
            from psycopg.rows import dict_row
            raw = psycopg.connect(self.url, row_factory=dict_row, connect_timeout=10, prepare_threshold=None)
            # Keep sample workspace data out of Supabase's default exposed public schema.
            raw.execute("SET search_path TO hive_workshop")
        else:
            raw = sqlite3.connect(self.path, timeout=30)
            raw.row_factory = sqlite3.Row
            raw.execute("PRAGMA foreign_keys=ON")
            raw.execute("PRAGMA journal_mode=WAL")
        try:
            yield Connection(raw, bool(self.url))
            raw.commit()
        except Exception:
            raw.rollback()
            raise
        finally:
            raw.close()

    def initialize(self):
        with self.connect() as conn:
            if self.url:
                conn.execute("SELECT pg_advisory_xact_lock(71403211)")
                conn.execute("CREATE SCHEMA IF NOT EXISTS hive_workshop")
            for statement in (ROOT / "migrations" / "001_initial.sql").read_text().split(";"):
                if statement.strip():
                    conn.execute(statement)


def insert_import(conn, workspace, data, filename, parsed):
    import_id = uid()
    report = parsed["report"]
    conn.execute("INSERT INTO imports(id,workspace_id,filename,sha256,source_base64,parsed_json,report_json,created_at) VALUES(?,?,?,?,?,?,?,?)",
        (import_id, workspace, filename, report["sha256"], base64.b64encode(data).decode("ascii"), json.dumps(parsed, ensure_ascii=False), json.dumps(report, ensure_ascii=False), now()))
    for row in parsed["rows"]:
        conn.execute("INSERT INTO source_rows VALUES(?,?,?,?,?)", (import_id, row["sheet"], row["row"], row["status"], json.dumps(row, ensure_ascii=False)))
    return import_id


def insert_tree(conn, workspace, import_id, name, sections, copied_from=None):
    template_id, timestamp = uid(), now()
    conn.execute("INSERT INTO templates(id,workspace_id,import_id,name,copied_from,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                 (template_id, workspace, import_id, name, copied_from, timestamp, timestamp))
    for sec in sections:
        section_id = uid()
        conn.execute("INSERT INTO sections VALUES(?,?,?,?,?,?)", (section_id, template_id, sec["name"], sec["position"], sec.get("sheet", sec.get("source_sheet")), sec.get("row", sec.get("source_row"))))
        for item in sec["items"]:
            item_id = uid()
            conn.execute("INSERT INTO items VALUES(?,?,?,?,?,?)", (item_id, section_id, item["name"], item["position"], item.get("sheet", item.get("source_sheet")), item.get("row", item.get("source_row"))))
            for comment in item["comments"]:
                metadata = comment.get("metadata", {})
                conn.execute("INSERT INTO comments VALUES(?,?,?,?,?,?,?,?,?)", (uid(), item_id, comment["name"], comment["html"], comment["original_html"],
                    json.dumps(metadata, ensure_ascii=False), comment["position"], comment.get("sheet", comment.get("source_sheet")), comment.get("row", comment.get("source_row"))))
    return template_id


def get_template(conn, workspace, template_id):
    template = conn.one("SELECT * FROM templates WHERE id=? AND workspace_id=?", (template_id, workspace))
    if not template:
        return None
    sections = conn.all("SELECT * FROM sections WHERE template_id=? ORDER BY position", (template_id,))
    items = conn.all("SELECT i.* FROM items i JOIN sections s ON i.section_id=s.id WHERE s.template_id=? ORDER BY i.position", (template_id,))
    comments = conn.all("SELECT c.* FROM comments c JOIN items i ON c.item_id=i.id JOIN sections s ON i.section_id=s.id WHERE s.template_id=? ORDER BY c.position", (template_id,))
    sections_by_id = {s["id"]: s for s in sections}
    items_by_id = {i["id"]: i for i in items}
    for section in sections:
        section["items"] = []
    for item in items:
        item["comments"] = []
        sections_by_id[item["section_id"]]["items"].append(item)
    for comment in comments:
        comment["metadata"] = json.loads(comment.pop("metadata_json"))
        items_by_id[comment["item_id"]]["comments"].append(comment)
    template["sections"] = sections
    template["report"] = json.loads(conn.one("SELECT report_json FROM imports WHERE id=?", (template["import_id"],))["report_json"])
    return template
