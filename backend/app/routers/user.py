from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import OperationLog, User
from ..schemas import (
    ChangePassword,
    ResetPassword,
    Token,
    UserCreate,
    UserLogin,
    UserOut,
    UserRoleUpdate,
)
from ..services.auth import (
    create_token,
    get_current_user,
    hash_password,
    log_operation,
    require_admin,
    verify_password,
)

router = APIRouter(tags=["user"])


@router.post("/api/auth/register", response_model=Token)
def register(body: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(status_code=400, detail="用户名已存在")
    # 注册一律 user 角色，管理员由种子/现有管理员创建，防自封
    user = User(
        username=body.username,
        password_hash=hash_password(body.password),
        role="user",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return Token(access_token=create_token(user))


@router.post("/api/auth/login", response_model=Token)
def login(body: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == body.username).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if user.role == "banned":
        raise HTTPException(status_code=401, detail="账号已被禁用")
    return Token(access_token=create_token(user))


@router.get("/api/users/me")
def me(user: User = Depends(get_current_user)):
    """当前用户信息。must_change_password：admin 仍用默认口令 admin123 时为 True。"""
    must_change = (
        user.role == "admin"
        and verify_password("admin123", user.password_hash)
    )
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "must_change_password": must_change,
    }


@router.post("/api/auth/change-password")
def change_password(
    body: ChangePassword,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """用户自助改密。密码不在 JWT 中，改密后现有 token 无需失效。"""
    if not verify_password(body.old_password, user.password_hash):
        raise HTTPException(status_code=400, detail="原密码不正确")
    user.password_hash = hash_password(body.new_password)
    db.commit()
    log_operation(db, "auth.change_password", f"用户改密：{user.username}", user.id)
    return {"ok": True}


# ---------------- 用户管理（管理员） ----------------

@router.get("/api/users")
def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    keyword: str | None = Query(None, description="用户名模糊搜索"),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    q = db.query(User)
    if keyword:
        q = q.filter(User.username.like(f"%{keyword}%"))
    total = q.count()
    rows = (
        q.order_by(User.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "items": [
            UserOut(
                id=u.id,
                username=u.username,
                role=u.role,
                created_at=str(u.created_at),
            )
            for u in rows
        ],
        "total": total,
    }


@router.patch("/api/users/{user_id}/role")
def update_user_role(
    user_id: int,
    body: UserRoleUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """改角色 / 封禁（banned）/ 解封。禁止对自己降级或封禁。"""
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="不能修改自己的角色")
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    old = target.role
    target.role = body.role
    db.commit()
    log_operation(
        db, "user.update_role", f"用户 {target.username}：{old} → {body.role}", admin.id
    )
    return {"ok": True}


@router.patch("/api/users/{user_id}/password")
def reset_user_password(
    user_id: int,
    body: ResetPassword,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """管理员重置用户密码。"""
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    target.password_hash = hash_password(body.new_password)
    db.commit()
    log_operation(
        db, "user.reset_password", f"重置用户密码：{target.username}", admin.id
    )
    return {"ok": True}


# ---------------- 操作日志（管理员） ----------------

@router.get("/api/logs")
def list_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    action: str | None = Query(None, description="按操作类型过滤，如 disease.create"),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """操作日志（仅管理员）：按时间倒序分页。"""
    q = db.query(OperationLog)
    if action:
        q = q.filter(OperationLog.action == action)
    total = q.count()
    rows = (
        q.order_by(OperationLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "items": [
            {
                "id": r.id,
                "user_id": r.user_id,
                "action": r.action,
                "detail": r.detail,
                "created_at": str(r.created_at),
            }
            for r in rows
        ],
        "total": total,
    }
