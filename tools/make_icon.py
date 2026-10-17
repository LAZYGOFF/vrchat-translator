import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = 1024


def gradient(size, c1, c2):
    g = Image.new("RGB", (size, size))
    px = g.load()
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * (size - 1))
            px[x, y] = tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))
    return g


def make():
    base = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle((40, 40, S - 40, S - 40), radius=230, fill=255)
    base.paste(gradient(S, (90, 169, 255), (139, 92, 246)), (0, 0), mask)

    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    bubble = (190, 230, 834, 700)
    tail = [(300, 680), (250, 840), (450, 690)]
    sd.rounded_rectangle([c + 18 for c in bubble], radius=150, fill=(20, 10, 60, 110))
    sd.polygon([(x + 18, y + 18) for x, y in tail], fill=(20, 10, 60, 110))
    base.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(22)))
    d = ImageDraw.Draw(base)
    d.rounded_rectangle(bubble, radius=150, fill=(255, 255, 255, 255))
    d.polygon(tail, fill=(255, 255, 255, 255))

    zh = ImageFont.truetype(r"C:\Windows\Fonts\msyhbd.ttc", 290)
    en = ImageFont.truetype(r"C:\Windows\Fonts\segoeuib.ttf", 300)
    d.text((375, 462), "文", font=zh, fill=(70, 80, 200, 255), anchor="mm")
    d.text((665, 462), "A", font=en, fill=(139, 92, 246, 255), anchor="mm")

    out = os.path.join(HERE, "icon.ico")
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    base.resize((256, 256), Image.LANCZOS).save(out, sizes=sizes)
    base.resize((256, 256), Image.LANCZOS).save(os.path.join(HERE, "icon.png"))
    return out


if __name__ == "__main__":
    print(make())
