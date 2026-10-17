"""Generate the original GoogleUnlimited desktop mark (development only)."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

target = Path(__file__).resolve().parents[1] / "desktop/assets"
target.mkdir(parents=True, exist_ok=True)
image = Image.new("RGBA", (512, 512))
draw = ImageDraw.Draw(image)
draw.rounded_rectangle((8, 8, 504, 504), radius=142, fill="#202a23")
font_path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
font = ImageFont.truetype(str(font_path), 410) if font_path.exists() else ImageFont.load_default(370)
draw.text((253, 195), "g", font=font, fill="#ffffff", anchor="mm")
draw.ellipse((350, 350, 498, 498), fill="#f4f4f4")
draw.ellipse((369, 369, 479, 479), fill="#139c48")
image.save(target / "icon.png")
image.save(target / "icon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
