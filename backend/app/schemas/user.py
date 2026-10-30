from typing import Literal

from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    """注册请求。注意：role 由服务端强制为 user，禁止自封 admin。"""
    username: str = Field(..., min_length=2, max_length=64)
    password: str = Field(..., min_length=6, max_length=128)


class UserLogin(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ChangePassword(BaseModel):
    """用户自助改密。"""
    old_password: str
    new_password: str = Field(..., min_length=6, max_length=128)


class UserRoleUpdate(BaseModel):
    """管理员改角色 / 封禁解封（banned 为封禁状态，解封改回 user）。"""
    role: Literal["admin", "user", "banned"]


class ResetPassword(BaseModel):
    """管理员重置用户密码。"""
    new_password: str = Field(..., min_length=6, max_length=128)


class UserOut(BaseModel):
    id: int
    username: str
    role: str
    created_at: str | None = None
