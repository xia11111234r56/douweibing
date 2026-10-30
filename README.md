# 「豆卫兵」绿豆病害智能诊断与精准防治系统

> 基于**多模态数据融合、动态知识图谱与 GAN 增强**的绿豆病害智能分级与精准防治系统

大创项目（编号 202510022402，北京市级）重做版。面向 2026.12 结题、2027 计算机设计大赛、国创赛/互联网+ 等。

## 架构

一套后端 + Web 平台为主 + 小程序薄端：

```
                 ┌─ Web 平台 (Vue3) ── 数据管理 / 多维检索 / 图片识别 / 知识图谱 / GIS种植信息 / 统计
后端统一 (FastAPI                    └─ 小程序薄端 ── 拍照识别（复用旧UI骨架，调用同一后端 API）
 + ONNX 推理 + 知识图谱
 + GIS 空间数据 + MySQL/SQLite)
                 └─ 模型训练管线（PyTorch）── 分类 + 深度严重度 + GAN增强（离线）
```

## 目录结构

```
backend/   FastAPI 后端（识别/检索/管理/图谱/GIS/统计 API + 数据库）
ml/        模型训练管线（分类 / 严重度 / ACGAN增强 / 消融实验 / 辅助标注）
web/       Vue3 Web 平台
miniapp/   微信小程序薄端
docs/      功能模块文档 / 数据库设计 / 结题对照 / 数据来源
docs/paper/   论文初稿
docs/软著/    软著材料（申请信息 + 源程序前后30页提取脚本与产物）
scripts/   公开数据下载/空间数据入库脚本
data/      空间数据（GeoJSON/FAOSTAT/WorldClim）与图片素材
```

## 快速开始

```bash
# 后端
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m app.data.seed     # 建表 + 灌入知识库种子数据
uvicorn app.main:app --port 8000
# 打开 http://127.0.0.1:8000/docs

# 前端（需先起后端）
cd web
npm install --cache "D:\temp\npm_cache"
npm run dev
```

## 当前进度（2026-08-18）

- 分类：MobileNetV3-Large 两阶段迁移。生产模型 = **GAN 增强 + 真实虫食补充版（B）**，40 epoch。固定 89 张测试集多 seed 复现 **mean 0.823 ± 0.027**（4 seed：0.843/0.843/0.820/0.787，`experiments/seed_sweep.json`）——单点 0.8315 不可复现，CUDA 非确定性 ±1–2 张。已部署 B 重评估（统一预处理协议后与训练评估一致）：test89 **0.8315** / 178 张 **0.8483**，ONNX 与 torch 逐图 89/89 一致，推理一致性 1.0。**全量 5 折 CV（601 张真实图，保守估计）pooled 0.8519 ± 0.022**（`experiments/cv_report.json`）——真实图+生产配方整体泛化接近 85% 目标，89 张固定集 0.82–0.84 的低估源于评估集规模与覆盖不足
- 严重度：深度模型（mobilenetv3 骨干 + 逻辑回归，179 张人工标注 5 折 CV 0.844，ONNX 部署）；颜色形态学面积比仅作回退
- 后端：识别/病害/检索/图谱/GIS/统计 API 全通，pytest 7 项通过
- 前端：Vue3 7 页 build 通过；小程序薄端调后端真实推理
- GAN：ACGAN 已训练并如实评估（生成图类判别性不足 0.10），消融 A/B（0.7865→0.8202）与生产 A/B（0.7753→0.8315）均已落盘。**注意**：多 seed 波动区间 ±0.027，单点差值方向成立但幅度引用须谨慎
- **部署与局限**：生产切 B 后，真实虫食识别率跨域测试 A 0%→B 100%（Mendeley caterpillar 251 张）；但 A/B 对 Mendeley healthy 均 0%（拍摄域偏移）——模型只对自家田间风格可靠，跨域泛化差，论文须如实写

## 关键文档

- [功能模块文档](docs/功能模块文档.md)
- [数据库设计](docs/数据库设计.md)
- [结题对照表](docs/结题对照.md)
- [数据来源与下载](docs/数据来源与下载.md)
