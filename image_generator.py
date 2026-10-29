# หน้าที่: สร้างโลโก้และรูปสำรองเมื่อไฟล์จำเป็นยังไม่มี
"""สร้างภาพประกอบ SmartBorrow ด้วย Pillow โดยไม่ใช้ไฟล์ภาพจากภายนอก.

รัน ``python image_generator.py`` เพื่อสร้างภาพทั้งหมดใหม่
ภาพอุปกรณ์ไม่มีข้อความฝังในภาพ เพื่อให้ชื่อภาษาไทยแสดงผ่าน Streamlit ได้ชัดเจน
"""

from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw, ImageFont


PROJECT_DIR = Path(__file__).resolve().parent
ASSETS_DIR = PROJECT_DIR / "assets"
EQUIPMENT_DIR = ASSETS_DIR / "equipment"
SCALE = 2
NAVY = "#471525"
BLUE = "#C82543"
SKY = "#F27A91"
PALE = "#FCF0F2"
GRAY = "#E5CDD3"
WHITE = "#FFFFFF"
EQUIPMENT_LABELS = {
    "camera": "กล้องถ่ายภาพ",
    "projector": "โปรเจกเตอร์",
    "microphone": "ไมโครโฟน",
    "notebook": "โน้ตบุ๊ก",
    "speaker": "ลำโพง",
    "placeholder": "ภาพแทนอุปกรณ์",
}


class Illustration:
    """วาดด้วยพิกัด 720 × 480 แล้วลดขนาดจากภาพใหญ่เพื่อให้ขอบเรียบ."""

    def __init__(self) -> None:
        self.image = Image.new("RGB", (720 * SCALE, 480 * SCALE), PALE)
        self.draw = ImageDraw.Draw(self.image)

    @staticmethod
    def bounds(values: tuple[int, ...]) -> tuple[int, ...]:
        return tuple(value * SCALE for value in values)

    def rectangle(self, bounds: tuple[int, int, int, int], fill: str,
                  radius: int = 0, outline: str | None = None, width: int = 1) -> None:
        self.draw.rounded_rectangle(
            self.bounds(bounds), radius=radius * SCALE, fill=fill,
            outline=outline, width=width * SCALE,
        )

    def ellipse(self, bounds: tuple[int, int, int, int], fill: str,
                outline: str | None = None, width: int = 1) -> None:
        self.draw.ellipse(self.bounds(bounds), fill=fill, outline=outline, width=width * SCALE)

    def line(self, points: list[tuple[int, int]], fill: str, width: int = 3) -> None:
        self.draw.line([(x * SCALE, y * SCALE) for x, y in points],
                       fill=fill, width=width * SCALE, joint="curve")

    def polygon(self, points: list[tuple[int, int]], fill: str) -> None:
        self.draw.polygon([(x * SCALE, y * SCALE) for x, y in points], fill=fill)

    def finish(self) -> Image.Image:
        return self.image.resize((720, 480), Image.Resampling.LANCZOS)


def draw_camera(art: Illustration) -> None:
    art.rectangle((229, 142, 327, 187), NAVY, 12)
    art.rectangle((210, 174, 525, 331), NAVY, 26)
    art.rectangle((211, 246, 525, 331), "#204B7B", 24)
    art.rectangle((230, 193, 282, 219), GRAY, 8)
    art.rectangle((446, 194, 491, 214), SKY, 5)
    art.ellipse((296, 170, 462, 336), "#547BA6")
    art.ellipse((308, 182, 450, 324), "#0F2747")
    art.ellipse((325, 199, 433, 307), BLUE)
    art.ellipse((341, 215, 417, 291), "#102D52")
    art.ellipse((350, 221, 378, 249), SKY)
    art.ellipse((382, 264, 393, 275), WHITE)
    art.line([(511, 210), (511, 292)], "#4A6D92", 5)


def draw_projector(art: Illustration) -> None:
    art.polygon([(408, 211), (629, 119), (629, 345), (408, 269)], "#DBEAFE")
    art.rectangle((169, 163, 487, 314), WHITE, 28, GRAY, 3)
    art.rectangle((174, 273, 482, 314), "#DCE7F3", 20)
    art.ellipse((345, 178, 471, 304), NAVY)
    art.ellipse((359, 192, 457, 290), BLUE)
    art.ellipse((375, 208, 441, 274), "#0F2747")
    art.ellipse((388, 218, 410, 240), SKY)
    for x in range(205, 303, 18):
        art.line([(x, 215), (x, 261)], "#92ABC5", 6)
    art.rectangle((211, 175, 256, 185), SKY, 4)
    art.rectangle((216, 312, 247, 327), NAVY, 5)
    art.rectangle((410, 312, 441, 327), NAVY, 5)


def draw_microphone(art: Illustration) -> None:
    art.line([(361, 322), (361, 375)], NAVY, 10)
    art.rectangle((304, 370, 417, 389), NAVY, 9)
    art.rectangle((310, 92, 411, 270), NAVY, 49)
    art.rectangle((323, 105, 398, 192), "#456D98", 35)
    for y in range(123, 187, 14):
        art.line([(335, y), (386, y)], "#9FB8D5", 3)
    art.rectangle((343, 223, 379, 236), SKY, 5)
    art.line([(284, 231), (284, 264), (293, 294), (319, 315),
              (361, 323), (401, 314), (425, 294), (438, 266), (438, 231)], BLUE, 9)
    art.line([(485, 156), (501, 178), (507, 204), (504, 229), (492, 249)], SKY, 6)
    art.line([(235, 156), (219, 178), (213, 204), (216, 229), (228, 249)], SKY, 6)


def draw_notebook(art: Illustration) -> None:
    art.rectangle((199, 112, 521, 324), NAVY, 17)
    art.rectangle((213, 127, 507, 304), BLUE, 8)
    art.ellipse((274, 147, 448, 321), "#3A7BED")
    art.rectangle((263, 176, 411, 193), WHITE, 7)
    art.rectangle((263, 205, 465, 215), "#9DDCFC", 4)
    art.rectangle((263, 228, 431, 238), "#9DDCFC", 4)
    art.rectangle((263, 259, 323, 281), SKY, 6)
    art.polygon([(199, 324), (521, 324), (562, 365), (158, 365)], "#B6C9DE")
    art.rectangle((158, 361, 562, 376), "#7B97B7", 7)
    art.polygon([(314, 334), (407, 334), (421, 352), (300, 352)], "#DDE7F2")


def draw_speaker(art: Illustration) -> None:
    art.rectangle((270, 84, 450, 383), NAVY, 24)
    art.rectangle((284, 98, 436, 369), "#234B7B", 15)
    art.ellipse((323, 118, 399, 194), "#0F2747", "#5A7A9F", 4)
    art.ellipse((341, 136, 381, 176), SKY)
    art.ellipse((296, 218, 424, 346), "#52779F")
    art.ellipse((308, 230, 412, 334), "#0F2747")
    art.ellipse((329, 251, 391, 313), BLUE)
    art.ellipse((345, 267, 375, 297), SKY)
    art.rectangle((335, 356, 385, 362), "#9FB8D5", 3)
    art.line([(496, 173), (512, 198), (518, 229), (511, 259), (496, 279)], SKY, 7)
    art.line([(224, 173), (208, 198), (202, 229), (209, 259), (224, 279)], SKY, 7)


def draw_placeholder(art: Illustration) -> None:
    art.polygon([(360, 130), (491, 193), (360, 257), (229, 193)], "#60A5FA")
    art.polygon([(229, 193), (360, 257), (360, 368), (229, 302)], BLUE)
    art.polygon([(360, 257), (491, 193), (491, 302), (360, 368)], NAVY)
    art.line([(301, 160), (428, 224), (428, 278)], "#BAE6FD", 17)
    art.line([(264, 272), (301, 291)], "#DBEAFE", 8)


DRAWERS: dict[str, Callable[[Illustration], None]] = {
    "camera": draw_camera,
    "projector": draw_projector,
    "microphone": draw_microphone,
    "notebook": draw_notebook,
    "speaker": draw_speaker,
    "placeholder": draw_placeholder,
}


def create_equipment_image(kind: str) -> Image.Image:
    """สร้างภาพอุปกรณ์หนึ่งประเภทตามชื่อใน DRAWERS."""
    if kind not in DRAWERS:
        raise ValueError(f"ไม่รู้จักประเภทภาพ: {kind}")
    art = Illustration()
    art.ellipse((80, 38, 403, 361), "#E0EDFF")
    art.ellipse((573, 71, 603, 101), "#BAE6FD")
    art.ellipse((116, 317, 137, 338), SKY)
    art.line([(567, 319), (593, 319)], "#93C5FD", 4)
    art.line([(580, 306), (580, 332)], "#93C5FD", 4)
    art.ellipse((188, 367, 536, 404), "#DAE6F5")
    DRAWERS[kind](art)
    return art.finish()


def create_avatar() -> Image.Image:
    """รูปโปรไฟล์เริ่มต้น ไม่มีชื่อหรือข้อมูลส่วนบุคคลฝังในภาพ."""
    image = Image.new("RGB", (240, 240), PALE)
    draw = ImageDraw.Draw(image)
    draw.ellipse((12, 12, 228, 228), fill=BLUE)
    draw.ellipse((82, 50, 158, 126), fill=WHITE)
    draw.rounded_rectangle((57, 140, 183, 206), radius=38, fill=WHITE)
    return image


def create_logo_icon() -> Image.Image:
    """สร้างสัญลักษณ์กล่องและลูกศรยืม-คืน ใช้เป็นโลโก้และไอคอนแท็บ."""
    image = Image.new("RGBA", (256 * SCALE, 256 * SCALE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    coords = Illustration.bounds
    draw.rounded_rectangle(coords((8, 8, 248, 248)), radius=58 * SCALE, fill=BLUE)
    draw.polygon([(128 * SCALE, 62 * SCALE), (188 * SCALE, 94 * SCALE),
                  (128 * SCALE, 126 * SCALE), (68 * SCALE, 94 * SCALE)], fill=WHITE)
    draw.polygon([(68 * SCALE, 104 * SCALE), (121 * SCALE, 132 * SCALE),
                  (121 * SCALE, 192 * SCALE), (68 * SCALE, 163 * SCALE)], fill="#DBEAFE")
    draw.polygon([(135 * SCALE, 132 * SCALE), (188 * SCALE, 104 * SCALE),
                  (188 * SCALE, 163 * SCALE), (135 * SCALE, 192 * SCALE)], fill=SKY)
    draw.line([(54 * SCALE, 211 * SCALE), (191 * SCALE, 211 * SCALE)],
              fill=WHITE, width=9 * SCALE)
    draw.polygon([(183 * SCALE, 194 * SCALE), (206 * SCALE, 211 * SCALE),
                  (183 * SCALE, 228 * SCALE)], fill=WHITE)
    return image.resize((256, 256), Image.Resampling.LANCZOS)


def load_logo_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """เลือกฟอนต์อังกฤษที่อ่านง่าย รองรับทั้ง Windows, macOS และ Linux."""
    candidates = (
        Path("C:/Windows/Fonts/segoeuib.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    )
    for path in candidates:
        if path.is_file():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default(size=size)


def create_logo() -> Image.Image:
    """สร้างโลโก้พร้อมพื้นขาว เพื่อให้ชื่ออ่านชัดบนทั้งหน้าสว่างและมืด."""
    image = Image.new("RGBA", (840 * SCALE, 180 * SCALE), (0, 0, 0, 0))
    ImageDraw.Draw(image).rounded_rectangle(
        (0, 0, image.width - 1, image.height - 1), radius=22 * SCALE, fill=WHITE,
    )
    icon = create_logo_icon().resize((152 * SCALE, 152 * SCALE), Image.Resampling.LANCZOS)
    image.paste(icon, (10 * SCALE, 14 * SCALE), icon)
    draw = ImageDraw.Draw(image)
    font = load_logo_font(80 * SCALE)
    draw.text((189 * SCALE, 90 * SCALE), "SmartBorrow", font=font, fill=NAVY, anchor="lm")
    return image.resize((840, 180), Image.Resampling.LANCZOS)


def create_banner() -> Image.Image:
    """สร้างแบนเนอร์สำหรับหน้าแรกและหน้า Login ในอนาคต โดยไม่มีข้อความฝัง."""
    image = Image.new("RGB", (1600, 560), PALE)
    draw = ImageDraw.Draw(image)
    for y in range(image.height):
        fraction = y / image.height
        color = tuple(round(start + (end - start) * fraction)
                      for start, end in zip((239, 246, 255), (219, 234, 254)))
        draw.line([(0, y), (1600, y)], fill=color)
    draw.ellipse((-220, -370, 570, 420), fill="#DBEAFE")
    draw.ellipse((1270, 320, 1840, 890), fill="#BFDBFE")
    draw.rounded_rectangle((180, 55, 750, 442), radius=34, fill=WHITE)
    draw.rounded_rectangle((850, 112, 1430, 499), radius=34, fill=WHITE)
    for kind, position in (("notebook", (195, 62)), ("camera", (865, 118))):
        card = create_equipment_image(kind).resize((550, 367), Image.Resampling.LANCZOS)
        mask = Image.new("L", card.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, 549, 366), radius=25, fill=255)
        image.paste(card, position, mask)
    draw.ellipse((733, 208, 873, 348), fill=BLUE)
    draw.line([(765, 252), (842, 252)], fill=WHITE, width=8)
    draw.polygon([(830, 238), (849, 252), (830, 266)], fill=WHITE)
    draw.line([(765, 304), (842, 304)], fill="#BAE6FD", width=8)
    draw.polygon([(777, 290), (758, 304), (777, 318)], fill="#BAE6FD")
    draw.ellipse((112, 434, 141, 463), fill=SKY)
    draw.ellipse((1464, 71, 1485, 92), fill=BLUE)
    return image


def generate_assets(overwrite: bool = False, assets_dir: Path = ASSETS_DIR) -> list[Path]:
    """สร้างภาพที่ยังไม่มี; overwrite=True เมื่อต้องการสร้างภาพทั้งหมดใหม่."""
    equipment_dir = assets_dir / "equipment"
    equipment_dir.mkdir(parents=True, exist_ok=True)
    factories: dict[Path, Callable[[], Image.Image]] = {
        assets_dir / "logo.png": create_logo,
        assets_dir / "logo_icon.png": create_logo_icon,
        assets_dir / "banner.png": create_banner,
    }
    for kind in DRAWERS:
        factories[equipment_dir / f"{kind}.png"] = lambda name=kind: create_equipment_image(name)
    for path, factory in factories.items():
        if overwrite or not path.exists():
            factory().save(path, format="PNG", optimize=True)
    return list(factories)


if __name__ == "__main__":
    for asset_path in generate_assets(overwrite=True):
        print(f"Created: {asset_path.relative_to(PROJECT_DIR)}")
