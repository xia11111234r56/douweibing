"""GAN 增强消融（通用）：真实 + 某版 GAN 图 对比已有 baseline。

基线数字直接复用 ablation_report.json（同一协议、同一 seed 42、同一测试集）：
baseline test_acc 0.7865（真实 423 张）。本脚本只跑「+GAN 变体」：
  训练集 = real/train（10 类 423 张）+ {--aug} 目录（如 augmented_v2 全 10 类 1000 张，
  或 augmented_v3 仅 4 类 400 张），验证/测试集、初始化（best_public.pth）、
  增强协议与 ablation.py 完全一致。

用法（ml/ 目录下）：
    python ablation_v3.py --aug augmented_v2 --out ablation_report_v2.json
    python ablation_v3.py --aug augmented_v3 --out ablation_report_v3.json
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ablation import train_and_eval  # noqa: E402
from config import CLASS_NAMES, EXPERIMENTS_DIR, ORGANIZED_DIR  # noqa: E402


def build_augmented_train_dir(aug_name: str, out_name: str) -> Path | None:
    """real/train + {aug_name} 合并成消融训练集。"""
    aug_root = EXPERIMENTS_DIR / aug_name
    if not aug_root.exists():
        print(f"[跳过] 未找到 experiments/{aug_name}，先运行对应 train_gan*.py")
        return None
    out = EXPERIMENTS_DIR / out_name
    if out.exists():
        shutil.rmtree(out)
    for cls in CLASS_NAMES:
        real = ORGANIZED_DIR / "train" / cls
        gen = aug_root / cls
        dst = out / cls
        if real.exists():
            shutil.copytree(real, dst)
        if gen.exists():
            dst.mkdir(parents=True, exist_ok=True)
            for p in gen.glob("*.png"):
                shutil.copy2(p, dst / p.name)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--aug", default="augmented_v3", help="GAN 图目录名")
    parser.add_argument("--out", default="ablation_report_v3.json", help="输出 report 文件名")
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--seeds", default="",
                        help="多种子配对消融（逗号分隔，如 42,1000,7777）；留空则单 seed(42) 复用 baseline")
    args = parser.parse_args()

    tag = f"gan_augmented_{args.aug.removeprefix('augmented_')}"
    report_path = EXPERIMENTS_DIR / args.out
    # seed42 的 baseline/v1 已有，避免重跑
    old = json.loads((EXPERIMENTS_DIR / "ablation_report.json").read_text(encoding="utf-8"))
    baseline42 = next((d for d in old if d["tag"] == "baseline"), None)
    v1 = next((d for d in old if d["tag"] == "gan_augmented"), None)

    aug_train = build_augmented_train_dir(args.aug, f"ablation_train_{args.aug.removeprefix('augmented_')}")
    if aug_train is None:
        sys.exit(1)

    seeds = [int(s.strip()) for s in args.seeds.split(",") if s.strip()]
    if not seeds:
        # 单 seed（42）模式：基线复用现成值
        if baseline42 is None:
            print("[错误] ablation_report.json 缺少 baseline，先跑 ablation.py")
            sys.exit(1)
        res = train_and_eval(aug_train, tag, args.epochs)
        report = {
            "baseline": baseline42, "gan_augmented_v1": v1, "variant": res,
            "delta_vs_baseline": round(res["test_acc"] - baseline42["test_acc"], 4),
            "delta_vs_v1": round(res["test_acc"] - v1["test_acc"], 4) if v1 else None,
            "note": f"{args.aug} 单 seed（42）。协议/seed/测试集与 ablation.py 一致，基线为复用值。",
        }
    else:
        rows = []
        for seed in seeds:
            if seed == 42 and baseline42 is not None:
                base_test = baseline42["test_acc"]
                print(f"[seed {seed}] baseline 复用 {base_test}")
            else:
                base = train_and_eval(ORGANIZED_DIR / "train", f"baseline_s{seed}", args.epochs, seed=seed)
                base_test = base["test_acc"]
                print(f"[seed {seed}] baseline 重跑 {base_test}")
            res = train_and_eval(aug_train, f"{tag}_s{seed}", args.epochs, seed=seed)
            rows.append({"seed": seed, "baseline_test": round(base_test, 4),
                         f"{tag}_test": res["test_acc"],
                         "delta": round(res["test_acc"] - base_test, 4)})
            print(f"[seed {seed}] {tag} {res['test_acc']:.4f}  较同 seed 基线 {rows[-1]['delta']:+.4f}")
        deltas = [r["delta"] for r in rows]
        m = sum(deltas) / len(deltas)
        sd = (sum((d - m) ** 2 for d in deltas) / (len(deltas) - 1)) ** 0.5 if len(deltas) > 1 else None
        report = {
            "variant": tag,
            "seeds": rows,
            "mean_delta": round(m, 4),
            "std_delta": round(sd, 4) if sd is not None else None,
            "note": f"{args.aug} 多种子配对消融（同 seed 基线对照，seed42 基线复用 ablation_report.json 的 0.7865）。",
        }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\n报告: {report_path}")


if __name__ == "__main__":
    main()
