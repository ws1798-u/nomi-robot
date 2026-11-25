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
        # 灯环 + 腰部光带串在一起，一共 RING_N + BELT_N 颗。亮度上限 70/255：68 颗全白也不超过约 1.1 A，不和舵机抢 5 V
        self.ring = PixelStrip(C.RING_N + C.BELT_N, C.RING_PIN, brightness=70)
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

    def glow(self, level, color=ACCENT, belt=True):
        """灯环（和腰部光带）整体一个亮度。level：0 到 1。"""
        r, g, b = (int(c * max(0.0, min(1.0, level))) for c in color)
        for i in range(C.RING_N + (C.BELT_N if belt else 0)):
            self.ring.setPixelColor(i, Color(r, g, b))
        self.ring.show()

    def belt(self, fn):
        """腰部光带逐颗设颜色：fn(k, n) 返回 (r, g, b)，k 是这一颗在这一段里的位置 0..n-1，前后两段对称（从右侧合缝往左数）。"""
        n = C.BELT_N // 2
        for k in range(n):
            col = Color(*(int(max(0, min(255, c))) for c in fn(k, n)))
            self.ring.setPixelColor(C.RING_N + k, col)                     # 前段
            self.ring.setPixelColor(C.RING_N + n + (n - 1 - k), col)       # 后段反着接，让两段的动画对称
        self.ring.show()

    def belt_level(self, frac, color=(40, 220, 120)):
        """充电：光带从两头往中间亮到 frac（0 到 1），像电量条。"""
        self.belt(lambda k, n: color if k < frac * n else (0, 0, 0))

    def belt_chase(self, t, color=ACCENT):
        """开心：一团光沿光带来回跑。"""
        def f(k, n):
            p = (math.sin(t * 3) * 0.5 + 0.5) * (n - 1)
            a = max(0.0, 1 - abs(k - p) / 3)
            return tuple(c * (0.15 + 0.85 * a) for c in color)
        self.belt(f)

    def mood(self, expr):
        """按情绪摆一个姿势。"""
        t = time.time()
        if expr == "happy":
            self.ears(20 * math.sin(t * 7))
            self.glow(0.8, belt=False)
            self.belt_chase(t)
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
