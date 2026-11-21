"""表情屏：在 320x240 的画布上画两只眼睛和嘴，和 3D 模型里的画法一致。"""
import math
import time
from PIL import Image, ImageDraw
from luma.core.interface.serial import spi
from luma.lcd.device import st7789
import config as C

EYE = (98, 247, 216)
BG = (10, 14, 17)


class Face:
    def __init__(self):
        serial = spi(port=0, device=0, gpio_DC=C.LCD_DC, gpio_RST=C.LCD_RST, bus_speed_hz=40_000_000)
        self.lcd = st7789(serial, width=320, height=240, rotate=0)
        self.expr = "normal"
        self.talking = False
        self.t0 = time.time()

    def draw(self):
        t = time.time() - self.t0
        img = Image.new("RGB", (320, 240), BG)
        d = ImageDraw.Draw(img)
        blink = (t % 3.7) < 0.14
        for s in (-1, 1):
            cx, cy = 160 + s * 62, 105
            if self.expr == "happy":
                d.arc((cx - 24, cy - 6, cx + 24, cy + 42), 200, 340, fill=EYE, width=11)
            elif self.expr == "heart":
                r = 15 + 2 * math.sin(t * 8)
                d.ellipse((cx - 2 * r, cy - r, cx, cy + r), fill=EYE)
                d.ellipse((cx, cy - r, cx + 2 * r, cy + r), fill=EYE)
                d.polygon([(cx - 2 * r, cy + 4), (cx + 2 * r, cy + 4), (cx, cy + 2.4 * r)], fill=EYE)
            elif self.expr == "scan":
                d.ellipse((cx - 22, cy - 22, cx + 22, cy + 22), outline=EYE, width=6)
                d.ellipse((cx - 7, cy - 7, cx + 7, cy + 7), fill=EYE)
            elif self.expr == "sleep":
                d.line((cx - 20, cy + 8, cx + 20, cy + 8), fill=EYE, width=9)
            else:
                h = 5 if blink else 56
                d.rounded_rectangle((cx - 17, cy - h / 2, cx + 17, cy + h / 2), radius=min(16, h / 2), fill=EYE)
        if self.talking:
            m = 4 + 8 * abs(math.sin(t * 14))
            d.ellipse((150, 168 - m, 170, 168 + m), fill=EYE)
        elif self.expr in ("happy", "heart"):
            d.arc((148, 150, 172, 172), 20, 160, fill=EYE, width=5)
        self.lcd.display(img)
