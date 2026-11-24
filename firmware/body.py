"""耳朵舵机、灯环、头顶触摸。"""
import math
import time
from gpiozero import DigitalInputDevice
from adafruit_servokit import ServoKit
from rpi_ws281x import PixelStrip, Color
import config as C

ACCENT = (18, 184, 154)


class Body:
    def __init__(self):
        self.kit = ServoKit(channels=16)
        self.ring = PixelStrip(C.RING_N, C.RING_PIN, brightness=120)
        self.ring.begin()
        self.touch = DigitalInputDevice(C.TOUCH)
        self.ears(0)

    def ears(self, deg):
        """deg：-30 到 30，正数向前。左右舵机镜像安装，所以一个加一个减。
        外壳顶盖上的槽按 ±30° 留的，再大摆杆会顶到槽头。"""
        deg = max(-30, min(30, deg))
        self.kit.servo[C.EAR_L].angle = 90 + deg
        self.kit.servo[C.EAR_R].angle = 90 - deg

    def glow(self, level, color=ACCENT):
        """level：0 到 1。"""
        r, g, b = (int(c * max(0.0, min(1.0, level))) for c in color)
        for i in range(C.RING_N):
            self.ring.setPixelColor(i, Color(r, g, b))
        self.ring.show()

    def mood(self, expr):
        """按情绪摆一个姿势。"""
        t = time.time()
        if expr == "happy":
            self.ears(20 * math.sin(t * 7))
            self.glow(0.8)
        elif expr == "heart":
            self.ears(25 * math.sin(t * 18))
            self.glow(1.0, (255, 120, 150))
        elif expr == "scan":
            self.ears(-10)
            self.glow(0.5 + 0.5 * math.sin(t * 5))
        elif expr == "sleep":
            self.ears(20)
            self.glow(0.15 + 0.1 * math.sin(t * 2))
        else:
            self.ears(5 * math.sin(t * 1.3))
            self.glow(0.4 + 0.15 * math.sin(t * 1.5))
