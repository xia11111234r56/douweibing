from pydantic import BaseModel, ConfigDict, Field


class TreatmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    severity_level: str
    method_type: str
    content: str


class DiseaseBase(BaseModel):
    name: str
    disease_type: str
    host_id: int = Field(..., description="寄主作物 id（如绿豆）")
    name_en: str | None = None
    pathogen: str | None = None
    symptoms: str | None = None
    conditions: str | None = None
    image_path: str | None = None


class DiseaseCreate(DiseaseBase):
    pass


class DiseaseUpdate(BaseModel):
    name: str | None = None
    disease_type: str | None = None
    name_en: str | None = None
    pathogen: str | None = None
    symptoms: str | None = None
    conditions: str | None = None
    image_path: str | None = None


class DiseaseOut(BaseModel):
    """含 host_name 与 treatments 的完整病害视图（由 serialize_disease 组装）。"""

    id: int
    name: str
    name_en: str | None = None
    disease_type: str
    pathogen: str | None = None
    symptoms: str | None = None
    conditions: str | None = None
    image_path: str | None = None
    host_id: int
    host_name: str | None = None
    treatments: list[TreatmentOut] = []


def serialize_disease(d) -> DiseaseOut:
    """把 ORM Disease 组装为含关联字段的视图对象。"""
    return DiseaseOut(
        id=d.id,
        name=d.name,
        name_en=d.name_en,
        disease_type=d.disease_type,
        pathogen=d.pathogen,
        symptoms=d.symptoms,
        conditions=d.conditions,
        image_path=d.image_path,
        host_id=d.host_id,
        host_name=d.host.name if d.host else None,
        treatments=[TreatmentOut.model_validate(t) for t in d.treatments],
    )
