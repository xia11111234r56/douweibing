"""论文数字核查：批量核对 ml/experiments 各报告 json 与论文初稿关键数字。

论文所有指标须与产物 json 一致（文档代码匹配原则）。本脚本打印各报告
关键字段，供论文定稿/结题材料逐项对照。缺失/损坏文件会显式标记。

注意：balanced_report.json 以 python repr 写入（字符串跨行隐式拼接），
非标准 JSON，脚本对解析失败的文件回退到打印原文前 300 字符。

用法（ml/ 下）：python verify_reports.py
"""
from __future__ import annotations

import json
from pathlib import Path

BASE = Path(__file__).resolve().parent / "experiments"


def rd(name: str):
    p = BASE / name
    if not p.exists():
        return {"MISSING": name}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        return {"BROKEN": name, "err": str(e), "head": p.read_text(encoding="utf-8")[:300]}


def show(label: str, val, keys: tuple[str, ...] | None = None) -> None:
    print(f"== {label} ==")
    if isinstance(val, dict):
        if "MISSING" in val or "BROKEN" in val:
            print("  ", val)
        elif keys:
            print("  ", {k: val.get(k) for k in keys})
        else:
            print("  ", val)
    elif isinstance(val, list):
        print(f"  list[{len(val)}]:")
        for i, item in enumerate(val):
            print(f"   [{i}]", item if not isinstance(item, dict) else
                  {k: item.get(k) for k in ("variant", "best_val_acc", "test_accuracy",
                                            "test89_accuracy", "eval178_accuracy")})
    else:
        print("  ", val)


def main() -> None:
    show("eval_report.json (test89 生产 B 重评估)", rd("eval_report.json"),
         ("test_accuracy", "consistency", "pass"))
    show("eval_report_178.json (eval178 生产 B 重评估)", rd("eval_report_178.json"),
         ("test_accuracy", "consistency", "pass"))
    show("seed_sweep.json (4 seed 复现)", rd("seed_sweep.json"),
         ("per_seed", "test_mean", "test_std", "test_all", "reference_single_run_seed42_production"))
    show("cv_report.json (5 折 CV)", rd("cv_report.json"),
         ("pooled_accuracy", "mean", "std", "folds", "per_class"))
    show("severity_cv.json (严重度 5 折 CV)", rd("severity_cv.json"),
         ("mean_acc", "std_acc", "fold_accs", "recall"))
    show("multimodal_ablation.json (多模态消融)", rd("multimodal_ablation.json"),
         ("baseline_no_env_accuracy", "settings", "flip_examples"))
    show("ablation_report.json (GAN A/B 消融)", rd("ablation_report.json"), None)
    show("B_report.json (2x2 B)", rd("B_report.json"),
         ("variant", "best_val_acc", "test89_accuracy", "eval178_accuracy"))
    show("C_report.json (2x2 C)", rd("C_report.json"),
         ("variant", "best_val_acc", "test89_accuracy", "eval178_accuracy"))
    show("balanced_report.json (2x2 D)", rd("balanced_report.json"),
         ("best_val_acc", "test_accuracy", "test_accuracy_178"))
    show("gan_quality.json (生成质量)", rd("gan_quality.json"), None)
    show("ensemble_report.json (Ensemble+TTA, 论文可选引用)", rd("ensemble_report.json"), None)


if __name__ == "__main__":
    main()
