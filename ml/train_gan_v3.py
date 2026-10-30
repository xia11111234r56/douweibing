"""ACGAN v3（架构升级 + 收窄训练）：WGAN-GP + 投影判别器 + 类别条件 BN + 谱归一化。

背景（v2 诊断，均来自真实训练曲线/评估产物）：
- v2 的 g_cls 从 0.663 崩到 ~0.004：生成器找到了判别器分类分支的「捷径」，
  能骗过分类头但骗不过真假头（g_adv 卡在 ~2.0），所以生成图「有叶子但类特征
  没学出来」——gan_quality_v2 里 10 类仅 2 类一致率 1.0，整体一致率 0.20
  （随机基线 0.10），平均置信度却高达 0.878（高置信但判错）。
- v2 训练图 335 张，10 类里 6 类 ≤7 张（叶腐1/枯萎2/细菌性疫病2/萎蔫6/虫食1/
  轮纹7），小类 GAN 只能背诵那 1~2 张样例，无法学到类别特征，硬训没有统计意义。

v3 四项针对性改造：
1. 对抗头改 WGAN-GP：判别器输出无界 critic 分数 + 梯度惩罚，D 不会饱和、梯度
   平稳（v2 的 BCE 让 g_adv 停在 ~2.0 无法继续优化）。
2. 投影判别器（Miyato et al. 2018）：类别条件改为「特征向量与类别向量内积」，
   去掉 v1/v2 的「嵌入拼接」捷径，D 无法靠类别信号走短路。
3. 生成器类别条件批归一化 CondBN：每个转置卷积层后用类别嵌入调制 γ/β，强制
   逐层注入类别信息（v2 只在 fc 拼一次，深层特征不含类信息）。
4. 谱归一化（G/D 卷积与线性层）：进一步稳定训练，替代 v2 的判别器输入噪声。

收窄（诚实）：只训真实样本 ≥ MIN_SAMPLES 的类——健康(46)/晕疫病(120)/
  炭疽叶斑病(120)/病毒病(30)。小类交给传统增强兜底，不硬训。

产物（不覆盖 v1/v2，论文现有数字不受影响）：
    checkpoints/acgan_g_v3.pth / acgan_d_v3.pth
    experiments/augmented_v3/{类名}/gan_*.png   （每类 gen_per_class 张）
    experiments/gan_progress/v3_epoch_XXX/...    （每 20 epoch 中间样本）
    experiments/gan_progress/v3_losses.csv

用法（ml/ 下）：python train_gan_v3.py [--epochs 200] [--gen_per_class 100] [--n_critic 3]
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
import torch.nn.functional as F
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
EMB_DIM = 128
G_BASE = 64
D_BASE = 64
LR = 1e-4                     # WGAN-GP 推荐
LAMBDA_GP = 10                # 梯度惩罚系数（WGAN-GP 论文默认）
CLS_LAMBDA = 1.0              # 分类分支权重
MIN_SAMPLES = 30              # 只训真实样本 ≥ 30 张的类
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


class CondBN2d(nn.Module):
    """类别条件批归一化：类别嵌入经线性层调制每个通道的 γ/β。"""

    def __init__(self, n_feat):
        super().__init__()
        self.bn = nn.BatchNorm2d(n_feat, affine=False)
        self.gamma = nn.Linear(EMB_DIM, n_feat)
        self.beta = nn.Linear(EMB_DIM, n_feat)

    def forward(self, x, e):
        x = self.bn(x)
        gamma = self.gamma(e).view(-1, self.bn.num_features, 1, 1)
        beta = self.beta(e).view(-1, self.bn.num_features, 1, 1)
        return x * gamma + beta


class Generator(nn.Module):
    """类别条件生成器：每层转置卷积后用 CondBN 注入类别（v3 关键改动之一）。"""

    def __init__(self):
        super().__init__()
        self.embed = nn.Embedding(NUM_CLASSES, EMB_DIM)
        self.fc = nn.Sequential(
            nn.utils.spectral_norm(nn.Linear(Z_DIM + EMB_DIM, G_BASE * 8 * 4 * 4)),
            nn.ReLU(True),
        )
        self.deconv1 = nn.utils.spectral_norm(nn.ConvTranspose2d(G_BASE * 8, G_BASE * 4, 4, 2, 1))
        self.bn1 = CondBN2d(G_BASE * 4)
        self.deconv2 = nn.utils.spectral_norm(nn.ConvTranspose2d(G_BASE * 4, G_BASE * 2, 4, 2, 1))
        self.bn2 = CondBN2d(G_BASE * 2)
        self.deconv3 = nn.utils.spectral_norm(nn.ConvTranspose2d(G_BASE * 2, G_BASE, 4, 2, 1))
        self.bn3 = CondBN2d(G_BASE)
        self.deconv4 = nn.utils.spectral_norm(nn.ConvTranspose2d(G_BASE, G_BASE, 4, 2, 1))
        self.bn4 = CondBN2d(G_BASE)
        self.deconv5 = nn.utils.spectral_norm(nn.ConvTranspose2d(G_BASE, 3, 4, 2, 1))

    def forward(self, z, labels):
        e = self.embed(labels)
        x = self.fc(torch.cat([z, e], 1)).view(z.size(0), -1, 4, 4)
        x = F.relu(self.bn1(self.deconv1(x), e), True)
        x = F.relu(self.bn2(self.deconv2(x), e), True)
        x = F.relu(self.bn3(self.deconv3(x), e), True)
        x = F.relu(self.bn4(self.deconv4(x), e), True)
        return torch.tanh(self.deconv5(x))


class Discriminator(nn.Module):
    """投影判别器（Miyato et al. 2018）+ 谱归一化 + 分类分支。

    critic 输出无界（WGAN），类别条件通过「特征与类别向量内积」实现，
    而不是 v1/v2 的「嵌入拼接输入图/拼接特征」（捷径来源）。
    """

    def __init__(self):
        super().__init__()
        self.conv = nn.Sequential(
            nn.utils.spectral_norm(nn.Conv2d(3, D_BASE, 4, 2, 1)), nn.LeakyReLU(0.2, True),
            nn.utils.spectral_norm(nn.Conv2d(D_BASE, D_BASE * 2, 4, 2, 1)), nn.LeakyReLU(0.2, True),
            nn.utils.spectral_norm(nn.Conv2d(D_BASE * 2, D_BASE * 4, 4, 2, 1)), nn.LeakyReLU(0.2, True),
            nn.utils.spectral_norm(nn.Conv2d(D_BASE * 4, D_BASE * 8, 4, 2, 1)), nn.LeakyReLU(0.2, True),
        )
        self.embed = nn.utils.spectral_norm(nn.Linear(NUM_CLASSES, D_BASE * 8))
        self.phi = nn.utils.spectral_norm(nn.Linear(D_BASE * 8, D_BASE * 8))
        self.psi = nn.utils.spectral_norm(nn.Linear(D_BASE * 8, 1))
        self.cls = nn.utils.spectral_norm(nn.Linear(D_BASE * 8, NUM_CLASSES))

    def forward(self, x, labels):
        h = F.relu(self.conv(x))                       # [B, 512, 8, 8]
        h = h.mean(dim=(2, 3))                         # 全局平均池化 → [B, 512]
        emb = self.embed(F.one_hot(labels, NUM_CLASSES).float())  # [B, 512]
        adv = (self.phi(h) * emb).sum(dim=1, keepdim=True) + self.psi(h)  # [B, 1]
        return adv, self.cls(h)


class SmallImageFolder(Dataset):
    """只保留真实样本 ≥ MIN_SAMPLES 的类（诚实收窄）。"""

    def __init__(self, root: Path, max_per_class: int = 120):
        self.items = []
        self.train_classes = []
        tf = transforms.Compose([
            transforms.Resize((IMG_SIZE_GAN, IMG_SIZE_GAN)),
            transforms.ToTensor(),
            transforms.Normalize([0.5] * 3, [0.5] * 3),
        ])
        for cls in CLASS_NAMES:
            d = root / "train" / cls
            if not d.exists():
                continue
            files = sorted(list(d.glob("*.png")) + list(d.glob("*.jpg")))
            if len(files) < MIN_SAMPLES:
                print(f"[收窄] 跳过 {cls}（真实样本 {len(files)} < {MIN_SAMPLES}，GAN 只能背诵）")
                continue
            files = files[:max_per_class]
            idx = CLASS_NAMES.index(cls)
            self.items += [(tf(Image.open(p).convert("RGB")), idx) for p in files]
            self.train_classes.append(idx)

    def __len__(self):
        return len(self.items)

    def __getitem__(self, i):
        return self.items[i]


def gradient_penalty(D, x_real, x_fake, labels):
    """WGAN-GP：真实与生成样本插值点上 critic 梯度范数逼近 1。"""
    alpha = torch.rand(x_real.size(0), 1, 1, 1, device=x_real.device)
    interp = (alpha * x_real + (1 - alpha) * x_fake).requires_grad_(True)
    adv, _ = D(interp, labels)
    grads = torch.autograd.grad(
        outputs=adv, inputs=interp,
        grad_outputs=torch.ones_like(adv), create_graph=True)[0]
    return ((grads.norm(2, dim=1) - 1) ** 2).mean()


def train_v3(epochs: int, gen_per_class: int, n_critic: int) -> None:
    torch.manual_seed(RANDOM_SEED)
    ds = SmallImageFolder(ORGANIZED_DIR)
    if len(ds) == 0:
        print(f"[错误] {ORGANIZED_DIR}/train 无满足条件的类")
        sys.exit(1)

    counts = Counter(idx for _, idx in ds.items)
    weights = [1.0 / counts[idx] for _, idx in ds.items]
    sampler = WeightedRandomSampler(weights, num_samples=len(ds), replacement=True)
    loader = DataLoader(ds, batch_size=BATCH_SIZE, sampler=sampler,
                        num_workers=0, drop_last=True)
    trained = [CLASS_NAMES[i] for i in ds.train_classes]
    print(f"GAN-v3 训练 {len(ds)} 张，仅类 {trained}，类分布 {dict(counts)}，设备 {DEVICE}，n_critic={n_critic}")

    G = Generator().to(DEVICE)
    D = Discriminator().to(DEVICE)
    with torch.no_grad():
        probe_z = torch.randn(2, Z_DIM, device=DEVICE)
        probe_y = torch.randint(0, NUM_CLASSES, (2,), device=DEVICE)
        probe_x = torch.randn(2, 3, IMG_SIZE_GAN, IMG_SIZE_GAN, device=DEVICE)
        assert G(probe_z, probe_y).shape == probe_x.shape
        D(probe_x, probe_y)
    g_opt = torch.optim.Adam(G.parameters(), lr=LR, betas=(0.5, 0.999))
    d_opt = torch.optim.Adam(D.parameters(), lr=LR, betas=(0.5, 0.999))

    progress_dir = EXPERIMENTS_DIR / "gan_progress"
    progress_dir.mkdir(parents=True, exist_ok=True)
    csv_path = progress_dir / "v3_losses.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["epoch", "d_real_adv", "d_fake_adv", "gp", "g_adv", "g_cls"])

    for epoch in range(1, epochs + 1):
        s_dr = s_df = s_gp = s_ga = s_gc = 0.0
        for x, y in loader:
            x, y = x.to(DEVICE), y.to(DEVICE)
            b = x.size(0)
            z = torch.randn(b, Z_DIM, device=DEVICE)

            # ---- 判别器（critic）更新 n_critic 次 ----
            for _ in range(n_critic):
                d_opt.zero_grad()
                y_rand = torch.randint(0, NUM_CLASSES, (b,), device=DEVICE)
                with torch.no_grad():
                    fake = G(z, y_rand)
                real_adv, real_cls = D(x, y)
                fake_adv, fake_cls = D(fake, y_rand)
                gp = gradient_penalty(D, x, fake, y)
                d_adv = -(real_adv.mean() - fake_adv.mean()) + LAMBDA_GP * gp
                d_cls = F.cross_entropy(real_cls, y) + F.cross_entropy(fake_cls, y_rand)
                (d_adv + CLS_LAMBDA * d_cls).backward()
                d_opt.step()
                s_dr += real_adv.mean().item()
                s_df += fake_adv.mean().item()
                s_gp += gp.item()

            # ---- 生成器更新 1 次 ----
            g_opt.zero_grad()
            z = torch.randn(b, Z_DIM, device=DEVICE)
            y_rand = torch.randint(0, NUM_CLASSES, (b,), device=DEVICE)
            fake = G(z, y_rand)
            fake_adv, fake_cls = D(fake, y_rand)
            g_adv = -fake_adv.mean()
            g_cls = F.cross_entropy(fake_cls, y_rand)
            (g_adv + CLS_LAMBDA * g_cls).backward()
            g_opt.step()
            s_ga += g_adv.item()
            s_gc += g_cls.item()

        n = max(len(loader), 1)
        with open(csv_path, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow([epoch, f"{s_dr/n/n_critic:.4f}", f"{s_df/n/n_critic:.4f}",
                        f"{s_gp/n/n_critic:.4f}", f"{s_ga/n:.4f}", f"{s_gc/n:.4f}"])

        if epoch % 5 == 0 or epoch == 1:
            print(f"[GAN-v3] epoch {epoch:3d}/{epochs}  d_real {s_dr/n/n_critic:.3f}  "
                  f"d_fake {s_df/n/n_critic:.3f}  gp {s_gp/n/n_critic:.3f}  "
                  f"g_adv {s_ga/n:.3f}  g_cls {s_gc/n:.3f}")

        if epoch % 20 == 0:
            sample_dir = progress_dir / f"v3_epoch_{epoch:03d}"
            sample_dir.mkdir(parents=True, exist_ok=True)
            G.eval()
            with torch.no_grad():
                for cls_idx in ds.train_classes:
                    z = torch.randn(1, Z_DIM, device=DEVICE)
                    y = torch.tensor([cls_idx], device=DEVICE)
                    img = (G(z, y).squeeze(0).cpu() + 1) / 2
                    transforms.ToPILImage()(img).save(sample_dir / f"{CLASS_NAMES[cls_idx]}.png")
            G.train()

    CHECKPOINTS_DIR.mkdir(parents=True, exist_ok=True)
    torch.save(G.state_dict(), CHECKPOINTS_DIR / "acgan_g_v3.pth")
    torch.save(D.state_dict(), CHECKPOINTS_DIR / "acgan_d_v3.pth")

    # 生成 v3 增强图（只对训练的类）
    G.eval()
    out_root = EXPERIMENTS_DIR / "augmented_v3"
    count = 0
    with torch.no_grad():
        for cls_idx in ds.train_classes:
            cls_dir = out_root / CLASS_NAMES[cls_idx]
            cls_dir.mkdir(parents=True, exist_ok=True)
            for i in range(gen_per_class):
                z = torch.randn(1, Z_DIM, device=DEVICE)
                y = torch.tensor([cls_idx], device=DEVICE)
                img = (G(z, y).squeeze(0).cpu() + 1) / 2
                transforms.ToPILImage()(img).save(cls_dir / f"gan_{i:04d}.png")
                count += 1
    print(f"✅ 生成 {count} 张合成图 -> {out_root}（类：{trained}）")
    print(f"loss 曲线: {csv_path}")
    print("评估质量：python gan_quality.py --root augmented_v3 --out gan_quality_v3.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=200)
    parser.add_argument("--gen_per_class", type=int, default=100)
    parser.add_argument("--n_critic", type=int, default=3)
    args = parser.parse_args()
    train_v3(args.epochs, args.gen_per_class, args.n_critic)
