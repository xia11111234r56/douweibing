"""多模态融合消融：有/无环境模态对 top-1 识别一致率的影响（真实部署链路）。

对比「无环境模态」（纯图像分类）与「有环境模态」（图像 + EXIF 拍摄月份 +
天气档位知识规则）在测试集 89 张上的 top-1 一致率，全部复用后端实际部署代码
（ONNX predict_topk + knowledge_rules.adjust_candidates）。

数据真实性说明（诚实口径）：
- EXIF 拍摄月份：真实自动提取（86/89 有）。
- 天气档位：来自用户输入，离线测试无真实选择，故对 5 个档位逐一注入做敏感性分析。
- WorldClim 气候回查：代码就绪但 worldclim_china.csv 尚未下载（backend/data/spatial/），
  部署中 clim 不命中、温度规则不触发，脚本会如实检测并报告。

基线（无环境，weather=None）应与 eval_report.json 的 test_accuracy 一致，验证消融链路正确。

用法（ml/ 目录下）：python ablation_multimodal.py
产物：experiments/multimodal_ablation.json
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))  # backend 根（app 包）
sys.path.insert(0, str(Path(__file__).resolve().parent))                      # ml/

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from app.services import knowledge_rules  # noqa: E402
from app.services.env import _GRID_PATH, climate_lookup, extract_exif  # noqa: E402
from app.services.model_inference import predict_topk  # noqa: E402

from config import EXPERIMENTS_DIR, ORGANIZED_DIR  # noqa: E402

# 环境模态设置：None=严格无环境（基线）；"真实自动"=EXIF+WorldClim（无天气输入）；
# 其余为 EXIF+WorldClim+用户天气档位（离线无真实选择，作敏感性）
SETTINGS = [
    ("无环境", None),
    ("真实自动(EXIF+WorldClim)", "AUTO"),
    ("天气:高温高湿", "高温高湿"),
    ("天气:阴雨连绵", "阴雨连绵"),
    ("天气:雨后天晴", "雨后天晴"),
    ("天气:晴热干燥", "晴热干燥"),
    ("天气:低温", "低温"),
]
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def build_env(exif: dict, weather: str | None) -> dict:
    """按部署 build_env_context 语义组装环境模态（月份/GPS→WorldClim + 天气档位）。"""
    env: dict = {}
    if weather:
        env["weather"] = weather
    lat, lon, month = exif.get("lat"), exif.get("lon"), exif.get("month")
    if lat is not None and lon is not None and month is not None:
        clim = climate_lookup(float(lat), float(lon), month)
        if clim:
            env["clim"] = clim
    return env


def collect_test_images() -> list[tuple[Path, str]]:
    root = ORGANIZED_DIR / "test"
    items = []
    for sub in sorted(p for p in root.iterdir() if p.is_dir()):
        for p in sorted(sub.glob("*")):
            if p.is_file() and p.suffix.lower() in IMG_EXT:
                items.append((p, sub.name))
    return items


def main() -> None:
    items = collect_test_images()
    if not items:
        print(f"[错误] 测试集为空: {ORGANIZED_DIR / 'test'}")
        sys.exit(1)
    print(f"测试集 {len(items)} 张；WorldClim 网格文件存在: {_GRID_PATH.exists()}")

    correct = {name: 0 for name, _ in SETTINGS}
    flips = {name: {"翻案总数": 0, "对→错": 0, "错→对": 0, "均错": 0} for name, _ in SETTINGS}
    conf_deltas = {name: [] for name, _ in SETTINGS}
    n_month = n_gps = n_clim = 0
    flip_examples: list[dict] = []

    for p, true_label in items:
        data = p.read_bytes()
        cands = predict_topk(data, k=5)
        base_top = cands[0]["name"]

        try:
            exif = extract_exif(Image.open(p))
        except Exception:  # noqa: BLE001
            exif = {}
        if exif.get("month"):
            n_month += 1
        if exif.get("lat") and exif.get("lon"):
            n_gps += 1
        if build_env(exif, None).get("clim"):
            n_clim += 1

        for name, weather in SETTINGS:
            env = build_env(exif, weather) if weather is not None else None
            adjusted = copy.deepcopy(cands)
            adjusted = knowledge_rules.adjust_candidates(adjusted, env)
            top = adjusted[0]["name"]
            if top == true_label:
                correct[name] += 1
            conf_deltas[name].append(adjusted[0]["confidence"] - cands[0]["confidence"])
            if top != base_top:
                flips[name]["翻案总数"] += 1
                if base_top == true_label and top != true_label:
                    flips[name]["对→错"] += 1
                elif base_top != true_label and top == true_label:
                    flips[name]["错→对"] += 1
                else:
                    flips[name]["均错"] += 1
                if len(flip_examples) < 12:
                    flip_examples.append({
                        "file": str(p.relative_to(ORGANIZED_DIR)),
                        "true": true_label, "base": base_top,
                        "setting": name, "top": top,
                    })

    n = len(items)
    base_acc = correct["无环境"] / n
    print(f"\n基线（无环境模态）top-1 一致率: {base_acc:.4f} "
          f"（对照 eval_report.json 生产模型一致率）")
    print(f"EXIF 拍摄月份命中 {n_month}/{n}；GPS {n_gps}/{n}；WorldClim 回查命中 {n_clim}/{n}")
    rows = {}
    for name, _ in SETTINGS:
        acc = correct[name] / n
        mean_delta = float(np.mean(conf_deltas[name])) if conf_deltas[name] else 0.0
        f = flips[name]
        print(f"[{name}]: 一致率 {acc:.4f} 翻案 {f['翻案总数']} "
              f"(对→错 {f['对→错']} / 错→对 {f['错→对']} / 均错 {f['均错']}) "
              f"top1置信度均变 {mean_delta:+.4f}")
        rows[name] = {
            "accuracy": round(acc, 4),
            "correct": correct[name],
            "flips": f,
            "top1_conf_mean_delta": round(mean_delta, 4),
        }

    result = {
        "n": n,
        "baseline_no_env_accuracy": round(base_acc, 4),
        "eval_report_reference": 0.8315,
        "env_source_stats": {"exif_month": n_month, "gps": n_gps, "worldclim_hit": n_clim},
        "worldclim_grid_exists": _GRID_PATH.exists(),
        "settings": rows,
        "flip_examples": flip_examples,
        "method": "生产 ONNX classifier + backend knowledge_rules.adjust_candidates；"
                  "环境模态=真实EXIF(月份/GPS)+WorldClim回查+天气档位敏感性；"
                  "翻案以无环境基线的 top-1 为参照",
    }
    EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
    (EXPERIMENTS_DIR / "multimodal_ablation.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n报告: {EXPERIMENTS_DIR / 'multimodal_ablation.json'}")


if __name__ == "__main__":
    main()
