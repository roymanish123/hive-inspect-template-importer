"""Exercise the running HTTP server with a fresh cookie jar and sample-only data."""
import argparse
import http.cookiejar
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

parser = argparse.ArgumentParser()
parser.add_argument("--base-url", default="http://127.0.0.1:5000")
parser.add_argument("--output", type=Path)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
checks = []
csrf = ""


def request(path, method="GET", body=None, content_type="application/json"):
    headers = {"X-CSRF-Token": csrf}
    if isinstance(body, dict):
        body = json.dumps(body).encode()
    if body is not None:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(args.base_url.rstrip("/") + path, data=body, method=method, headers=headers)
    try:
        with client.open(req, timeout=30) as response:
            data = response.read()
            return response.status, json.loads(data) if "application/json" in response.headers.get("Content-Type", "") else data
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def check(name, condition):
    if not condition:
        raise AssertionError(name)
    checks.append({"check": name, "passed": True})


def upload(filename):
    boundary = "smoke-" + uuid4().hex
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode()
            + (root / "examples" / filename).read_bytes() + f'\r\n--{boundary}--\r\n'.encode())
    return request('/api/imports/preview', 'POST', body, 'multipart/form-data; boundary=' + boundary)


status, health = request('/api/health')
check('Real HTTP health and database connection', status == 200 and health['status'] == 'ok')
status, page = request('/')
check('Application page served', status == 200 and b'Template Workshop' in page)
for asset in ('app.js', 'style.css', 'mark.svg'):
    status, data = request('/static/' + asset)
    check('Static asset served: ' + asset, status == 200 and len(data) > 50)
status, info = request('/api/bootstrap')
csrf = info['csrf_token']
status, templates = request('/api/templates')
check('Fresh browser opens with an imported sample', status == 200 and len(templates) > 0)
original_id = templates[0]['id']
status, original = request('/api/templates/' + original_id)
status, copied = request(f'/api/templates/{original_id}/copy', 'POST', {})
check('Deep copy over HTTP', status == 201 and copied['template_id'] != original_id)
copy_id = copied['template_id']
status, copied = request('/api/templates/' + copy_id)
c = copied['sections'][0]['items'][0]['comments'][0]
edited_html = '<p>HTTP smoke test: independently saved copy.</p>'
status, result = request('/api/templates/' + copy_id, 'PATCH', {'revision':copied['revision'], 'changes':[{'entity':'comment', 'id':c['id'], 'field':'html', 'value':edited_html}]})
check('Edit saved to backend', status == 200)
status, reopened = request('/api/templates/' + copy_id)
check('Edit retrieved in a separate HTTP request', reopened['sections'][0]['items'][0]['comments'][0]['html'] == edited_html)
status, untouched = request('/api/templates/' + original_id)
check('Original unchanged after copy edit', untouched == original)
status, audit = request(f'/api/templates/{copy_id}/audit')
check('Checksum, row accounting, original HTML, hierarchy and order checks', all(audit['checks'].values()))
status, preview = upload('edge-cases.html-text.csv')
check('Second template format previews over multipart upload', status == 200 and preview['report']['counts']['comments'] == 5)
status, committed = request('/api/imports/' + preview['id'] + '/commit', 'POST', {'name':'HTTP test import', 'acknowledge_warnings':True})
check('Reviewed upload committed to database', status == 201)
status, before = request('/api/templates')
status, failure = upload('invalid-missing-parent.csv')
check('Orphan row returns a visible validation failure', status == 422 and bool(failure['issues']))
status, after = request('/api/templates')
check('Failed import leaves saved library unchanged', before == after)
result = {'checked_at_utc': datetime.now(timezone.utc).isoformat(), 'transport':'real HTTP', 'database':health['database'],
          'checks': checks, 'passed':len(checks), 'failed':0, 'browser_visual_check':'Not performed: browser automation unavailable.'}
print(json.dumps(result, indent=2))
if args.output:
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
