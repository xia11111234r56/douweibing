"""模型训练配置：路径、类别、超参数。"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"               # 用户放入的原始图（文件夹名=类别名或别名）
ORGANIZED_DIR = DATA_DIR / "organized"   # prepare_data 整理后的 train/val/test
PENDING_DIR = DATA_DIR / "pending_label" # 待标注池（绿豆_未知/邢台等，模型辅助标注）
PUBLIC_DIR = DATA_DIR / "public"         # PlantVillage / Mendeley 公开数据（预训练）
EXPERIMENTS_DIR = ROOT / "experiments"   # 消融实验/指标输出
CHECKPOINTS_DIR = ROOT / "checkpoints"
# 导出 ONNX 的目标位置（后端模型目录）
BACKEND_MODELS_DIR = Path(__file__).resolve().parent.parent / "backend" / "models"

# 识别原图目录（纠错再训练取图用；与 backend/config.py RECOGNITION_DIR 同址：
# 本地 d:\dc2\data\recognitions，生产 /opt/dc2/data/recognitions 用环境变量覆盖）
RECOGNITION_DIR = Path(os.getenv("RECOGNITION_DIR", str(ROOT.parent / "data" / "recognitions")))

# 按实际数据重构的分类体系（2026-08-17 定稿）：真实绿豆田间数据 train 共 10 类。
# 待标注池（绿豆_未知/邢台）与其它豆种（芸豆/小豆）暂不入训练分类器。
# 注意：后端 DISEASES 种子知识库目前还是旧 7 类，M1 后端改造时同步替换。
CLASS_NAMES = [
    "健康",
    "晕疫病",          # 旧称"云疫病"，本批数据文件夹用"晕疫病"，为标准名
    "炭疽叶斑病",
    "轮纹叶斑病",
    "枯萎病",
    "病毒病",
    "细菌性疫病",
    "叶腐病",
    "细菌性萎蔫",
    "虫食",
]

# 用户原始文件夹名 → 标准类名（标注/重命名时宽容处理）
CLASS_ALIASES = {
    # 健康
    "jiankang": "健康", "健康": "健康", "healthy": "健康", "00": "健康", "0": "健康",
    # 晕疫病
    "01yunyibing": "晕疫病", "01 晕疫病": "晕疫病", "晕疫病": "晕疫病",
    "云疫病": "晕疫病", "halo_blight": "晕疫病", "01": "晕疫病", "1": "晕疫病",
    # 炭疽叶斑病
    "02tanjuyebanbing": "炭疽叶斑病", "02 炭疽叶斑病": "炭疽叶斑病", "炭疽叶斑病": "炭疽叶斑病",
    "炭疽病": "炭疽叶斑病", "anthracnose": "炭疽叶斑病", "02": "炭疽叶斑病", "2": "炭疽叶斑病",
    # 轮纹叶斑病
    "03lunwenyebanbing": "轮纹叶斑病", "03 轮纹叶斑病": "轮纹叶斑病", "轮纹叶斑病": "轮纹叶斑病",
    "leaf_spot": "轮纹叶斑病", "03": "轮纹叶斑病", "3": "轮纹叶斑病",
    # 枯萎病
    "04kuweibing": "枯萎病", "04 枯萎病": "枯萎病", "枯萎病": "枯萎病",
    "fusarium": "枯萎病", "04": "枯萎病", "4": "枯萎病",
    # 病毒病
    "05bingdubing": "病毒病", "05 病毒病": "病毒病", "病毒病": "病毒病",
    "virus": "病毒病", "05": "病毒病", "5": "病毒病",
    # 细菌性疫病
    "06xijunxingyibing": "细菌性疫病", "06 细菌性疫病": "细菌性疫病", "细菌性疫病": "细菌性疫病",
    "bacterial_blight": "细菌性疫病", "06": "细菌性疫病", "6": "细菌性疫病",
    # 叶腐病
    "07yefubing": "叶腐病", "07 叶腐病": "叶腐病", "叶腐病": "叶腐病",
    "07": "叶腐病", "7": "叶腐病",
    # 细菌性萎蔫
    "08xijunxingweinian": "细菌性萎蔫", "08 细菌性萎蔫": "细菌性萎蔫", "细菌性萎蔫": "细菌性萎蔫",
    "08": "细菌性萎蔫", "8": "细菌性萎蔫",
    # 虫食
    "15chongshi": "虫食", "15 虫蚀": "虫食", "虫食": "虫食", "虫蚀": "虫食",
    "15": "虫食",
}

# 数据划分
TRAIN_RATIO, VAL_RATIO, TEST_RATIO = 0.7, 0.15, 0.15
RANDOM_SEED = 42

NUM_CLASSES = len(CLASS_NAMES)
IMG_SIZE_GAN = 128  # GAN 生成分辨率（4GB 显存可用）

# 模型与训练超参数
IMG_SIZE = 224
# mobilenetv3_large / efficientnet_lite1（轻量，CPU 可推理）
MODEL_NAME = "mobilenetv3_large"
BATCH_SIZE = 32
WORKERS = 2                      # Windows spawn 加载：2 进程加速公开大数据集
EPOCHS_PUBLIC = 8                # 公开数据预训练（大规模，轮数精简）
EPOCHS_FINETUNE = 40             # 用户数据微调
LR = 1e-3
LR_FINETUNE = 1e-4
WEIGHT_DECAY = 1e-4
# 4GB 显存：mobilenetv3_large + 224 可跑；如 OOM 降 BATCH_SIZE 或换 lite
GRAD_ACCUM = 1

# 严重度阈值（病斑面积占比）——依据刘学敏等《大豆灰斑病叶部病斑严重度的分级标准》
# （<1%, 1-3, 3-6, 6-12, 12-25, >25% 七级）合并为健康/轻/中/重粗粒度（方案B）：
#   健康=0；轻=(0,6%]（文献1-3级）；中=(6%,25%]（4-5级）；重=(25%,100%)（6级）
SEVERITY_THRESHOLDS = {"轻": 0.06, "中": 0.25}

# 测试/验收
TARGET_ACCURACY = 0.85
