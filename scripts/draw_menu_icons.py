"""画「我的」页 4 个菜单图标（PIL 纯代码，无外部素材）。

配色与 badge 文字色一致（见 profile.wxss）：
  记(记录列表)  #2E7D32 绿
  关(关于/信息) #00796B 青
  馈(意见反馈)  #EF6C00 橙
  清(清除资料)  #5f6b72 灰
3x 超采样抗锯齿，输出 96x96 透明 PNG 到 miniapp/images/。
"""
from PIL import Image, ImageDraw
import os

OUT = r"d:\dc2\miniapp\images"
SS = 3          # 超采样倍数
SIZE = 96       # 输出边长
os.makedirs(OUT, exist_ok=True)


def draw(fn, painter):
    canvas = Image.new("RGBA", (SIZE * SS, SIZE * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(canvas)
    painter(d, SS)
    canvas = canvas.resize((SIZE, SIZE), Image.LANCZOS)
    canvas.save(os.path.join(OUT, fn), "PNG", optimize=True)
    print(fn, f"{os.path.getsize(os.path.join(OUT, fn))/1024:.1f}KB")


def clear(color, d, s):
    """用 alpha 0 擦除，实现镂空。"""
    pass  # 直接用 d.rectangle(fill=(0,0,0,0))


# 1. 记 - 识别记录：列表(圆点+三条横线)
def painter_records(d, s):
    c = "#2E7D32"
    for y in (24, 48, 72):
        d.ellipse([12 * s, (y - 7) * s, 26 * s, (y + 7) * s], fill=c)          # 圆点
        d.rounded_rectangle([38 * s, (y - 5) * s, 84 * s, (y + 5) * s], radius=5 * s, fill=c)
draw("menu-records.png", painter_records)


# 2. 关 - 关于：圆圈 + i
def painter_about(d, s):
    c = "#00796B"
    d.ellipse([12 * s, 12 * s, 84 * s, 84 * s], outline=c, width=8 * s)        # 外圈
    d.ellipse([41 * s, 24 * s, 55 * s, 38 * s], fill=c)                        # 点
    d.rounded_rectangle([42 * s, 46 * s, 54 * s, 72 * s], radius=6 * s, fill=c)  # 竖条
draw("menu-about.png", painter_about)


# 3. 馈 - 意见反馈：对话气泡(圆角矩形+左下尾)
def painter_feedback(d, s):
    c = "#EF6C00"
    d.rounded_rectangle([14 * s, 18 * s, 82 * s, 64 * s], radius=14 * s, fill=c)
    d.polygon([(30 * s, 60 * s), (50 * s, 60 * s), (26 * s, 82 * s)], fill=c)
draw("menu-feedback.png", painter_feedback)


# 4. 清 - 清除资料：垃圾桶
def painter_clear(d, s):
    c = "#5f6b72"
    d.rounded_rectangle([40 * s, 16 * s, 56 * s, 26 * s], radius=5 * s, fill=c)    # 提手
    d.rounded_rectangle([28 * s, 26 * s, 68 * s, 35 * s], radius=4 * s, fill=c)    # 盖子
    d.rounded_rectangle([30 * s, 34 * s, 66 * s, 78 * s], radius=6 * s, fill=c)    # 桶身
    d.rounded_rectangle([42 * s, 42 * s, 47 * s, 72 * s], radius=3 * s, fill=(0, 0, 0, 0))
    d.rounded_rectangle([53 * s, 42 * s, 58 * s, 72 * s], radius=3 * s, fill=(0, 0, 0, 0))
draw("menu-clear.png", painter_clear)

print("done")
