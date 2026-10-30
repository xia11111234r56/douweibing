r"""合并绿豆数据：新「豆类图片」+ 旧 dataset 独有原图 → ml/data/raw/，HEIC→JPG，按图去重。

规则：
- 去重键 = DSC\d+ | IMG_\d+_\d+ | 其余用完整基名
- 同键多文件：优先 .JPG/.jpg/.png，HEIC 仅当该键没有 JPG 时才转换
- 旧 dataset 只抢救「新文件夹没有的原图」，且优先取无 _gray/_rotated/_translated 后缀的原版
- 未知 / 邢台 → 待标注池；芸豆 / 小豆 → other_crops（暂不入训练分类器）
"""
import re
import sys
import shutil
from pathlib import Path
from collections import defaultdict

import pillow_heif
from PIL import Image

pillow_heif.register_heif_opener()

SRC_NEW = Path(r"D:\dc2\豆类图片\豆类图片")
SRC_OLD = Path(r"D:\BaiduNetdiskDownload\dataset\dataset")
DST_RAW = Path(r"D:\dc2\ml\data\raw")
DST_PENDING = Path(r"D:\dc2\ml\data\pending_label")
DST_OTHER = Path(r"D:\dc2\ml\data\other_crops")

ID_RE = re.compile(r"^(DSC\d+|IMG_\d+_\d+)")


def img_id(fname: str) -> str:
    m = ID_RE.match(Path(fname).stem)
    return m.group(1) if m else Path(fname).stem


def is_aug(fname: str) -> bool:
    return "_gray" in fname or "_rotated" in fname or "_translated" in fname


def collect(folder: Path, recursive: bool = True) -> dict[str, list[Path]]:
    """返回 {img_id: [file_paths]}。"""
    files = list(folder.rglob("*") if recursive else folder.glob("*"))
    files = [f for f in files if f.is_file() and f.suffix.lower() in {".jpg", ".jpeg", ".png", ".heic"}]
    out = defaultdict(list)
    for f in files:
        out[img_id(f.name)].append(f)
    return out


def merge_id_maps(a: dict[str, list[Path]], b: dict[str, list[Path]]) -> dict[str, list[Path]]:
    """把 b 累积进 a（同键路径合并），不覆盖。"""
    for pid, paths in b.items():
        a[pid].extend(paths)
    return a


def pick_best(paths: list[Path]) -> Path:
    """同键多文件取最好：JPG/PNG 优先（保 EXIF），HEIC 垫底。"""
    rank = {".jpg": 0, ".jpeg": 0, ".png": 1, ".heic": 2}
    return min(paths, key=lambda p: (rank.get(p.suffix.lower(), 5), p.name))


def convert_heic_to_jpg(src: Path, dst: Path) -> None:
    """HEIC → JPG，尽量携带 EXIF。"""
    exif = None
    try:
        heif = pillow_heif.open_heif(src)
        exif = heif.info.get("exif")
    except Exception:
        pass
    img = Image.open(src)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    kwargs = {}
    if exif:
        try:
            kwargs["exif"] = exif
        except Exception:
            pass
    img.save(dst, "JPEG", quality=95, **kwargs)


def copy_img(src: Path, dst_dir: Path) -> Path | None:
    """把 src 复制到 dst_dir：HEIC 转 JPG，其余原样。返回落盘路径。"""
    dst_dir.mkdir(parents=True, exist_ok=True)
    if src.suffix.lower() == ".heic":
        dst = dst_dir / (src.stem + ".jpg")
        if not dst.exists():
            try:
                convert_heic_to_jpg(src, dst)
            except Exception as e:
                print(f"  ⚠️ HEIC 转换失败 {src.name}: {e}")
                return None
        return dst
    dst = dst_dir / src.name
    if not dst.exists():
        shutil.copy2(src, dst)
    return dst


# 新文件夹绿豆：中文目录名 → 标准类名；None = 待标注池
NEW_CLASS = {
    "01 晕疫病": "晕疫病", "02 炭疽叶斑病": "炭疽叶斑病", "03 轮纹叶斑病": "轮纹叶斑病",
    "04 枯萎病": "枯萎病", "05 病毒病": "病毒病", "06 细菌性疫病": "细菌性疫病",
    "07 叶腐病": "叶腐病", "08 细菌性萎蔫": "细菌性萎蔫", "15 虫蚀": "虫食",
    "健康": "健康", "未知": None,
}
# 旧 dataset：拼音目录名 → 标准类名；None = 待标注池
OLD_CLASS = {
    "01yunyibing": "晕疫病", "02tanjuyebanbing": "炭疽叶斑病", "03lunwenyebanbing": "轮纹叶斑病",
    "04kuweibing": "枯萎病", "05bingdubing": "病毒病", "06xijunxingyibing": "细菌性疫病",
    "07yefubing": "叶腐病", "08xijunxingweinian": "细菌性萎蔫", "15chongshi": "虫食",
    "jiankang": "健康", "weizhi": None,
}

stats = defaultdict(lambda: {"new": 0, "rescue": 0, "dup": 0, "heic": 0})


def merge_class(new_ids: dict, old_ids: dict, cls: str, *, is_pending: bool):
    """合并一个类：新图为底，旧图只补独有。"""
    dest = DST_PENDING / f"绿豆_未知" if is_pending else DST_RAW / cls
    dest.mkdir(parents=True, exist_ok=True)
    st = stats["待标注池" if is_pending else cls]

    for pid, paths in new_ids.items():
        best = pick_best(paths)
        st["new"] += 1
        if best.suffix.lower() == ".heic":
            st["heic"] += 1
        copy_img(best, dest)

    for pid, paths in old_ids.items():
        if pid in new_ids:  # 新图已覆盖，跳过（旧图不补）
            st["dup"] += 1
            continue
        # 旧图独有：优先取无增强后缀的原版
        base = [p for p in paths if not is_aug(p.name)]
        pick = base[0] if base else min(paths, key=lambda p: (is_aug(p.name), len(p.name)))
        st["rescue"] += 1
        copy_img(pick, dest)


def main():
    new_root = SRC_NEW / "绿豆"
    print("=== 1/4 合并绿豆训练类（新图 + 旧独有）===")
    for cn, cls in NEW_CLASS.items():
        new_ids = collect(new_root / cn)
        old_ids: dict[str, list[Path]] = defaultdict(list)
        old_folder = "weizhi" if cls is None else [k for k, v in OLD_CLASS.items() if v == cls][0]
        for sp in ("train", "val", "test"):
            merge_id_maps(old_ids, collect(SRC_OLD / sp / old_folder, recursive=False))
        merge_class(new_ids, old_ids, cls, is_pending=(cls is None))

    print("=== 2/4 邢台未标注 → 待标注池 ===")
    xt_dir = new_root.parent / "绿豆图片 0617 邢台采集" / "0617 邢台 手机拍" / "0617 邢台 手机拍"
    xt_dst = DST_PENDING / "邢台_20260617"
    xt_dst.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in sorted(xt_dir.glob("*")):
        if f.suffix.lower() == ".zip":
            continue
        if f.is_file() and not (xt_dst / f.name).exists():
            shutil.copy2(f, xt_dst / f.name)
            n += 1
    print(f"  邢台复制 {n} 个文件")

    print("=== 3/4 芸豆 / 小豆 → other_crops（暂不入训练）===")
    for crop in ("芸豆", "小豆锈病"):
        src = SRC_NEW / crop
        if not src.exists():
            continue
        for f in src.rglob("*"):
            if f.is_file() and f.suffix.lower() in {".jpg", ".jpeg", ".png", ".heic"}:
                rel = f.relative_to(src)
                copy_img(f, DST_OTHER / crop / rel.parent)

    print("=== 4/4 汇总 ===")
    print(f"{'类':<10} {'新图':>4} {'旧独有':>5} {'重复跳过':>6} {'HEIC':>4}")
    total_new = total_rescue = 0
    for k in sorted(stats, key=lambda x: (x != "待标注池", x)):
        s = stats[k]
        total_new += s["new"]; total_rescue += s["rescue"]
        print(f"{k:<10} {s['new']:>4} {s['rescue']:>5} {s['dup']:>6} {s['heic']:>4}")
    print(f"训练集合计：新 {total_new} + 旧独有 {total_rescue} = {total_new + total_rescue} 张")
    print("落地目录：")
    for d in (DST_RAW, DST_PENDING, DST_OTHER):
        if d.exists():
            nfiles = sum(1 for _ in d.rglob("*") if _.is_file())
            print(f"  {d}  ({nfiles} 文件)")


if __name__ == "__main__":
    main()
