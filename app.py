"""Flask WSGI entry point; Vercel discovers the module-level app."""
import base64
import hashlib
import io
import json
import os
import secrets
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, jsonify, request, send_file, session
from werkzeug.exceptions import HTTPException
from werkzeug.utils import secure_filename

from hive_importer.db import Database, ROOT, get_template, insert_import, insert_tree, now, uid
from hive_importer.importer import ImportFailure, MAX_BYTES, parse_export
from hive_importer.rich_text import render_html


def load_env():
    file = ROOT / ".env"
    if file.exists():
        for line in file.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def create_app(config=None):
    load_env()
    app = Flask(__name__, static_folder="public/static", static_url_path="/static")
    production = bool(os.getenv("VERCEL"))
    secret = os.getenv("APP_SECRET", "")
    if not secret and not production and not config:
        (ROOT / ".data").mkdir(exist_ok=True)
        secret_file = ROOT / ".data" / "session-secret"
        if not secret_file.exists():
            try:
                with secret_file.open("x") as file:
                    file.write(secrets.token_hex(32))
            except FileExistsError:
                pass
        secret = secret_file.read_text()
    app.config.update(SECRET_KEY=secret, MAX_CONTENT_LENGTH=MAX_BYTES + 100000, SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_SECURE=production or os.getenv("COOKIE_SECURE") == "1",
        PERMANENT_SESSION_LIFETIME=timedelta(days=365), SEED_DEMO=True, DATABASE_URL=os.getenv("DATABASE_URL", ""))
    if config:
        app.config.update(config)
    if production and (len(app.config["SECRET_KEY"] or "") < 32 or not app.config["DATABASE_URL"]):
        raise RuntimeError("Vercel requires DATABASE_URL (persistent PostgreSQL) and APP_SECRET (32+ characters).")
    db = Database(url=app.config["DATABASE_URL"], sqlite_path=app.config.get("SQLITE_PATH"))
    db.initialize()
    app.extensions["database"] = db

    def fail(message, status=400, **extra):
        return jsonify({"error": message, **extra}), status

    def json_object():
        payload = request.get_json()
        if not isinstance(payload, dict):
            from flask import abort
            abort(400, description="Request body must be a JSON object.")
        return payload

    def workspace():
        if "workspace_id" not in session:
            session["workspace_id"] = uid()
            session["csrf_token"] = secrets.token_urlsafe(32)
            session.permanent = True
        workspace_id = session["workspace_id"]
        with db.connect() as conn:
            created = conn.execute("INSERT INTO workspaces VALUES(?,?) ON CONFLICT(id) DO NOTHING", (workspace_id, now())).rowcount
            if created and app.config["SEED_DEMO"]:
                filename = "residential-demo.html-text.csv"
                data = (ROOT / "examples" / filename).read_bytes()
                parsed = parse_export(data, filename)
                import_id = insert_import(conn, workspace_id, data, filename, parsed)
                template_id = insert_tree(conn, workspace_id, import_id, "Residential inspection · sample", parsed["sections"])
                conn.execute("UPDATE imports SET committed_template_id=? WHERE id=?", (template_id, import_id))
        return workspace_id

    @app.before_request
    def guard():
        if request.path.startswith("/api/") and request.path != "/api/health":
            workspace()
            if request.method not in {"GET", "HEAD", "OPTIONS"}:
                token = request.headers.get("X-CSRF-Token", "")
                if not secrets.compare_digest(token, session["csrf_token"]):
                    return fail("Session expired. Reload the page and try again.", 403)
                origin = request.headers.get("Origin")
                if origin and urlsplit(origin).netloc != request.host:
                    return fail("Cross-origin writes are not allowed.", 403)

    @app.after_request
    def headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' https: http: data:; connect-src 'self'; frame-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(ImportFailure)
    def import_failure(exc):
        return fail(str(exc), 422, issues=exc.issues)

    @app.errorhandler(HTTPException)
    def http_failure(exc):
        return fail("File exceeds the upload limit." if exc.code == 413 else exc.description, exc.code)

    @app.errorhandler(Exception)
    def unexpected_failure(exc):
        if app.testing:
            raise exc
        app.logger.exception("Request failed")
        return fail("The server could not complete this request. Your saved templates are unchanged; retry shortly.", 500)

    @app.get("/")
    def index():
        return send_file(ROOT / "public" / "static" / "index.html")

    @app.get("/api/health")
    def health():
        with db.connect() as conn:
            conn.one("SELECT 1 AS ok")
        return jsonify({"status": "ok", "database": "postgresql" if db.url else "sqlite"})

    @app.get("/api/bootstrap")
    def bootstrap():
        return jsonify({"csrf_token": session["csrf_token"], "storage": "PostgreSQL" if db.url else "SQLite", "workspace": session["workspace_id"],
            "demo_notice": "Private sample workspace for this browser. Keep cookies to reopen your saved work. Use shareable sample material only.", "max_bytes": MAX_BYTES})

    @app.get("/api/templates")
    def list_templates():
        with db.connect() as conn:
            data = conn.all("SELECT id,name,revision,copied_from,created_at,updated_at FROM templates WHERE workspace_id=? ORDER BY created_at,id", (session["workspace_id"],))
        return jsonify(data)

    def template_or_404(conn, template_id):
        template = get_template(conn, session["workspace_id"], template_id)
        if template is None:
            from flask import abort
            abort(404, description="Template not found in this workspace.")
        return template

    @app.get("/api/templates/<template_id>")
    def template_detail(template_id):
        with db.connect() as conn:
            template = template_or_404(conn, template_id)
        for sec in template["sections"]:
            for item in sec["items"]:
                for comment in item["comments"]:
                    comment.update(render_html(comment["html"]))
        return jsonify(template)

    @app.post("/api/imports/preview")
    def preview_import():
        upload = request.files.get("file")
        if upload is None or not upload.filename:
            return fail("Choose an export file first.")
        filename = secure_filename(upload.filename) or "template.xlsx"
        data = upload.read(MAX_BYTES + 1)
        parsed = parse_export(data, filename)
        with db.connect() as conn:
            quota = conn.one("SELECT COUNT(*) AS n FROM imports WHERE workspace_id=?", (session["workspace_id"],))["n"]
            if quota >= 30:
                return fail("This sample workspace has reached its 30-upload limit.", 429)
            import_id = insert_import(conn, session["workspace_id"], data, filename, parsed)
        return jsonify({"id": import_id, "report": parsed["report"], "sections": parsed["sections"]})

    @app.post("/api/imports/<import_id>/commit")
    def commit_import(import_id):
        payload = json_object()
        name = payload.get("name", "")
        if not isinstance(name, str) or not name.strip() or len(name) > 250:
            return fail("Give the template a name between 1 and 250 characters.")
        with db.connect() as conn:
            # Serializes parallel commits on PostgreSQL; SQLite write reservation below.
            if not conn.postgres:
                conn.execute("BEGIN IMMEDIATE")
            sql = "SELECT * FROM imports WHERE id=? AND workspace_id=?" + (" FOR UPDATE" if conn.postgres else "")
            imported = conn.one(sql, (import_id, session["workspace_id"]))
            if not imported:
                return fail("Import preview not found. Upload the file again.", 404)
            if imported["committed_template_id"]:
                return jsonify({"template_id": imported["committed_template_id"]})
            report = json.loads(imported["report_json"])
            if report["warnings"] and payload.get("acknowledge_warnings") is not True:
                return fail("Review and acknowledge the import warnings before saving.", 422)
            parsed = json.loads(imported["parsed_json"])
            template_id = insert_tree(conn, session["workspace_id"], import_id, name, parsed["sections"])
            conn.execute("UPDATE imports SET committed_template_id=? WHERE id=?", (template_id, import_id))
        return jsonify({"template_id": template_id}), 201

    @app.patch("/api/templates/<template_id>")
    def save_edits(template_id):
        payload = json_object()
        changes = payload.get("changes")
        revision = payload.get("revision")
        if type(revision) is not int or not isinstance(changes, list) or not 1 <= len(changes) <= 500:
            return fail("Provide the current revision and between 1 and 500 changes.")
        with db.connect() as conn:
            template = template_or_404(conn, template_id)
            allowed = {("template", template_id): ("templates", {"name"})}
            for s in template["sections"]:
                allowed[("section", s["id"])] = ("sections", {"name"})
                for i in s["items"]:
                    allowed[("item", i["id"])] = ("items", {"name"})
                    for c in i["comments"]:
                        allowed[("comment", c["id"])] = ("comments", {"name", "html"})
            validated = []
            for change in changes:
                if not isinstance(change, dict):
                    return fail("Invalid edit.")
                if not all(isinstance(change.get(key), str) for key in ("entity", "id", "field")):
                    return fail("Edit entity, id and field must be strings.")
                target = allowed.get((change.get("entity"), change.get("id")))
                field, value = change.get("field"), change.get("value")
                if not target or field not in target[1] or not isinstance(value, str):
                    return fail("Edit targets an unknown field or another template.")
                if len(value) > (200000 if field == "html" else 250):
                    return fail("Edit exceeds the field length limit.")
                if field == "name" and change.get("entity") != "comment" and not value.strip():
                    return fail("Template, section and item names cannot be empty.")
                validated.append((target[0], field, value, change["id"]))
            changed = conn.execute("UPDATE templates SET revision=revision+1,updated_at=? WHERE id=? AND workspace_id=? AND revision=?",
                                   (now(), template_id, session["workspace_id"], revision)).rowcount
            if not changed:
                return fail("This template changed in another tab. Download your unsaved edits, then reload the latest version.", 409)
            for table, field, value, entity_id in validated:
                conn.execute(f"UPDATE {table} SET {field}=? WHERE id=?", (value, entity_id))
            conn.execute("INSERT INTO edit_events VALUES(?,?,?,?,?)", (uid(), template_id, revision + 1, json.dumps(changes, ensure_ascii=False), now()))
        return jsonify({"revision": revision + 1, "saved": True})

    @app.post("/api/templates/<template_id>/copy")
    def copy_template(template_id):
        with db.connect() as conn:
            if not conn.postgres:
                conn.execute("BEGIN IMMEDIATE")
            else:
                conn.execute("SELECT id FROM templates WHERE id=? AND workspace_id=? FOR UPDATE", (template_id, session["workspace_id"]))
            template = template_or_404(conn, template_id)
            count = conn.one("SELECT COUNT(*) AS n FROM templates WHERE workspace_id=?", (session["workspace_id"],))["n"]
            if count >= 60:
                return fail("This sample workspace has reached its 60-template limit.", 429)
            copy_id = insert_tree(conn, session["workspace_id"], template["import_id"], (template["name"] + " (copy)")[:250], template["sections"], template_id)
        return jsonify({"template_id": copy_id}), 201

    @app.get("/api/templates/<template_id>/audit")
    def audit(template_id):
        with db.connect() as conn:
            template = template_or_404(conn, template_id)
            source = conn.one("SELECT * FROM imports WHERE id=?", (template["import_id"],))
            rows = conn.all("SELECT evidence_json FROM source_rows WHERE import_id=? ORDER BY source_sheet,source_row", (template["import_id"],))
        parsed = json.loads(source["parsed_json"])
        expected = {(c["sheet"], c["row"]): c["original_html"] for s in parsed["sections"] for i in s["items"] for c in i["comments"]}
        current = [c for s in template["sections"] for i in s["items"] for c in i["comments"]]
        mismatches = [f"{c['source_sheet']}:{c['source_row']}" for c in current if expected.get((c["source_sheet"], c["source_row"])) != c["original_html"]]
        actual_keys = [(c["source_sheet"], c["source_row"]) for c in current]
        expected_positions = {(s["sheet"], s["row"], i["sheet"], i["row"], c["sheet"], c["row"]): (s["position"], i["position"], c["position"])
            for s in parsed["sections"] for i in s["items"] for c in i["comments"]}
        actual_positions = {(s["source_sheet"], s["source_row"], i["source_sheet"], i["source_row"], c["source_sheet"], c["source_row"]): (s["position"], i["position"], c["position"])
            for s in template["sections"] for i in s["items"] for c in i["comments"]}
        checks = {"source_checksum_matches": hashlib.sha256(base64.b64decode(source["source_base64"])).hexdigest() == source["sha256"],
                  "all_source_rows_accounted_for": len(rows) == template["report"]["counts"]["source_rows"],
                  "original_comment_html_matches": not mismatches and len(actual_keys) == len(expected) and set(actual_keys) == set(expected),
                  "hierarchy_and_order_match": actual_positions == expected_positions and len(template["sections"]) == len(parsed["sections"])
                      and sum(len(s["items"]) for s in template["sections"]) == template["report"]["counts"]["items"]}
        return jsonify({"report": template["report"], "checks": checks, "mismatches": mismatches,
                        "edited_comments": sum(c["html"] != c["original_html"] for c in current), "rows": [json.loads(r["evidence_json"]) for r in rows]})

    @app.get("/api/templates/<template_id>/source")
    def download_source(template_id):
        with db.connect() as conn:
            template = template_or_404(conn, template_id)
            imported = conn.one("SELECT filename,source_base64 FROM imports WHERE id=?", (template["import_id"],))
        return send_file(io.BytesIO(base64.b64decode(imported["source_base64"])), mimetype="application/octet-stream", as_attachment=True, download_name=imported["filename"])

    @app.get("/api/templates/<template_id>/export")
    def export_template(template_id):
        with db.connect() as conn:
            template = template_or_404(conn, template_id)
        return send_file(io.BytesIO(json.dumps(template, ensure_ascii=False, indent=2).encode()), mimetype="application/json", as_attachment=True, download_name=secure_filename(template["name"]) + ".json")

    @app.post("/api/render")
    def render_preview():
        html = json_object().get("html")
        if not isinstance(html, str) or len(html) > 200000:
            return fail("Provide comment HTML within the 200,000 character limit.")
        return jsonify(render_html(html))

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")), debug=False)
