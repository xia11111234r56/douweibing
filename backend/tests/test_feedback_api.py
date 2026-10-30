"""识别纠错反馈 API 边界测试。

覆盖：归属权限（本人/他人/管理员/匿名）、upsert 覆盖、匿名可重复提交、
is_correct=false 缺 corrected 422、病害不存在 404、非训练类 400、
识别记录不存在 404、列表归属过滤、导出管理员权限。

运行（backend 目录下）：.venv\\Scripts\\python.exe -m pytest tests/test_feedback_api.py -q
"""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.models import Disease, Recognition, RecognitionFeedback, User  # noqa: E402
from app.services.auth import hash_password  # noqa: E402

client = TestClient(app)


@pytest.fixture(scope="session", autouse=True)
def _init_db():
    """TestClient 非上下文管理器不触发 lifespan，需显式建表。"""
    init_db()


def _token_for(username, password):
    r = client.post(
        "/api/auth/register", json={"username": username, "password": password}
    )
    if r.status_code == 400:  # 已存在则直接登录
        r = client.post(
            "/api/auth/login", json={"username": username, "password": password}
        )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _disease_id(name):
    db = SessionLocal()
    try:
        d = db.query(Disease).filter(Disease.name == name).first()
        return d.id if d else None
    finally:
        db.close()


@pytest.fixture(scope="module")
def users():
    """测试用户：fbowner（记录归属人）/ fbother（他人）/ testadmin（管理员）。"""
    tokens = {}
    for name in ("fbowner", "fbother"):
        tokens[name] = _token_for(name, "test123456")
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
    tokens["admin"] = _token_for("testadmin", "test123456")
    return tokens


@pytest.fixture(scope="module")
def recs(users):
    """插入三条识别记录：owner 一条、匿名两条。"""
    db = SessionLocal()
    try:
        owner = db.query(User).filter(User.username == "fbowner").first()
        r_owner = Recognition(user_id=owner.id, image_path=None)
        r_anon = Recognition(user_id=None, image_path=None)
        r_anon2 = Recognition(user_id=None, image_path=None)
        db.add_all([r_owner, r_anon, r_anon2])
        db.commit()
        for r in (r_owner, r_anon, r_anon2):
            db.refresh(r)
        return {"owner": r_owner.id, "anon": r_anon.id, "anon2": r_anon2.id}
    finally:
        db.close()


def test_owner_feedback_ok(users, recs):
    """记录归属人反馈正确 → 200。"""
    r = client.post(
        f"/api/recognitions/{recs['owner']}/feedback",
        json={"is_correct": True, "remark": "正确"},
        headers={"Authorization": f"Bearer {users['fbowner']}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["recognition_id"] == recs["owner"]
    assert body["is_correct"] is True
    assert body["corrected_disease_id"] is None


def test_owner_upsert_overwrites(users, recs):
    """同 (recognition, user) 二次提交 → 覆盖更新为一行。"""
    yunyid = _disease_id("晕疫病")
    assert yunyid is not None
    h = {"Authorization": f"Bearer {users['fbowner']}"}
    r1 = client.post(
        f"/api/recognitions/{recs['owner']}/feedback",
        json={"is_correct": False, "corrected_disease_id": yunyid},
        headers=h,
    )
    assert r1.status_code == 200, r1.text
    r2 = client.post(
        f"/api/recognitions/{recs['owner']}/feedback",
        json={"is_correct": True, "remark": "修正"},
        headers=h,
    )
    assert r2.status_code == 200, r2.text
    db = SessionLocal()
    try:
        rows = (
            db.query(RecognitionFeedback)
            .filter(RecognitionFeedback.recognition_id == recs["owner"])
            .all()
        )
        assert len(rows) == 1
        assert rows[0].is_correct is True
        assert rows[0].remark == "修正"
    finally:
        db.close()


def test_other_feedback_forbidden(users, recs):
    """他人反馈非本人记录 → 403。"""
    r = client.post(
        f"/api/recognitions/{recs['owner']}/feedback",
        json={"is_correct": True},
        headers={"Authorization": f"Bearer {users['fbother']}"},
    )
    assert r.status_code == 403


def test_anonymous_feedback_anon_ok(recs):
    """匿名反馈匿名记录 → 200，重复提交各插一行（NULL 不互斥）。"""
    url = f"/api/recognitions/{recs['anon']}/feedback"
    r1 = client.post(url, json={"is_correct": True})
    assert r1.status_code == 200, r1.text
    r2 = client.post(url, json={"is_correct": False, "corrected_disease_id": _disease_id("病毒病")})
    assert r2.status_code == 200, r2.text
    db = SessionLocal()
    try:
        n = (
            db.query(RecognitionFeedback)
            .filter(
                RecognitionFeedback.recognition_id == recs["anon"],
                RecognitionFeedback.user_id.is_(None),
            )
            .count()
        )
        assert n == 2
    finally:
        db.close()


def test_anonymous_feedback_owner_forbidden(recs):
    """匿名反馈登录用户的记录 → 403（防枚举）。"""
    r = client.post(
        f"/api/recognitions/{recs['owner']}/feedback",
        json={"is_correct": True},
    )
    assert r.status_code == 403


def test_admin_feedback_anon_ok(users, recs):
    """管理员可反馈任意记录。"""
    r = client.post(
        f"/api/recognitions/{recs['anon2']}/feedback",
        json={"is_correct": True},
        headers={"Authorization": f"Bearer {users['admin']}"},
    )
    assert r.status_code == 200, r.text


def test_missing_corrected_422(users, recs):
    """is_correct=false 且缺 corrected_disease_id → 422。"""
    r = client.post(
        f"/api/recognitions/{recs['anon2']}/feedback",
        json={"is_correct": False},
        headers={"Authorization": f"Bearer {users['admin']}"},
    )
    assert r.status_code == 422


def test_nonexistent_disease_404(users, recs):
    """corrected_disease_id 不存在 → 404。"""
    r = client.post(
        f"/api/recognitions/{recs['anon2']}/feedback",
        json={"is_correct": False, "corrected_disease_id": 999999},
        headers={"Authorization": f"Bearer {users['admin']}"},
    )
    assert r.status_code == 404


def test_non_trainable_disease_400(users, recs):
    """corrected 指向不在 10 类白名单的病害 → 400（防 labels 漂移）。"""
    db = SessionLocal()
    try:
        tmp = Disease(name="非训练类测试病", disease_type="生理性", host_id=1)
        db.add(tmp)
        db.commit()
        db.refresh(tmp)
        tmp_id = tmp.id
    finally:
        db.close()
    try:
        r = client.post(
            f"/api/recognitions/{recs['anon2']}/feedback",
            json={"is_correct": False, "corrected_disease_id": tmp_id},
            headers={"Authorization": f"Bearer {users['admin']}"},
        )
        assert r.status_code == 400
        assert "不在可训练分类内" in r.json()["detail"]
    finally:
        db2 = SessionLocal()
        try:
            db2.query(Disease).filter(Disease.id == tmp_id).delete()
            db2.commit()
        finally:
            db2.close()


def test_corrected_severity_invalid(users, recs):
    """corrected_severity 非法取值（非 轻/中/重）→ 422。"""
    vid = _disease_id("病毒病")
    assert vid is not None
    r = client.post(
        f"/api/recognitions/{recs['anon2']}/feedback",
        json={
            "is_correct": False,
            "corrected_disease_id": vid,
            "corrected_severity": "极重",
        },
        headers={"Authorization": f"Bearer {users['admin']}"},
    )
    assert r.status_code == 422


def test_corrected_severity_stored(users):
    """非健康病害 + 严重度 → 200 且落库。"""
    db = SessionLocal()
    try:
        fresh = Recognition(user_id=None, image_path=None)
        db.add(fresh)
        db.commit()
        db.refresh(fresh)
        rid = fresh.id
    finally:
        db.close()
    vid = _disease_id("病毒病")
    assert vid is not None
    r = client.post(
        f"/api/recognitions/{rid}/feedback",
        json={
            "is_correct": False,
            "corrected_disease_id": vid,
            "corrected_severity": "重度",
        },
        headers={"Authorization": f"Bearer {users['admin']}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["corrected_severity"] == "重度"
    db = SessionLocal()
    try:
        fb = (
            db.query(RecognitionFeedback)
            .filter(RecognitionFeedback.recognition_id == rid)
            .first()
        )
        assert fb.corrected_severity == "重度"
    finally:
        db.close()


def test_healthy_clears_severity(users):
    """纠正为健康 → 严重度强制置空（健康 = 无病害）。"""
    db = SessionLocal()
    try:
        fresh = Recognition(user_id=None, image_path=None)
        db.add(fresh)
        db.commit()
        db.refresh(fresh)
        rid = fresh.id
    finally:
        db.close()
    hid = _disease_id("健康")
    assert hid is not None
    r = client.post(
        f"/api/recognitions/{rid}/feedback",
        json={
            "is_correct": False,
            "corrected_disease_id": hid,
            "corrected_severity": "中度",
        },
        headers={"Authorization": f"Bearer {users['admin']}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["corrected_severity"] is None
    db = SessionLocal()
    try:
        fb = (
            db.query(RecognitionFeedback)
            .filter(RecognitionFeedback.recognition_id == rid)
            .first()
        )
        assert fb.corrected_severity is None
    finally:
        db.close()


def test_nonexistent_recognition_404(users):
    """recognition_id 不存在 → 404。"""
    r = client.post(
        "/api/recognitions/999999/feedback",
        json={"is_correct": True},
        headers={"Authorization": f"Bearer {users['admin']}"},
    )
    assert r.status_code == 404


def test_list_feedback_own_only(users):
    """GET /api/feedback：无 token 401；普通用户仅本人相关；管理员可看全部。"""
    assert client.get("/api/feedback").status_code == 401
    r = client.get(
        "/api/feedback", headers={"Authorization": f"Bearer {users['fbother']}"}
    )
    assert r.status_code == 200
    # fbother 没有反馈记录且不是 admin，其可见总数为 0
    assert r.json()["total"] == 0
    r = client.get(
        "/api/feedback", headers={"Authorization": f"Bearer {users['admin']}"}
    )
    assert r.status_code == 200
    assert r.json()["total"] >= 1


def test_list_recognitions_has_feedback(users):
    """识别记录列表 has_feedback：反馈前 false，反馈后 true（批量查询正确）。"""
    db = SessionLocal()
    try:
        fresh = Recognition(user_id=None, image_path=None)
        db.add(fresh)
        db.commit()
        db.refresh(fresh)
        fresh_id = fresh.id
    finally:
        db.close()
    h = {"Authorization": f"Bearer {users['admin']}"}

    # 无反馈 → has_feedback=False
    r = client.get("/api/recognitions", params={"page_size": 100}, headers=h)
    assert r.status_code == 200, r.text
    by_id = {it["id"]: it for it in r.json()["items"]}
    assert fresh_id in by_id
    assert by_id[fresh_id]["has_feedback"] is False

    # 反馈后 → has_feedback=True
    r = client.post(
        f"/api/recognitions/{fresh_id}/feedback",
        json={"is_correct": True},
        headers=h,
    )
    assert r.status_code == 200, r.text
    r = client.get("/api/recognitions", params={"page_size": 100}, headers=h)
    by_id = {it["id"]: it for it in r.json()["items"]}
    assert by_id[fresh_id]["has_feedback"] is True


def test_list_recognitions_filter_feedback(users):
    """纠错状态筛选 + corrected_count：true 只含已纠错，false 只含未纠错。"""
    db = SessionLocal()
    try:
        r1 = Recognition(user_id=None, image_path=None)  # 将纠错
        r2 = Recognition(user_id=None, image_path=None)  # 不纠错
        db.add_all([r1, r2])
        db.commit()
        db.refresh(r1)
        db.refresh(r2)
        corr_id, uncorr_id = r1.id, r2.id
    finally:
        db.close()
    h = {"Authorization": f"Bearer {users['admin']}"}

    # 先给 r1 反馈
    r = client.post(
        f"/api/recognitions/{corr_id}/feedback",
        json={"is_correct": True},
        headers=h,
    )
    assert r.status_code == 200, r.text

    # 无筛选：两条都在，逐行标记正确
    r = client.get("/api/recognitions", params={"page_size": 100}, headers=h)
    assert r.status_code == 200, r.text
    data = r.json()
    by_id = {it["id"]: it for it in data["items"]}
    assert by_id[corr_id]["has_feedback"] is True
    assert by_id[uncorr_id]["has_feedback"] is False
    assert data["corrected_count"] >= 1

    # 筛选 已纠错=true → 只含 corr_id
    r = client.get(
        "/api/recognitions",
        params={"page_size": 100, "has_feedback": "true"},
        headers=h,
    )
    assert r.status_code == 200, r.text
    ids = {it["id"] for it in r.json()["items"]}
    assert corr_id in ids and uncorr_id not in ids

    # 筛选 未纠错=false → 只含 uncorr_id，corrected_count=0
    r = client.get(
        "/api/recognitions",
        params={"page_size": 100, "has_feedback": "false"},
        headers=h,
    )
    assert r.status_code == 200, r.text
    ids = {it["id"] for it in r.json()["items"]}
    assert uncorr_id in ids and corr_id not in ids
    assert r.json()["corrected_count"] == 0


def test_export_admin_only(users):
    """导出：非 admin 403；admin 200 且含 BOM + 表头 + 数据行。"""
    r = client.get(
        "/api/feedback/export",
        headers={"Authorization": f"Bearer {users['fbowner']}"},
    )
    assert r.status_code == 403
    r = client.get(
        "/api/feedback/export",
        headers={"Authorization": f"Bearer {users['admin']}"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    body = r.content.decode("utf-8")
    assert body.startswith("﻿")  # BOM
    assert "recognition_id,image_path,predicted_class,corrected_class" in body
    assert "病毒病" in body  # 匿名重复反馈里 correction 为病毒病，应进入 CSV
