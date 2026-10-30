from pydantic import BaseModel, ConfigDict


class GraphNodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str
    name: str
    properties: dict | None = None


class GraphEdgeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_id: int
    target_id: int
    relation: str
    weight: float
