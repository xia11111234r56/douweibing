r"""API 集成测试：健康 / 认证 / 病害CRUD / 检索 / 图谱 / 识别（模型未就绪应 503）。

运行（backend 目录下）：.venv\Scripts\python.exe -m pytest tests -q
"""
import base64
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app  # noqa: E402

client = TestClient(app)


def _token_for(username, password):
    """注册（若不存在则登录）并返回 token。"""
    r = client.post("/api/auth/register", json={"username": username, "password": password})
    if r.status_code == 400:  # 已存在则直接登录
        r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def admin_token():
    """注册接口已禁止自封 admin，故直接向库中插入 admin 账号后登录。"""
    from app.db import SessionLocal
    from app.models import User
    from app.services.auth import hash_password

    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.username == "testadmin").first()
        if admin is None:
            db.add(
                User(
                    username="testadmin",
                    password_hash=hash_password("test123456"),
                    role="admin",
                )
            )
            db.commit()
    finally:
        db.close()
    return _token_for("testadmin", "test123456")


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"


def test_login_me(admin_token):
    r = client.get("/api/users/me", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    assert r.json()["username"] == "testadmin"
    assert r.json()["role"] == "admin"


def test_register_forces_user_role():
    """注册接口不得自封 admin：注册返回的 token 角色必须是 user。"""
    token = _token_for("regrole", "test123456")
    r = client.get("/api/users/me", headers={"Authorization": f"Bearer {token}"})
    assert r.json()["role"] == "user"


def test_non_admin_write_forbidden():
    """普通用户对病害写操作应 403。"""
    token = _token_for("plainuser", "test123456")
    r = client.post("/api/diseases", json={
        "name": "越权测试", "disease_type": "生理性", "host_id": 1,
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_logs_admin_only():
    """操作日志仅管理员可查。"""
    user_token = _token_for("loguser", "test123456")
    r = client.get("/api/logs", headers={"Authorization": f"Bearer {user_token}"})
    assert r.status_code == 403


def test_diseases_list():
    r = client.get("/api/diseases")
    assert r.status_code == 200
    diseases = r.json()
    assert len(diseases) == 10
    # 晕疫病应有 12 条防治方案（3 严重度 × 4 方法）
    leaf = next(d for d in diseases if d["name"] == "晕疫病")
    assert len(leaf["treatments"]) == 12
    assert leaf["host_name"] == "绿豆"


def test_disease_crud(admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    # 创建
    r = client.post("/api/diseases", json={
        "name": "测试生理性病", "disease_type": "生理性", "host_id": 1,
        "symptoms": "测试症状", "conditions": "测试条件",
    }, headers=headers)
    assert r.status_code == 200, r.text
    new_id = r.json()["id"]
    # 更新
    r = client.put(f"/api/diseases/{new_id}", json={"disease_type": "生理性病害"},
                   headers=headers)
    assert r.status_code == 200
    assert r.json()["disease_type"] == "生理性病害"
    # 删除
    r = client.delete(f"/api/diseases/{new_id}", headers=headers)
    assert r.status_code == 200
    assert client.get(f"/api/diseases/{new_id}").status_code == 404


def test_search():
    # 按类型
    r = client.get("/api/search", params={"disease_type": "真菌性病害"})
    assert r.status_code == 200
    assert len(r.json()) >= 4
    # 按关键词（症状）
    r = client.get("/api/search", params={"keyword": "黄色晕圈"})
    assert r.status_code == 200
    assert any("晕疫病" in d["name"] for d in r.json())
    # 按严重度（有该等级防治方案的病害）
    r = client.get("/api/search", params={"severity": "重度"})
    assert r.status_code == 200
    assert len(r.json()) >= 6


def test_graph():
    r = client.get("/api/graph")
    assert r.status_code == 200
    body = r.json()
    assert len(body["nodes"]) > 10
    assert len(body["edges"]) > 10
    labels = {n["label"] for n in body["nodes"]}
    assert {"病害", "寄主", "症状", "药剂", "环境"} <= labels


def test_recognize_model_not_ready():
    """模型未就绪时返回 503；模型已导出时做真实推理（返回病害+严重度+防治）。"""
    if not Path(__file__).resolve().parent.parent.joinpath(
        "models", "classifier.onnx"
    ).exists():
        r = client.post("/api/recognize", json={
            "image_base64": base64.b64encode(_tiny_png()).decode(),
            "env": {"growth_stage": "结荚期", "weather": "高温高湿"},
        })
        assert r.status_code == 503
        assert "模型未就绪" in r.json()["detail"]
        return

    # 真实推理：用一张训练集图片
    img_path = Path(__file__).resolve().parent.parent.parent / "ml" / "data" / "organized" / "train" / "晕疫病"
    if img_path.is_dir():
        img = next(img_path.glob("*.JPG"), None) or next(img_path.glob("*.jpg"), None)
    else:
        img = None
    if not img:
        return
    raw = img.read_bytes()
    r = client.post("/api/recognize", json={
        "image_base64": base64.b64encode(raw).decode(),
        "env": {"growth_stage": "结荚期", "weather": "高温高湿"},
    })
    assert r.status_code == 200
    body = r.json()
    assert body["disease_name"]
    assert body["severity"] in ("轻度", "中度", "重度")
    assert len(body["treatments"]) >= 1


def _tiny_png() -> bytes:
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGBgAAAABQAB"
        "h6FO1AAAAABJRU5ErkJggg=="
    )
