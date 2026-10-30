"""环境模态：EXIF 时间/GPS 提取 + WorldClim 月平均气候回查 + 用户输入归一化。

数据来源设计（无需传感器）：
1. 照片 EXIF 自带拍摄时间 + GPS 定位
2. WorldClim 月平均气候栅格（公开免费）下采样为 CSV 网格：
   data/spatial/worldclim_china.csv  (lat, lon, month, tavg, prec)
   按最近邻匹配取该地点该月的平均温/降水 → 该图的环境上下文
3. 用户可选填：生育期 / 天气档位 / 种植方式
"""
from __future__ import annotations

import csv
import io
from pathlib import Path

from PIL import ExifTags, Image

from ..config import SPATIAL_DIR

# 生育期/天气档位/种植方式的合法取值（供校验与文档）
GROWTH_STAGES = ["苗期", "分枝期", "开花期", "结荚期", "成熟期"]
WEATHER_MODES = ["高温高湿", "阴雨连绵", "雨后天晴", "晴热干旱", "虫害盛发"]
PLANTING_MODES = ["露地", "大棚"]

_GRID_PATH = SPATIAL_DIR / "worldclim_china.csv"
_grid_by_month: dict[int, list[dict]] | None = None


def _load_grid() -> dict[int, list[dict]]:
    """懒加载 WorldClim 网格（按月索引）；文件不存在时返回空 dict。"""
    global _grid_by_month
    if _grid_by_month is not None:
        return _grid_by_month
    index: dict[int, list[dict]] = {}
    if _GRID_PATH.exists():
        with open(_GRID_PATH, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                try:
                    m = int(row["month"])
                except (KeyError, ValueError):
                    continue
                index.setdefault(m, []).append(row)
    _grid_by_month = index
    return index


def extract_exif(image: Image.Image) -> dict:
    """从图片提取拍摄时间与 GPS。返回 {capture_datetime, month, lat, lon}。"""
    out: dict = {"capture_datetime": None, "month": None, "lat": None, "lon": None}
    try:
        exif = image.getexif()
    except Exception:
        return out

    # 拍摄时间（新版 Pillow：ExifTags.Base.DateTime）
    dt_str = exif.get(ExifTags.Base.DateTime) or exif.get(0x0132)  # "YYYY:MM:DD HH:MM:SS"
    if dt_str:
        try:
            out["capture_datetime"] = dt_str
            out["month"] = int(dt_str[5:7])
        except Exception:
            pass

    # GPS
    try:
        gps_ifd = exif.get_ifd(ExifTags.IFD.GPSInfo)
        lat_ref = gps_ifd.get(1)
        lat = gps_ifd.get(2)
        lon_ref = gps_ifd.get(3)
        lon = gps_ifd.get(4)
        if lat and lon:
            out["lat"] = _dms_to_dd(lat, lat_ref == "S")
            out["lon"] = _dms_to_dd(lon, lon_ref == "W")
    except Exception:
        pass
    return out


def _dms_to_dd(dms: tuple, negative: bool = False) -> float:
    deg, minutes, sec = float(dms[0]), float(dms[1]), float(dms[2])
    dd = deg + minutes / 60 + sec / 3600
    return -dd if negative else dd


def climate_lookup(lat: float, lon: float, month: int | None) -> dict | None:
    """WorldClim 网格最近邻回查，返回 {"tavg": float, "prec": float, "source": str}。"""
    index = _load_grid()
    if not index or month is None:
        return None
    rows = index.get(int(month))
    if not rows:
        return None
    best = None
    best_d = 1e18
    for r in rows:
        try:
            rlat, rlon = float(r["lat"]), float(r["lon"])
        except (KeyError, ValueError):
            continue
        d = (rlat - lat) ** 2 + (rlon - lon) ** 2
        if d < best_d:
            best_d = d
            best = r
    if best is None:
        return None
    return {
        "tavg": round(float(best["tavg"]), 1),
        "prec": round(float(best["prec"]), 1),
        "source": "worldclim",
    }


def build_env_context(image: Image.Image | None, user_env) -> dict:
    """组装环境模态上下文（落库用）。

    返回：
    {
      "growth_stage": ..., "weather": ..., "planting": ...,   # 用户输入
      "capture_month": 7, "gps_lat": ..., "gps_lon": ...,      # EXIF 自动
      "clim": {"tavg": 27.0, "prec": 180.0},                   # WorldClim 回查
      "source": ["user", "exif", "worldclim"]
    }
    """
    ctx: dict = {}
    src: list[str] = []

    # 用户输入
    if user_env:
        if user_env.growth_stage:
            ctx["growth_stage"] = user_env.growth_stage
        if user_env.weather:
            ctx["weather"] = user_env.weather
        if user_env.planting:
            ctx["planting"] = user_env.planting
        if user_env.lat is not None:
            ctx["gps_lat"] = user_env.lat
        if user_env.lon is not None:
            ctx["gps_lon"] = user_env.lon
        if ctx:
            src.append("user")

    # EXIF + WorldClim
    exif: dict = {}
    if image is not None:
        exif = extract_exif(image)
        if exif.get("month"):
            ctx["capture_month"] = exif["month"]
            src.append("exif")
        if exif.get("lat") and exif.get("lon"):
            ctx.setdefault("gps_lat", exif["lat"])
            ctx.setdefault("gps_lon", exif["lon"])
            src.append("exif")

    lat = ctx.get("gps_lat")
    lon = ctx.get("gps_lon")
    month = ctx.get("capture_month")
    if lat is not None and lon is not None:
        clim = climate_lookup(float(lat), float(lon), month)
        if clim:
            ctx["clim"] = clim
            src.append("worldclim")

    ctx["source"] = src
    return ctx
