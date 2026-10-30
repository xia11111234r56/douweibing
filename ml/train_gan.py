"""ACGAN 数据增强：按类生成合成病害图，扩充小样本训练集。

用法（ml/ 目录下）：
    python train_gan.py                    # 训练并生成，默认每类 100 张
    python train_gan.py --epochs 200 --gen_per_class 200

产物：
    checkpoints/acgan_g.pth / acgan_d.pth
    experiments/augmented/{类名}/gan_000.png ...

A/B 对比见 ablation.py。
注意：小样本 GAN 易模式崩溃，效果用 FID + 下游分类提升验证，如实报告。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image
from torch.utils.data import DataLoader, Dataset
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
    WORKERS,
)

Z_DIM = 100
G_BASE = 64
D_BASE = 64
# DCGAN 建议 G:D 学习率 2:1；小样本下降低 D 更新幅度缓解 D 主导
LR_G, LR_D = 2e-4, 1e-4
# 真实标签平滑：真实样本标 0.9 而非 1.0，防止 D 过强
REAL_SMOOTH = 0.9
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


class Generator(nn.Module):
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
            # 4→8→16→32→64，再补一层 64→128 以匹配判别器输入分辨率
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
    def __init__(self):
        super().__init__()
        # 类别条件投影为 3 通道图，与 RGB 拼接成 6 通道输入
        self.embed = nn.Embedding(NUM_CLASSES, 3 * IMG_SIZE_GAN * IMG_SIZE_GAN)
        self.conv = nn.Sequential(
            nn.Conv2d(6, D_BASE, 4, 2, 1), nn.LeakyReLU(0.2, True),
            nn.Conv2d(D_BASE, D_BASE * 2, 4, 2, 1), nn.BatchNorm2d(D_BASE * 2), nn.LeakyReLU(0.2, True),
            nn.Conv2d(D_BASE * 2, D_BASE * 4, 4, 2, 1), nn.BatchNorm2d(D_BASE * 4), nn.LeakyReLU(0.2, True),
            nn.Conv2d(D_BASE * 4, D_BASE * 8, 4, 2, 1), nn.BatchNorm2d(D_BASE * 8), nn.LeakyReLU(0.2, True),
        )
        self.adv = nn.Linear(D_BASE * 8 * 8 * 8, 1)
        self.cls = nn.Linear(D_BASE * 8 * 8 * 8, NUM_CLASSES)

    def forward(self, x, labels):
        c = self.embed(labels).view(labels.size(0), 3, IMG_SIZE_GAN, IMG_SIZE_GAN)
        x = self.conv(torch.cat([x, c], 1))
        f = x.view(x.size(0), -1)
        return self.adv(f).squeeze(1), self.cls(f)


class SmallImageFolder(Dataset):
    """只加载每类前 max_per_class 张，控制训练集规模。"""

    def __init__(self, root: Path, max_per_class: int = 120):
        self.items = []
        tf = transforms.Compose([
            transforms.Resize((IMG_SIZE_GAN, IMG_SIZE_GAN)),
            transforms.CenterCrop(IMG_SIZE_GAN),
            transforms.ToTensor(),
            transforms.Normalize([0.5] * 3, [0.5] * 3),
        ])
        for cls, idx in CLASS_NAME_TO_IDX.items():
            d = root / "train" / cls
            if not d.exists():
                continue
            files = sorted(list(d.glob("*.png")) + list(d.glob("*.jpg")))[:max_per_class]
            self.items += [(tf(Image.open(p).convert("RGB")), idx) for p in files]

    def __len__(self):
        return len(self.items)

    def __getitem__(self, i):
        return self.items[i]


CLASS_NAME_TO_IDX = {c: i for i, c in enumerate(CLASS_NAMES)}


def train_gan(epochs: int, gen_per_class: int) -> None:
    torch.manual_seed(RANDOM_SEED)
    ds = SmallImageFolder(ORGANIZED_DIR)
    if len(ds) == 0:
        print(f"[错误] {ORGANIZED_DIR}/train 无数据，请先 prepare_data")
        sys.exit(1)
    print(f"GAN 训练数据 {len(ds)} 张，设备 {DEVICE}")

    # 数据集已全部加载为内存 tensor，num_workers=0 避免子进程每 epoch 重新解码大图
    loader = DataLoader(ds, batch_size=BATCH_SIZE, shuffle=True,
                        drop_last=True, num_workers=0)
    G = Generator().to(DEVICE)
    D = Discriminator().to(DEVICE)
    # 形状自检：G 输出必须与真实图同分辨率，避免上采样层数不匹配
    with torch.no_grad():
        probe_z = torch.randn(2, Z_DIM, device=DEVICE)
        probe_y = torch.randint(0, NUM_CLASSES, (2,), device=DEVICE)
        probe_x = torch.randn(2, 3, IMG_SIZE_GAN, IMG_SIZE_GAN, device=DEVICE)
        assert G(probe_z, probe_y).shape == probe_x.shape, (
            f"G 输出 {tuple(G(probe_z, probe_y).shape)} ≠ 输入 {tuple(probe_x.shape)}"
        )
        D(probe_x, probe_y)
    g_opt = torch.optim.Adam(G.parameters(), lr=LR_G, betas=(0.5, 0.999))
    d_opt = torch.optim.Adam(D.parameters(), lr=LR_D, betas=(0.5, 0.999))
    adv_criterion = nn.BCEWithLogitsLoss()
    cls_criterion = nn.CrossEntropyLoss()

    for epoch in range(epochs):
        for x, y in loader:
            x, y = x.to(DEVICE), y.to(DEVICE)
            b = x.size(0)
            real_t = torch.full((b,), REAL_SMOOTH, device=DEVICE)
            fake_t = torch.zeros(b, device=DEVICE)

            # ---- D：真实损失 + 假样本损失 + 分类损失 ----
            d_opt.zero_grad()
            r_adv, r_cls = D(x, y)
            d_real = adv_criterion(r_adv, real_t) + cls_criterion(r_cls, y)

            z = torch.randn(b, Z_DIM, device=DEVICE)
            y_rand = torch.randint(0, NUM_CLASSES, (b,), device=DEVICE)
            fake = G(z, y_rand)
            f_adv, f_cls = D(fake.detach(), y_rand)
            d_fake = adv_criterion(f_adv, fake_t) + cls_criterion(f_cls, y_rand)
            d_loss = d_real + d_fake
            d_loss.backward()
            d_opt.step()

            # ---- G：欺骗 D + 分类正确 ----
            g_opt.zero_grad()
            z = torch.randn(b, Z_DIM, device=DEVICE)
            y_rand = torch.randint(0, NUM_CLASSES, (b,), device=DEVICE)
            fake = G(z, y_rand)
            g_adv, g_cls = D(fake, y_rand)
            g_loss = adv_criterion(g_adv, real_t) + cls_criterion(g_cls, y_rand)
            g_loss.backward()
            g_opt.step()

        if (epoch + 1) % 20 == 0:
            print(f"[GAN] epoch {epoch + 1}/{epochs}  D {d_loss.item():.3f}  G {g_loss.item():.3f}")

    CHECKPOINTS_DIR.mkdir(parents=True, exist_ok=True)
    torch.save(G.state_dict(), CHECKPOINTS_DIR / "acgan_g.pth")
    torch.save(D.state_dict(), CHECKPOINTS_DIR / "acgan_d.pth")

    # ---- 生成 ----
    G.eval()
    out_root = EXPERIMENTS_DIR / "augmented"
    count = 0
    with torch.no_grad():
        for cls_idx in range(NUM_CLASSES):
            cls_dir = out_root / CLASS_NAMES[cls_idx]
            cls_dir.mkdir(parents=True, exist_ok=True)
            for i in range(gen_per_class):
                z = torch.randn(1, Z_DIM, device=DEVICE)
                y = torch.tensor([cls_idx], device=DEVICE)
                img = (G(z, y).squeeze(0).cpu() + 1) / 2  # [3,H,W]
                pil = transforms.ToPILImage()(img)
                pil.save(cls_dir / f"gan_{i:04d}.png")
                count += 1
    print(f"✅ 生成 {count} 张合成图 -> {out_root}")
    print("下一步：python ablation.py 做 A/B 对比")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=200)
    parser.add_argument("--gen_per_class", type=int, default=100)
    args = parser.parse_args()
    train_gan(args.epochs, args.gen_per_class)
