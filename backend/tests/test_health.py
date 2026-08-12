"""Phase 1 验收测试：/api/health 必须返回规范约定格式。"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_ok():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"code": 0, "message": "success", "data": {"status": "ok"}}


def test_unknown_route_return_unified_error():
    resp = client.get("/api/not-exist")
    assert resp.status_code == 404
    body = resp.json()
    assert body == {"code": 40400, "message": "Not Found", "data": None}