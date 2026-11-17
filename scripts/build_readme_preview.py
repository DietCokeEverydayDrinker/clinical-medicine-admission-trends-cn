"""Build the report preview banner used at the top of the README."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parents[1]
FIGURE_ROOT = ROOT / "output" / "report_figures"
OUTPUT = ROOT / "output" / "readme_preview" / "report_preview_v2.png"

WIDTH = 1800
HEIGHT = 1000
BACKGROUND = "#f4f7fa"
INK = "#17344f"
MUTED = "#587086"
BORDER = "#d5e0e9"
CARD = "#ffffff"
ACCENT = "#1d5a83"
ACCENT_LIGHT = "#dcebf4"


def load_font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    names = (
        ("msyhbd.ttc", "simhei.ttf", "NotoSansCJK-Bold.ttc")
        if bold
        else ("msyh.ttc", "simsun.ttc", "NotoSansCJK-Regular.ttc")
    )
    roots = (Path("C:/Windows/Fonts"), Path("/usr/share/fonts"))
    for root in roots:
        for name in names:
            path = root / name
            if path.exists():
                return ImageFont.truetype(str(path), size)
    return ImageFont.truetype("DejaVuSans.ttf", size)


def soften(image: Image.Image) -> Image.Image:
    image = ImageOps.exif_transpose(image).convert("RGB")
    image = image.filter(ImageFilter.GaussianBlur(0.8))
    image = ImageEnhance.Contrast(image).enhance(0.88)
    return Image.blend(image, Image.new("RGB", image.size, "white"), 0.1)


def fit_image(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    return ImageOps.pad(
        soften(image),
        size,
        method=Image.Resampling.LANCZOS,
        color=CARD,
        centering=(0.5, 0.5),
    )


def main() -> None:
    canvas = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(canvas)

    title_font = load_font(56, bold=True)
    subtitle_font = load_font(28)
    card_title_font = load_font(32, bold=True)
    callout_font = load_font(38, bold=True)
    callout_small_font = load_font(24)

    draw.text((70, 42), "临床医学录取趋势 · 报告预览", fill=INK, font=title_font)
    draw.text(
        (72, 112),
        "31 个省级单位｜2017–2026｜专业池百分位与同校平衡样本",
        fill=MUTED,
        font=subtitle_font,
    )

    cards = (
        (
            (60, 190, 880, 720),
            FIGURE_ROOT / "fig_heatmap_all_clinical.png",
            "省级录取位置热图",
        ),
        (
            (920, 190, 1740, 720),
            FIGURE_ROOT / "fig_average_curves.png",
            "省级中位数均值与 95% 区间",
        ),
    )

    for box, figure_path, label in cards:
        x0, y0, x1, y1 = box
        draw.rounded_rectangle(box, radius=24, fill=CARD, outline=BORDER, width=3)
        draw.text((x0 + 28, y0 + 22), label, fill=INK, font=card_title_font)
        image = Image.open(figure_path)
        fitted = fit_image(image, (x1 - x0 - 56, y1 - y0 - 104))
        canvas.paste(fitted, (x0 + 28, y0 + 76))

    callout = (520, 820, 1280, 940)
    draw.rounded_rectangle(callout, radius=30, fill=ACCENT)
    draw.text(
        (900, 865),
        "点击查看完整报告",
        fill="white",
        font=callout_font,
        anchor="mm",
    )
    draw.text(
        (900, 910),
        "结论、方法、图注、数据边界与复现材料",
        fill=ACCENT_LIGHT,
        font=callout_small_font,
        anchor="mm",
    )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(OUTPUT, optimize=True)
    print(OUTPUT)


if __name__ == "__main__":
    main()
