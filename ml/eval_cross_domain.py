"""跨域鲁棒性测试：Mendeley 公开图当测试集，看模型能否跨拍摄场景识别。

背景：test89/eval178 里虫食 support=0，加不加 251 张真实虫食训练（B vs A）在
top-1 上同分。本脚本用 Mendeley 公开图做跨域评估，量化"部署端真实虫食/健康
到底认不认得"：
  - Mendeley caterpillar 251 张（真实虫食）→ 期望预测 虫食（模型输出 index 8）
  - Mendeley healthy 244 张 → 期望预测 健康（模型输出 index 0）

输出各 checkpoint 的命中率 + 预测分布（诊断错到哪类）。

用法（ml/ 目录下）：
    python eval_cross_domain.py [checkpoint ...]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PIL import Image  # noqa: E402
import torch  # noqa: E402
from collections import Counter  # noqa: E402
from torchvision import transforms  # noqa: E402

from config import IMG_SIZE, PUBLIC_DIR  # noqa: E402
from train_classifier import build_model  # noqa: E402

# 模型输出索引 = 训练时按类目录名排序（与 labels.json 一致，勿用 config.CLASS_NAMES 顺序）
SORTED_CLASSES = ["健康", "叶腐病", "晕疫病", "枯萎病", "炭疽叶斑病",
                  "病毒病", "细菌性疫病", "细菌性萎蔫", "虫食", "轮纹叶斑病"]
TARGET_IDX = {"虫食": 8, "健康": 0}

IMG_T = transforms.Compose([
    transforms.Resize((IMG_SIZE, IMG_SIZE)),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
])

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
CAT = PUBLIC_DIR / "organized" / "train" / "caterpillar"
HEALTHY = PUBLIC_DIR / "organized" / "train" / "healthy"


def eval_dir(model, root: Path, expect: str) -> dict:
    """平铺图片目录（无类子目录），逐张用 IMG_T 推理。"""
    files = sorted(p for p in root.iterdir()
                   if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".webp"})
    hit, total = 0, 0
    preds: Counter[int] = Counter()
    target = TARGET_IDX[expect]
    model.eval()
    with torch.no_grad():
        for p in files:
            x = IMG_T(Image.open(p).convert("RGB")).unsqueeze(0).to(DEVICE)
            v = model(x).argmax(1).item()
            preds[v] += 1
            total += 1
            hit += (v == target)
    return {
        "dataset": root.name, "expect": expect, "n": total,
        "hit_rate": round(hit / total, 4),
        "pred_dist": {SORTED_CLASSES[k]: v for k, v in sorted(preds.items())},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("ckpts", type=Path, nargs="*",
                        default=[Path("checkpoints/best_finetune_aug.pth"),
                                 Path("checkpoints/best_finetune_B.pth")])
    args = parser.parse_args()
    for ckpt in args.ckpts:
        model = build_model(pretrained=False).to(DEVICE)
        model.load_state_dict(torch.load(ckpt, map_location=DEVICE))
        model.eval()
        print(f"\n=== {ckpt.name} ===")
        for root, expect in ((CAT, "虫食"), (HEALTHY, "健康")):
            r = eval_dir(model, root, expect)
            print(f"  {r['dataset']} (期望{expect}) 命中 {r['hit_rate']}  {r['n']}张")
            print(f"    预测分布: {r['pred_dist']}")


if __name__ == "__main__":
    main()
