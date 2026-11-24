"""耳朵舵机、灯环、头顶触摸。"""
import math
import time
from gpiozero import DigitalInputDevice
from adafruit_servokit import ServoKit
from rpi_ws281x import PixelStrip, Color
import config as C

ACCENT = (18, 184, 154)
EAR_LEVER, EAR_HORN = 11.5, 6.0     # 耳朵拨杆孔离球心、舵机摇臂孔离轴心（mm），和 make_shell.py 一致


class Body:
    def __init__(self):
        self.kit = ServoKit(channels=16)
        self.ring = PixelStrip(C.RING_N, C.RING_PIN, brightness=120)
        self.ring.begin()
        self.touch = DigitalInputDevice(C.TOUCH)
        self.ears(0)

    def ears(self, deg):
        """deg：耳朵前后摆的角度，-20 到 20，正数向前。左右舵机镜像安装，所以一个加一个减。
        v1.5 起耳朵是球窝式：根部的球插在顶盖的球窝里，超过 ±20° 胶囊会碰到孔边。
        舵机摇臂（孔离轴心 6）通过钢丝推耳朵的拨杆（孔离球心 11.5），所以舵机要转 asin(11.5 / 6 · sin 耳朵角)，±20° 对应约 ±41°。"""
        deg = max(-20.0, min(20.0, deg))
        sv = math.degrees(math.asin(max(-1.0, min(1.0, EAR_LEVER / EAR_HORN * math.sin(math.radians(deg))))))
        self.kit.servo[C.EAR_L].angle = 90 + sv
        self.kit.servo[C.EAR_R].angle = 90 - sv

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
