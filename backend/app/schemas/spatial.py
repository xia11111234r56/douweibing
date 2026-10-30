from pydantic import BaseModel, ConfigDict


class SpatialDataOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    region_code: str
    region_name: str
    region_level: str
    year: int
    metric: str
    value: float
    unit: str | None = None
    source: str | None = None
