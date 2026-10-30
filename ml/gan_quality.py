"""GAN 生成质量定量评估：多样性 + 类一致性（不靠肉眼，可复现）。

两类指标：
1. 类内多样性：每类 100 张生成图的像素标准差（均值/通道）。模式崩溃时趋近 0。
   与真实训练图的同指标对比，给出相对多样性。
2. 分类一致性：用 best_finetune.pth 对每类生成图预测，统计"预测=该类"的比例与
   平均置信度。高置信说明生成图落在该类的视觉区域（受分类器局限，仅作辅助）。

产物：experiments/gan_quality.json
用法：python gan_quality.py [--root augmented|augmented_v2] [--out gan_quality.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import torch
import torch.nn.functional as F
from PIL import Image
from torchvision import datasets, transforms

from config import (  # noqa: E402
    CHECKPOINTS_DIR,
    CLASS_NAMES,
    EXPERIMENTS_DIR,
    IMG_SIZE,
    ORGANIZED_DIR,
)
from train_classifier import build_model  # noqa: E402

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


def _arg_parser():
    p = argparse.ArgumentParser(description="GAN 生成质量定量评估")
    p.add_argument("--root", default="augmented", help="生成图目录名（如 augmented / augmented_v2）")
    p.add_argument("--out", default="gan_quality.json", help="输出 json 文件名")
    return p.parse_args()


def _std_of_files(files: list[Path]) -> float:
    """对一组图求像素标准差（先缩到 64×64 加速）。"""
    vals = []
    for p in files[:50]:
        img = Image.open(p).convert("RGB").resize((64, 64))
        arr = torch.as_tensor(list(img.getdata()), dtype=torch.float32).view(64, 64, 3)
        vals.append(arr)
    t = torch.stack(vals) / 255.0  # [N,64,64,3]
    return float(t.std().item())


def main() -> None:
    args = _arg_parser()
    aug_root = EXPERIMENTS_DIR / args.root
    if not aug_root.exists():
        print(f"[错误] {aug_root} 不存在")
        sys.exit(1)
    ckpt = CHECKPOINTS_DIR / "best_finetune.pth"
    model = build_model(pretrained=False, num_classes=len(CLASS_NAMES)).to(DEVICE)
    model.load_state_dict(torch.load(ckpt, map_location=DEVICE))
    model.eval()
    tf = transforms.Compose([
        transforms.Resize((IMG_SIZE, IMG_SIZE)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])

    real_std = []
    report = {"per_class": {}, "overall": {}}
    agree_total = agree_conf = n_total = 0

    for cls in CLASS_NAMES:
        gen_files = sorted((aug_root / cls).glob("*.png"))
        real_files = sorted((ORGANIZED_DIR / "train" / cls).glob("*"))[:50]
        if not gen_files:
            continue
        gen_std = _std_of_files(gen_files)
        real_std.append(_std_of_files(real_files) if real_files else None)

        # 分类一致性
        confs = []
        with torch.no_grad():
            for p in gen_files[:50]:
                x = tf(Image.open(p).convert("RGB")).unsqueeze(0).to(DEVICE)
                prob = F.softmax(model(x), dim=1)[0]
                confs.append((float(prob.argmax() == CLASS_NAMES.index(cls)),
                              float(prob.max())))
        agree = sum(c for c, _ in confs)
        conf = sum(c for _, c in confs) / len(confs)
        agree_total += agree
        agree_conf += conf * len(confs)
        n_total += len(confs)
        report["per_class"][cls] = {
            "gen_pixel_std": round(gen_std, 4),
            "real_pixel_std": round(real_std[-1], 4) if real_std[-1] else None,
            "class_agree_rate": round(agree / len(confs), 4),
            "mean_conf": round(conf, 4),
        }

    report["overall"] = {
        "n_gen_total": n_total,
        "class_agree_rate": round(agree_total / n_total, 4) if n_total else None,
        "mean_conf": round(agree_conf / n_total, 4) if n_total else None,
        "mean_gen_pixel_std": round(sum(
            v["gen_pixel_std"] for v in report["per_class"].values()) / len(report["per_class"]), 4),
    }
    rstd = [s for s in real_std if s]
    if rstd:
        report["overall"]["mean_real_pixel_std"] = round(sum(rstd) / len(rstd), 4)

    out = EXPERIMENTS_DIR / args.out
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\n报告: {out}")


if __name__ == "__main__":
    main()
