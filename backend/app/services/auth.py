"""JWT 认证：bcrypt 密码哈希 + HS256 token。"""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from ..config import JWT_ALGORITHM, JWT_EXPIRE_MINUTES, JWT_SECRET
from ..db import get_db
from ..models import OperationLog, User

security = HTTPBearer()
security_optional = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_token(user: User) -> str:
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "role": user.role,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def get_current_user(
    cred: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    try:
        payload = jwt.decode(cred.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="登录凭证无效或已过期")
    user = db.get(User, int(payload["sub"]))
    if user is None:
        raise HTTPException(status_code=401, detail="用户不存在")
    if user.role == "banned":
        raise HTTPException(status_code=401, detail="账号已被禁用")
    return user


def get_current_user_optional(
    cred: HTTPAuthorizationCredentials | None = Depends(security_optional),
    db: Session = Depends(get_db),
) -> User | None:
    """可选鉴权：无凭证 / 坏 token / 用户不存在时一律返回 None，绝不抛 401。

    供匿名可用的接口（如 /api/recognize，小程序匿名调用）绑定 user_id 用。
    """
    if cred is None:
        return None
    try:
        payload = jwt.decode(cred.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None
    user = db.get(User, int(payload["sub"]))
    if user is None or user.role == "banned":
        return None
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    """仅管理员可访问的依赖。非 admin 返回 403。"""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


def log_operation(
    db: Session,
    action: str,
    detail: str | None = None,
    user_id: int | None = None,
) -> None:
    """记录操作日志（operation_logs 表）。"""
    db.add(OperationLog(user_id=user_id, action=action, detail=detail))
    db.commit()
