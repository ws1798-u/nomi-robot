"""软启动 / 软停止：限制加速度，防止急起急停把机器人带翻。不碰硬件，drive.py 和模拟程序都用它。

重心离地约 56 mm，滑垫离轮轴 14 mm，前后方向超过约 2.4 m/s² 就会点头甚至翻过滑垫。
所以前进后退的加速度限制在 1.0 m/s²；原地转圈（两轮一正一反）不会让它前后翻，放宽到轮缘 2.5 m/s²。
"""
import config as C

A_LIN = 1000.0                       # 前后加速度上限 mm/s²
A_ROT = 2500.0 / (C.TRACK / 2)       # 转圈角加速度上限 rad/s²（轮缘 2.5 m/s²）


class Ramp:
    def __init__(self):
        self.v = 0.0
        self.w = 0.0

    def step(self, v, w, dt):
        """给目标 (v, w)，返回这一帧实际该用的 (v, w)。"""
        dv, dw = A_LIN * dt, A_ROT * dt
        self.v += max(-dv, min(dv, v - self.v))
        self.w += max(-dw, min(dw, w - self.w))
        return self.v, self.w

    def reset(self):
        self.v = self.w = 0.0
