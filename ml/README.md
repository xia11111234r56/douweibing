# ML 训练管线

> 分类（MobileNetV3/EfficientNet）+ MobileSAM 严重度 + ACGAN 增强 + 消融实验。
> 产出**真实指标**，不编造（吸取上次"文档写 EfficientNet 实际是 ResNet"的教训）。

## 数据准备

```bash
# 1. 把已分类图片放入 ml/data/raw/{类名}/ （类名映射见 config.py CLASS_ALIASES）
# 2. 整理为 train/val/test
python scripts/prepare_data.py            # 实际执行
python scripts/prepare_data.py --dry-run  # 先看统计
```

## 训练流程

```bash
# 阶段1（可选）：公开数据预训练
#   把 PlantVillage / Mendeley 数据放入 ml/data/public/ 后执行
python train_classifier.py --stage public

# 阶段2：用户绿豆数据微调（核心）
python train_classifier.py --stage finetune --epochs 40

# 评估（准确率 / 混淆矩阵 / 一致性）
python evaluate.py

# 导出 ONNX -> backend/models/（后端推理用）
python export_onnx.py
```

## 严重度量化（MobileSAM）

```bash
# 下载 mobile_sam.pt 放入 ml/checkpoints/
python severity_sam.py <图片路径>     # 输出 病斑占比 + 严重度
```

## GAN 增强 + 消融（论文实验）

```bash
python train_gan.py --epochs 200 --gen_per_class 100   # 生成合成图
python ablation.py --epochs 30                          # A/B 对比：基线 vs +GAN
```

## 里程碑对照

| 里程碑 | 脚本 | 产出 |
|---|---|---|
| M1 识别闭环 | train_classifier / evaluate / export_onnx | classifier.onnx + eval_report.json |
| M1 严重度 | severity_sam | 病斑占比 → 轻/中/重 |
| M2 GAN+消融 | train_gan / ablation | augmented/ + ablation_report.json |

## 验收标准（docs/结题对照.md）

- 分类测试集准确率 ≥85%（混淆矩阵）
- 严重度经人工抽样验证
- 同一图多次推理结果一致
- GAN/多模态消融报告真实数据
