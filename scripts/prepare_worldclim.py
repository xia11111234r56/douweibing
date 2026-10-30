"""WorldClim 月平均气候数据处理 → EXIF 回查网格 + 地图可视化栅格。

输出：
    data/spatial/worldclim_china.csv    # 粗网格 (lat, lon, month, tavg, prec)
                                        # 后端 services/env.py 最近邻回查用
    data/spatial/worldclim_clip/        # 中国范围裁剪的 tavg/prec GeoTIFF（地图可视化用）

WorldClim 2.1 base 数据按变量打包为 ZIP（内含 12 个月 GeoTIFF）：
    https://geodata.ucdavis.edu/climate/worldclim/2_1/base/wc2.1_10m_{var}.zip

依赖：pip install -r scripts/requirements-gis.txt （rasterio）
用法：python scripts/prepare_worldclim.py [--res 10m] [--grid 0.25]
"""
from __future__ import annotations

import argparse
import csv
import sys
import zipfile
from pathlib import Path

import numpy as np
import requests

ROOT = Path(__file__).resolve().parent.parent
SPATIAL = ROOT / "data" / "spatial"
DL_DIR = SPATIAL / "worldclim_dl"        # ZIP 缓存 + 解压目录
CLIP_DIR = SPATIAL / "worldclim_clip"    # 中国裁剪 GeoTIFF
CSV_OUT = SPATIAL / "worldclim_china.csv"

# WorldClim 2.1 base GeoTIFF 下载地址（UCDAVIS，按变量打包 ZIP）
BASE_URL = "https://geodata.ucdavis.edu/climate/worldclim/2_1/base"
VARS = {"tavg": "tavg", "prec": "prec"}

# 中国范围 bbox（经纬度）
CHINA_BBOX = (70, 15, 140, 55)  # min_lon, min_lat, max_lon, max_lat


def ensure_extracted(var: str, res: str) -> Path:
    """下载并解压某变量的 12 个月 ZIP，返回解压目录（已存在则跳过）。"""
    DL_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = DL_DIR / f"wc2.1_{res}_{var}.zip"
    if not zip_path.exists():
        url = f"{BASE_URL}/wc2.1_{res}_{var}.zip"
        print(f"  下载 {url} ...")
        r = requests.get(url, timeout=300)
        r.raise_for_status()
        zip_path.write_bytes(r.content)
        print(f"  已保存 {zip_path}（{zip_path.stat().st_size/1e6:.1f} MB）")
    out_dir = DL_DIR / f"wc2.1_{res}_{var}"
    if not out_dir.exists():
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(out_dir)
        print(f"  已解压到 {out_dir}")
    return out_dir


def build_grid_csv(res: str, grid_step: float) -> None:
    try:
        import rasterio
        from rasterio.transform import rowcol
        from rasterio.windows import from_bounds
    except ImportError as e:
        print(f"[错误] 需要 rasterio：pip install -r scripts/requirements-gis.txt ({e})")
        sys.exit(1)

    CLIP_DIR.mkdir(parents=True, exist_ok=True)
    monthly: dict[str, dict[int, np.ndarray]] = {}
    profile = None

    for var in VARS:
        extracted = ensure_extracted(var, res)
        monthly[var] = {}
        for m in range(1, 13):
            tif = extracted / f"wc2.1_{res}_{var}_{m:02d}.tif"
            src_path = CLIP_DIR / f"wc2.1_{res}_{var}_{m:02d}_clip.tif"
            with rasterio.open(tif) as src:
                window = from_bounds(*CHINA_BBOX, transform=src.transform)
                out_transform = src.window_transform(window)
                arr = src.read(1, window=window)
                if profile is None:
                    profile = src.profile.copy()
                profile.update(height=arr.shape[0], width=arr.shape[1], transform=out_transform)
                with rasterio.open(src_path, "w", **profile) as dst:
                    dst.write(arr, 1)
            monthly[var][m] = arr
            print(f"  已裁剪 {var}_{m}")

    # 下采样为粗网格 CSV（每 grid_step 度一个采样点），像素索引用真实 transform
    transform = profile["transform"]
    lons = np.arange(CHINA_BBOX[0] + grid_step / 2, CHINA_BBOX[2], grid_step)
    lats = np.arange(CHINA_BBOX[1] + grid_step / 2, CHINA_BBOX[3], grid_step)
    rows = []
    for lat in lats:
        for lon in lons:
            for m in range(1, 13):
                # rowcol 返回 (row, col)，勿颠倒
                row_idx, col_idx = rowcol(transform, float(lon), float(lat))
                arr_t = monthly["tavg"][m]
                if not (0 <= row_idx < arr_t.shape[0] and 0 <= col_idx < arr_t.shape[1]):
                    continue
                tavg = arr_t[row_idx, col_idx]
                prec = monthly["prec"][m][row_idx, col_idx]
                # WorldClim 用 -3.4e38 / -32768 作 nodata（非 NaN），一并剔除
                if not np.isfinite(tavg) or abs(tavg) > 1e4 or abs(prec) > 1e4:
                    continue
                rows.append({
                    "lat": round(lat, 3), "lon": round(lon, 3), "month": m,
                    "tavg": round(float(tavg), 1), "prec": round(float(prec), 1),
                })
    with open(CSV_OUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["lat", "lon", "month", "tavg", "prec"])
        w.writeheader()
        w.writerows(rows)
    print(f"✅ {CSV_OUT}（{len(rows)} 行）")
    print("后端 services/env.py 将据此做 EXIF 环境回查；裁剪栅格供 GIS 可视化")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--res", default="10m", choices=["10m", "2.5m"])
    parser.add_argument("--grid", type=float, default=0.25, help="采样网格步长（度）")
    args = parser.parse_args()
    build_grid_csv(args.res, args.grid)
