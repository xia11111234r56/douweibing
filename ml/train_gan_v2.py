"""ACGAN 改进版（v2）：针对 v1 模式崩溃（生成图=彩色噪声）的三项关键改造。

对比 v1（train_gan.py）：
1. 判别器改标准 ACGAN 条件方式：卷积提特征后拼接类别嵌入向量，再分支输出
   真假/类别；不再把类别嵌入投影成 128×128×3 的输入图（v1 该设计让判别器
   只靠类别图即可分类，不看真实叶片结构，是崩溃主因）。
2. 类均衡采样：WeightedRandomSampler（权重=1/该类样本数），保证小类（叶腐/
   枯萎/细菌性疫病/虫食）也出现在每个 epoch，避免大类主导、小类分支崩溃。
3. 判别器真实输入加高斯噪声（std=0.1），防止 D 过拟合 335 张训练图。
4. 训练监控：每 epoch 记录 D/G 分项 loss 到 experiments/gan_progress/v2_losses.csv；
   每 20 epoch 保存生成样本到 gan_progress/v2_epoch_XXX/，可观察崩溃时机。

产物（不覆盖 v1，论文产物与数字不受影响）：
    checkpoints/acgan_g_v2.pth / acgan_d_v2.pth
    experiments/augmented_v2/{类名}/gan_*.png   （每类 100 张）
    experiments/gan_progress/...

用法（ml/ 下）：python train_gan_v2.py [--epochs 200] [--gen_per_class 100]
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import torch
import torch.nn as nn
from PIL import Image
from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler
from torchvision import transforms

from config import (  # noqa: E402
    BATCH_SIZE,
    CHECKPOINTS_DIR,
    CLASS_NAMES,
    EXPERIMENTS_DIR,
    IMG_SIZE_GAN,
    NUM_CLASSES,
    ORGANIZED_DIR,
    RANDOM_SEED,
)

Z_DIM = 100
EMB_DIM = 64
G_BASE = 64
D_BASE = 64
LR_G, LR_D = 2e-4, 1e-4
REAL_SMOOTH = 0.9
D_NOISE_STD = 0.1  # 判别器真实输入高斯噪声，防止 D 过拟合
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


class Generator(nn.Module):
    """同 v1：类别条件嵌入拼接噪声进全连接，5 层转置卷积到 128×128。"""

    def __init__(self):
        super().__init__()
        self.embed = nn.Embedding(NUM_CLASSES, 128)
        self.fc = nn.Sequential(
            nn.Linear(Z_DIM + 128, G_BASE * 8 * 4 * 4),
            nn.BatchNorm1d(G_BASE * 8 * 4 * 4), nn.ReLU(True),
        )
        self.deconv = nn.Sequential(
            nn.ConvTranspose2d(G_BASE * 8, G_BASE * 4, 4, 2, 1),
            nn.BatchNorm2d(G_BASE * 4), nn.ReLU(True),
            nn.ConvTranspose2d(G_BASE * 4, G_BASE * 2, 4, 2, 1),
            nn.BatchNorm2d(G_BASE * 2), nn.ReLU(True),
            nn.ConvTranspose2d(G_BASE * 2, G_BASE, 4, 2, 1),
            nn.BatchNorm2d(G_BASE), nn.ReLU(True),
            nn.ConvTranspose2d(G_BASE, G_BASE, 4, 2, 1),
            nn.BatchNorm2d(G_BASE), nn.ReLU(True),
            nn.ConvTranspose2d(G_BASE, 3, 4, 2, 1),
            nn.Tanh(),
        )

    def forward(self, z, labels):
        c = self.embed(labels)
        x = self.fc(torch.cat([z, c], 1)).view(z.size(0), -1, 4, 4)
        return self.deconv(x)


class Discriminator(nn.Module):
    """标准 ACGAN 条件：卷积提特征 → 拼接类别嵌入 → adv/cls 双头。"""

    def __init__(self):
        super().__init__()
        self.embed = nn.Embedding(NUM_CLASSES, EMB_DIM)
        self.conv = nn.Sequential(
            nn.Conv2d(3, D_BASE, 4, 2, 1), nn.LeakyReLU(0.2, True),
            nn.Conv2d(D_BASE, D_BASE * 2, 4, 2, 1), nn.BatchNorm2d(D_BASE * 2), nn.LeakyReLU(0.2, True),
            nn.Conv2d(D_BASE * 2, D_BASE * 4, 4, 2, 1), nn.BatchNorm2d(D_BASE * 4), nn.LeakyReLU(0.2, True),
            nn.Conv2d(D_BASE * 4, D_BASE * 8, 4, 2, 1), nn.BatchNorm2d(D_BASE * 8), nn.LeakyReLU(0.2, True),
        )
        feat_dim = D_BASE * 8 * 8 * 8
        self.adv = nn.Linear(feat_dim + EMB_DIM, 1)
        self.cls = nn.Linear(feat_dim + EMB_DIM, NUM_CLASSES)

    def forward(self, x, labels):
        h = self.conv(x).view(x.size(0), -1)
        e = self.embed(labels)
        return self.adv(torch.cat([h, e], 1)).squeeze(1), self.cls(torch.cat([h, e], 1))


class SmallImageFolder(Dataset):
    def __init__(self, root: Path, max_per_class: int = 120):
        self.items = []
        tf = transforms.Compose([
            transforms.Resize((IMG_SIZE_GAN, IMG_SIZE_GAN)),
            transforms.ToTensor(),
            transforms.Normalize([0.5] * 3, [0.5] * 3),
        ])
        for cls, idx in {c: i for i, c in enumerate(CLASS_NAMES)}.items():
            d = root / "train" / cls
            if not d.exists():
                continue
            files = sorted(list(d.glob("*.png")) + list(d.glob("*.jpg")))[:max_per_class]
            self.items += [(tf(Image.open(p).convert("RGB")), idx) for p in files]

    def __len__(self):
        return len(self.items)

    def __getitem__(self, i):
        return self.items[i]


def train_v2(epochs: int, gen_per_class: int) -> None:
    torch.manual_seed(RANDOM_SEED)
    ds = SmallImageFolder(ORGANIZED_DIR)
    if len(ds) == 0:
        print(f"[错误] {ORGANIZED_DIR}/train 无数据")
        sys.exit(1)

    # 类均衡采样：权重 = 1/该类样本数
    counts = Counter(idx for _, idx in ds.items)
    weights = [1.0 / counts[idx] for _, idx in ds.items]
    sampler = WeightedRandomSampler(weights, num_samples=len(ds), replacement=True)
    loader = DataLoader(ds, batch_size=BATCH_SIZE, sampler=sampler,
                        num_workers=0, drop_last=True)
    print(f"GAN-v2 训练数据 {len(ds)} 张，类分布 {dict(counts)}，设备 {DEVICE}，采样器类均衡")

    G = Generator().to(DEVICE)
    D = Discriminator().to(DEVICE)
    with torch.no_grad():
        probe_z = torch.randn(2, Z_DIM, device=DEVICE)
        probe_y = torch.randint(0, NUM_CLASSES, (2,), device=DEVICE)
        probe_x = torch.randn(2, 3, IMG_SIZE_GAN, IMG_SIZE_GAN, device=DEVICE)
        assert G(probe_z, probe_y).shape == probe_x.shape
        D(probe_x, probe_y)
    g_opt = torch.optim.Adam(G.parameters(), lr=LR_G, betas=(0.5, 0.999))
    d_opt = torch.optim.Adam(D.parameters(), lr=LR_D, betas=(0.5, 0.999))
    adv_criterion = nn.BCEWithLogitsLoss()
    cls_criterion = nn.CrossEntropyLoss()

    progress_dir = EXPERIMENTS_DIR / "gan_progress"
    progress_dir.mkdir(parents=True, exist_ok=True)
    csv_path = progress_dir / "v2_losses.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["epoch", "d_real", "d_fake", "g_adv", "g_cls"])

    for epoch in range(1, epochs + 1):
        s_dr = s_df = s_ga = s_gc = 0.0
        for x, y in loader:
            x, y = x.to(DEVICE), y.to(DEVICE)
            b = x.size(0)
            real_t = torch.full((b,), REAL_SMOOTH, device=DEVICE)
            fake_t = torch.zeros(b, device=DEVICE)
            x_noisy = x + D_NOISE_STD * torch.randn_like(x)

            # D
            d_opt.zero_grad()
            r_adv, r_cls = D(x_noisy, y)
            d_real = adv_criterion(r_adv, real_t) + cls_criterion(r_cls, y)
            z = torch.randn(b, Z_DIM, device=DEVICE)
            y_rand = torch.randint(0, NUM_CLASSES, (b,), device=DEVICE)
            fake = G(z, y_rand)
            f_adv, f_cls = D(fake.detach(), y_rand)
            d_fake = adv_criterion(f_adv, fake_t) + cls_criterion(f_cls, y_rand)
            (d_real + d_fake).backward()
            d_opt.step()

            # G
            g_opt.zero_grad()
            z = torch.randn(b, Z_DIM, device=DEVICE)
            y_rand = torch.randint(0, NUM_CLASSES, (b,), device=DEVICE)
            fake = G(z, y_rand)
            g_adv, g_cls = D(fake, y_rand)
            g_adv_l = adv_criterion(g_adv, real_t)
            g_cls_l = cls_criterion(g_cls, y_rand)
            (g_adv_l + g_cls_l).backward()
            g_opt.step()

            s_dr += d_real.item(); s_df += d_fake.item()
            s_ga += g_adv_l.item(); s_gc += g_cls_l.item()

        n = max(len(loader), 1)
        with open(csv_path, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow([epoch, f"{s_dr/n:.4f}", f"{s_df/n:.4f}", f"{s_ga/n:.4f}", f"{s_gc/n:.4f}"])

        if epoch % 5 == 0 or epoch == 1:
            print(f"[GAN-v2] epoch {epoch:3d}/{epochs}  d_real {s_dr/n:.3f}  d_fake {s_df/n:.3f}  "
                  f"g_adv {s_ga/n:.3f}  g_cls {s_gc/n:.3f}")

        # 每 20 epoch 保存生成样本（观察演进）
        if epoch % 20 == 0:
            sample_dir = progress_dir / f"v2_epoch_{epoch:03d}"
            sample_dir.mkdir(parents=True, exist_ok=True)
            G.eval()
            with torch.no_grad():
                for cls_idx in range(NUM_CLASSES):
                    z = torch.randn(1, Z_DIM, device=DEVICE)
                    y = torch.tensor([cls_idx], device=DEVICE)
                    img = (G(z, y).squeeze(0).cpu() + 1) / 2
                    transforms.ToPILImage()(img).save(sample_dir / f"{CLASS_NAMES[cls_idx]}.png")
            G.train()

    CHECKPOINTS_DIR.mkdir(parents=True, exist_ok=True)
    torch.save(G.state_dict(), CHECKPOINTS_DIR / "acgan_g_v2.pth")
    torch.save(D.state_dict(), CHECKPOINTS_DIR / "acgan_d_v2.pth")

    # 生成 v2 增强图（每类 gen_per_class 张）
    G.eval()
    out_root = EXPERIMENTS_DIR / "augmented_v2"
    count = 0
    with torch.no_grad():
        for cls_idx in range(NUM_CLASSES):
            cls_dir = out_root / CLASS_NAMES[cls_idx]
            cls_dir.mkdir(parents=True, exist_ok=True)
            for i in range(gen_per_class):
                z = torch.randn(1, Z_DIM, device=DEVICE)
                y = torch.tensor([cls_idx], device=DEVICE)
                img = (G(z, y).squeeze(0).cpu() + 1) / 2
                transforms.ToPILImage()(img).save(cls_dir / f"gan_{i:04d}.png")
                count += 1
    print(f"✅ 生成 {count} 张合成图 -> {out_root}")
    print(f"loss 曲线: {csv_path}")
    print("评估质量：python gan_quality.py --root augmented_v2 --out gan_quality_v2.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=200)
    parser.add_argument("--gen_per_class", type=int, default=100)
    args = parser.parse_args()
    train_v2(args.epochs, args.gen_per_class)
