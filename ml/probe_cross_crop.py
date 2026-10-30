"""跨作物域兼容探测：芸豆（Phaseolus vulgaris）图能否补充绿豆模型训练。

用现部署模型（best_finetune.pth = B）对芸豆各病害类目录平铺推理，
看预测分布集中在哪些绿豆类：
  - 若芸豆「细菌性疫病」图集中判成 细菌性疫病(idx6)/晕疫(idx2)/炭疽(idx3)，
    说明特征相近、有补充价值；
  - 若分布散乱或全判一个无关类，说明域差大、直接灌进训练集有害。

用法（ml/ 下）：python probe_cross_crop.py <芸豆类目录...>
"""
from __future__ import annotations

import sys
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PIL import Image  # noqa: E402
import torch  # noqa: E402
from torchvision import transforms  # noqa: E402

from config import IMG_SIZE  # noqa: E402
from train_classifier import build_model  # noqa: E402

SORTED_CLASSES = ["健康", "叶腐病", "晕疫病", "枯萎病", "炭疽叶斑病",
                  "病毒病", "细菌性疫病", "细菌性萎蔫", "虫食", "轮纹叶斑病"]

IMG_T = transforms.Compose([
    transforms.Resize((IMG_SIZE, IMG_SIZE)),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
])

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


def probe(root: Path, model) -> None:
    files = sorted(p for p in root.iterdir()
                   if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".webp"})
    preds: Counter[int] = Counter()
    model.eval()
    with torch.no_grad():
        for p in files:
            x = IMG_T(Image.open(p).convert("RGB")).unsqueeze(0).to(DEVICE)
            preds[model(x).argmax(1).item()] += 1
    total = len(files)
    print(f"\n=== {root.name}（{total} 张）===")
    for idx, cnt in sorted(preds.items()):
        pct = cnt / total if total else 0
        bar = "#" * round(pct * 40)
        print(f"  {SORTED_CLASSES[idx]:<10} {cnt:>4}  {pct*100:5.1f}%  {bar}")


def main() -> None:
    model = build_model(pretrained=False).to(DEVICE)
    ckpt = Path(__file__).resolve().parent / "checkpoints" / "best_finetune.pth"
    model.load_state_dict(torch.load(ckpt, map_location=DEVICE))
    for d in sys.argv[1:]:
        probe(Path(d), model)


if __name__ == "__main__":
    main()
