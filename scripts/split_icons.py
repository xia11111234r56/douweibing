"""拆分四合一.png 为 4 个透明底图标。

来源：d:\\dc2\\四合一.png（即梦AI 2x2 四宫格，暗绿底 + 亮色图标）
处理：
1. 四象限各自检测图标包围盒（背景分界在颜色距离 26，阈值用 27）
2. 右下象限排除即梦水印带（y>=1238 且 x>=1100），裁切后再把水印区 alpha 置 0
3. 暗绿背景 -> 透明（距离阈值）
4. 输出 RGBA PNG 到 miniapp/images/

映射：左上=病(放大镜叶片) 右上=科(书本) 左下=种(幼苗) 右下=答(机器人)
"""
from PIL import Image
import os

SRC = r"d:\dc2\四合一.png"
OUT_DIR = r"d:\dc2\miniapp\images"
QUADS = [
    ("feature-disease.png", 0, 0, 664, 664),
    ("feature-science.png", 664, 0, 1328, 664),
    ("feature-plant.png", 0, 664, 664, 1328),
    ("ai-avatar.png", 664, 664, 1328, 1328),
]
BG = (32, 39, 23)  # 背景暗绿
DIST_THRESH = 27
WM_BOX = (0, 1239, 1328, 1328)  # 即梦水印带：BR 象限底部 y>=1239（机器人底座到 y~1238 止，其下全为水印）

os.makedirs(OUT_DIR, exist_ok=True)


def dist(p):
    return ((p[0] - BG[0]) ** 2 + (p[1] - BG[1]) ** 2 + (p[2] - BG[2]) ** 2) ** 0.5


def is_bg(px):
    return dist(px) < DIST_THRESH


def find_bbox(im, x0, y0, x1, y1, skip_wm=False):
    xs, ys = [], []
    for yy in range(y0, y1, 2):
        for xx in range(x0, x1, 2):
            if skip_wm and WM_BOX[0] <= xx <= WM_BOX[2] and WM_BOX[1] <= yy <= WM_BOX[3]:
                continue
            if not is_bg(im.getpixel((xx, yy))):
                xs.append(xx)
                ys.append(yy)
    return (min(xs), min(ys), max(xs), max(ys))


def make_transparent(crop: Image.Image, origin, zero_wm=False) -> Image.Image:
    """距离阈值: 背景 -> alpha 0。可把原图坐标落在水印带的像素一并清透明。"""
    w, h = crop.size
    ox, oy = origin
    px = crop.convert("RGB")
    alpha = []
    for y in range(h):
        for x in range(w):
            p = px.getpixel((x, y))
            if zero_wm and WM_BOX[0] <= ox + x <= WM_BOX[2] and WM_BOX[1] <= oy + y <= WM_BOX[3]:
                alpha.append(0)
            elif dist(p) < DIST_THRESH:
                alpha.append(0)
            else:
                alpha.append(255)
    out = Image.new("RGBA", (w, h))
    out.putdata([(r, g, b, a) for (r, g, b), a in zip(px.getdata(), alpha)])
    return out


im = Image.open(SRC).convert("RGB")
for name, x0, y0, x1, y1 in QUADS:
    skip_wm = name.startswith("ai-avatar")
    bx0, by0, bx1, by1 = find_bbox(im, x0, y0, x1, y1, skip_wm=skip_wm)
    pad = 24
    left, top = max(x0, bx0 - pad), max(y0, by0 - pad)
    right, bottom = min(x1, bx1 + pad), min(y1, by1 + pad)
    crop = im.crop((left, top, right, bottom))
    out = make_transparent(crop, (left, top), zero_wm=skip_wm)
    path = os.path.join(OUT_DIR, name)
    out.save(path, "PNG")
    alpha = [a for _, _, _, a in out.getdata()]
    nz = sum(1 for a in alpha if a > 0)
    print(f"{name}: bbox=({bx0},{by0})-({bx1},{by1}) size={out.size} opaque%={nz / len(alpha):.1%}")
print("done")
