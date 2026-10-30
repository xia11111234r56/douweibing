"""GIS 空间数据：FAOSTAT / 中国统计年鉴 / WorldClim 汇总入库，供地图与风险区划查询。"""
from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class SpatialData(Base):
    __tablename__ = "spatial_data"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    region_code: Mapped[str] = mapped_column(String(16), index=True)  # 国家/省代码
    region_name: Mapped[str] = mapped_column(String(64), index=True)  # China / 内蒙古
    region_level: Mapped[str] = mapped_column(String(16))  # country / province
    year: Mapped[int] = mapped_column(Integer, index=True)
    metric: Mapped[str] = mapped_column(String(16))  # production / area / yield
    value: Mapped[float] = mapped_column()
    unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)  # FAOSTAT / 统计年鉴
