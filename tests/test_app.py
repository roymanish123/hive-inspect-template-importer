import io
import json
from pathlib import Path

import pytest

from app import create_app
from tests.test_importer import HEADERS, csv_bytes, workbook_bytes


@pytest.fixture
def configured(tmp_path):
    config = {"TESTING":True,"SECRET_KEY":"test-secret-not-a-production-credential", "DATABASE_URL":"", "SQLITE_PATH":str(tmp_path/'test.db'),"SEED_DEMO":True}
    return create_app(config), config


def bootstrap(client):
    info = client.get('/api/bootstrap').get_json()
    return {"X-CSRF-Token": info['csrf_token']}


def first(client):
    return client.get('/api/templates/'+client.get('/api/templates').get_json()[0]['id']).get_json()


def comment(template):
    return template['sections'][0]['items'][0]['comments'][0]


def test_seed_open_and_real_database_health(configured):
    app, _ = configured
    with app.test_client() as client:
        bootstrap(client)
        template = first(client)
        assert len(template['sections']) == 8
        assert client.get('/api/health').get_json() == {"status":"ok","database":"sqlite"}
        assert client.get('/').status_code == 200


def test_edits_copies_and_restart_persistence(configured):
    app, config = configured
    client = app.test_client()
    headers = bootstrap(client)
    original = first(client)
    tid = original['id']
    sec, item, c = original['sections'][0], original['sections'][0]['items'][0], comment(original)
    changes = [{"entity":"section","id":sec['id'],"field":"name","value":"Changed roof"},
        {"entity":"item","id":item['id'],"field":"name","value":"Changed item"},
        {"entity":"comment","id":c['id'],"field":"html","value":"<p>Saved edit, café.</p>"}]
    assert client.patch('/api/templates/'+tid,json={"revision":1,"changes":changes},headers=headers).status_code == 200
    copied_id = client.post(f'/api/templates/{tid}/copy',json={},headers=headers).get_json()['template_id']
    copied = client.get('/api/templates/'+copied_id).get_json()
    assert copied['sections'][0]['name'] == 'Changed roof'
    assert copied['sections'][0]['id'] != sec['id'] and comment(copied)['id'] != c['id']
    assert comment(copied)['html'] == '<p>Saved edit, café.</p>'
    changed = client.patch('/api/templates/'+copied_id,json={"revision":1,"changes":[{"entity":"comment","id":comment(copied)['id'],"field":"html","value":"Copy only"}]},headers=headers)
    assert changed.status_code == 200
    assert comment(client.get('/api/templates/'+tid).get_json())['html'] == '<p>Saved edit, café.</p>'
    # New application instance, new DB connection, same durable database and browser cookie.
    cookie = client.get_cookie('session')
    reopened = create_app(config).test_client()
    reopened.set_cookie('session',cookie.value)
    assert comment(reopened.get('/api/templates/'+copied_id).get_json())['html'] == 'Copy only'
    assert comment(reopened.get('/api/templates/'+tid).get_json())['original_html'] == c['original_html']
    audit = reopened.get(f'/api/templates/{copied_id}/audit').get_json()
    assert all(audit['checks'].values()) and audit['edited_comments'] == 1


def test_optimistic_lock_rejects_stale_tab_without_overwriting(configured):
    app,_ = configured
    client = app.test_client(); headers=bootstrap(client); t=first(client)
    url='/api/templates/'+t['id']
    payload={"revision":1,"changes":[{"entity":"template","id":t['id'],"field":"name","value":"Tab one"}]}
    assert client.patch(url,json=payload,headers=headers).status_code == 200
    payload['changes'][0]['value']='Stale tab'
    assert client.patch(url,json=payload,headers=headers).status_code == 409
    assert client.get(url).get_json()['name'] == 'Tab one'


def test_workspace_isolation_and_csrf(configured):
    app,_=configured
    one,two=app.test_client(),app.test_client()
    bootstrap(one); headers=bootstrap(two); t=first(one)
    assert two.get('/api/templates/'+t['id']).status_code == 404
    for route in ['source','export','audit']:
        assert two.get(f"/api/templates/{t['id']}/{route}").status_code == 404
    assert two.post(f"/api/templates/{t['id']}/copy",json={},headers=headers).status_code == 404
    assert one.post('/api/render',json={'html':'hello'}).status_code == 403
    assert two.post('/api/render',json={'html':'hello'},headers={**headers,'Origin':'https://hostile.example'}).status_code == 403


def test_real_xlsx_preview_commit_ack_and_idempotency(configured):
    app,_=configured
    client=app.test_client();headers=bootstrap(client)
    html='<p><b>Exact</b> &amp; <a href="https://example.com">link</a></p>'
    data=workbook_bytes({'Residential':[HEADERS+['Custom Field'],['Roof','Shingles','Wear',html,'keep me']]})
    before=len(client.get('/api/templates').get_json())
    response=client.post('/api/imports/preview',data={'file':(io.BytesIO(data),'actual-format.xlsx')},headers=headers)
    assert response.status_code == 200
    preview=response.get_json(); url='/api/imports/'+preview['id']+'/commit'
    assert len(client.get('/api/templates').get_json()) == before
    assert client.post(url,json={'name':'New'},headers=headers).status_code == 422
    response=client.post(url,json={'name':'New','acknowledge_warnings':True},headers=headers)
    assert response.status_code == 201
    tid=response.get_json()['template_id']
    assert client.post(url,json={'name':'New','acknowledge_warnings':True},headers=headers).get_json()['template_id']==tid
    assert len(client.get('/api/templates').get_json()) == before+1
    actual=client.get('/api/templates/'+tid).get_json()
    assert comment(actual)['html']==html and comment(actual)['metadata']['Custom Field']=='keep me'
    assert client.get(f'/api/templates/{tid}/source').data == data
    assert all(client.get(f'/api/templates/{tid}/audit').get_json()['checks'].values())


def test_failure_does_not_create_partial_template_or_import(configured):
    app,_=configured
    client=app.test_client();headers=bootstrap(client)
    before=client.get('/api/templates').get_json()
    bad=csv_bytes([HEADERS,['Roof','One','Valid','Good'],['Other','','Orphan','Bad']])
    response=client.post('/api/imports/preview',data={'file':(io.BytesIO(bad),'bad.csv')},headers=headers)
    assert response.status_code == 422 and response.get_json()['issues']
    assert client.get('/api/templates').get_json()==before
    with app.extensions['database'].connect() as conn:
        assert conn.one('SELECT COUNT(*) AS n FROM imports')['n']==1 # Seed only.


def test_invalid_bulk_edit_is_atomic_and_foreign_ids_rejected(configured):
    app,_=configured
    client=app.test_client();headers=bootstrap(client);t=first(client)
    cid=client.post(f"/api/templates/{t['id']}/copy",json={},headers=headers).get_json()['template_id']
    copied=client.get('/api/templates/'+cid).get_json()
    response=client.patch('/api/templates/'+t['id'],json={'revision':1,'changes':[
        {'entity':'template','id':t['id'],'field':'name','value':'Should rollback'},
        {'entity':'comment','id':comment(copied)['id'],'field':'html','value':'Other template'}]},headers=headers)
    assert response.status_code==400
    unchanged=client.get('/api/templates/'+t['id']).get_json()
    assert unchanged['name']==t['name'] and unchanged['revision']==1


def test_api_rejects_over_limit_body(configured):
    app,_=configured;client=app.test_client();headers=bootstrap(client)
    response=client.post('/api/imports/preview',data={'file':(io.BytesIO(b'x'*(3*1024*1024+1)),'big.csv')},headers=headers)
    assert response.status_code==422


def test_export_is_structured_and_provenance_immutable(configured):
    app,_=configured;client=app.test_client();bootstrap(client);t=first(client)
    data=json.loads(client.get(f"/api/templates/{t['id']}/export").data)
    assert data['sections'][0]['items'][0]['comments'][0]['original_html']
    assert client.get('/api/templates').headers['Cache-Control']=='no-store'
    assert 'frame-ancestors' in client.get('/').headers['Content-Security-Policy']


@pytest.mark.parametrize('payload', [[], None, 'invalid', 42])
def test_malformed_json_returns_actionable_failure(configured, payload):
    app,_=configured;client=app.test_client();headers=bootstrap(client)
    response=client.post('/api/render',data=json.dumps(payload),content_type='application/json',headers=headers)
    assert response.status_code==400 and 'JSON object' in response.get_json()['error']


def test_unhashable_edit_target_does_not_crash(configured):
    app,_=configured;client=app.test_client();headers=bootstrap(client);t=first(client)
    response=client.patch('/api/templates/'+t['id'],json={'revision':1,'changes':[{'entity':[], 'id':{}, 'field':'name','value':'bad'}]},headers=headers)
    assert response.status_code==400
    assert client.get('/api/templates/'+t['id']).get_json()['revision']==1


def test_audit_detects_order_corruption(configured):
    app,_=configured;client=app.test_client();bootstrap(client);t=first(client)
    with app.extensions['database'].connect() as conn:
        conn.execute('UPDATE comments SET position=100 WHERE id=?',(comment(t)['id'],))
    result=client.get(f"/api/templates/{t['id']}/audit").get_json()
    assert result['checks']['hierarchy_and_order_match'] is False
