"""多维多条件检索（导师课题核心）：病害名/寄主/症状关键词/药剂/类型/严重度。"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..models import Disease, Host, Pesticide, Treatment
from ..schemas.disease import DiseaseOut, serialize_disease

router = APIRouter(tags=["search"])


@router.get("/api/search", response_model=None)
def search(
    keyword: str | None = Query(None, description="病害名/症状/病原关键词"),
    host: str | None = Query(None, description="寄主作物名，如：绿豆"),
    disease_type: str | None = Query(None, description="真菌性/细菌性/病毒性/生理性"),
    pesticide: str | None = Query(None, description="药剂名关键词"),
    severity: str | None = Query(None, description="按某严重度有防治方案：轻/中/重"),
    page: int | None = Query(None, ge=1, description="传页码启用分页"),
    page_size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    q = (
        db.query(Disease)
        .options(selectinload(Disease.treatments), selectinload(Disease.host))
    )

    if keyword:
        like = f"%{keyword}%"
        q = q.filter(
            or_(
                Disease.name.like(like),
                Disease.symptoms.like(like),
                Disease.pathogen.like(like),
                Disease.conditions.like(like),
            )
        )
    if host:
        q = q.join(Host).filter(Host.name == host)
    if disease_type:
        q = q.filter(Disease.disease_type == disease_type)
    if pesticide:
        q = q.join(Disease.pesticides).filter(Pesticide.name.like(f"%{pesticide}%"))
    if severity:
        q = q.join(Treatment).filter(Treatment.severity_level == severity)

    if page is None:
        return [serialize_disease(d) for d in q.all()]
    total = q.count()
    rows = q.offset((page - 1) * page_size).limit(page_size).all()
    return {"items": [serialize_disease(d) for d in rows], "total": total}
