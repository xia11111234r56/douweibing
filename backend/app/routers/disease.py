"""病害知识 CRUD。写操作需管理员权限并记录操作日志。"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Disease, Host, User
from ..schemas import DiseaseCreate, DiseaseUpdate, serialize_disease
from ..schemas.disease import DiseaseOut
from ..services.auth import log_operation, require_admin

router = APIRouter(tags=["disease"])


@router.get("/api/diseases", response_model=None)
def list_diseases(
    page: int | None = Query(None, ge=1, description="传页码启用分页"),
    page_size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """病害列表。

    双模式分页：page 为空时返回裸数组（小程序 4 页按此处理，保持兼容）；
    page 有值时返回 {"items": [...], "total": N} 供管理平台分页。
    """
    if page is None:
        return [serialize_disease(d) for d in db.query(Disease).order_by(Disease.id).all()]
    q = db.query(Disease).order_by(Disease.id)
    total = q.count()
    rows = q.offset((page - 1) * page_size).limit(page_size).all()
    return {"items": [serialize_disease(d) for d in rows], "total": total}


@router.get("/api/diseases/{disease_id}", response_model=DiseaseOut)
def get_disease(disease_id: int, db: Session = Depends(get_db)):
    d = db.get(Disease, disease_id)
    if d is None:
        raise HTTPException(status_code=404, detail="病害不存在")
    return serialize_disease(d)


@router.post("/api/diseases", response_model=DiseaseOut)
def create_disease(
    body: DiseaseCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if db.get(Host, body.host_id) is None:
        raise HTTPException(status_code=400, detail="寄主作物不存在")
    d = Disease(**body.model_dump())
    db.add(d)
    db.commit()
    db.refresh(d)
    log_operation(db, "disease.create", f"新增病害：{d.name}", admin.id)
    return serialize_disease(d)


@router.put("/api/diseases/{disease_id}", response_model=DiseaseOut)
def update_disease(
    disease_id: int,
    body: DiseaseUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    d = db.get(Disease, disease_id)
    if d is None:
        raise HTTPException(status_code=404, detail="病害不存在")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(d, k, v)
    db.commit()
    db.refresh(d)
    log_operation(db, "disease.update", f"更新病害：{d.name}", admin.id)
    return serialize_disease(d)


@router.delete("/api/diseases/{disease_id}")
def delete_disease(
    disease_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    d = db.get(Disease, disease_id)
    if d is None:
        raise HTTPException(status_code=404, detail="病害不存在")
    name = d.name
    db.delete(d)
    db.commit()
    log_operation(db, "disease.delete", f"删除病害：{name}", admin.id)
    return {"ok": True}
