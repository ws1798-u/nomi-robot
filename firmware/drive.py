"""差速底盘：给线速度 v（mm/s）和角速度 w（rad/s），算出左右轮占空比。带桌沿刹停。"""
import math
from gpiozero import Motor, DigitalInputDevice
import config as C

V_MAX = C.RPM_MAX / 60 * math.pi * C.WHEEL_D     # 约 345 mm/s


class Drive:
    def __init__(self):
        self.left = Motor(*C.MOTOR_L)
        self.right = Motor(*C.MOTOR_R)
        self.cliff = {k: DigitalInputDevice(p) for k, p in C.CLIFF.items()}
        self.desk_mode = False

    def over_edge(self, forward):
        """前进时看前面两个传感器，后退时看后面一个。任何一个悬空就算到边了。"""
        keys = ("fl", "fr") if forward else ("back",)
        return any(self.cliff[k].value for k in keys)

    def set(self, v, w):
        if self.desk_mode:
            v = max(-100.0, min(100.0, v))          # 桌面上限速 0.1 m/s
        if v and self.over_edge(v > 0):
            v = 0.0                                  # 探出桌沿：只许原地转或反方向走
        vl = v - w * C.TRACK / 2                     # 左轮在 +x 一侧，和 3D 模型里一致
        vr = v + w * C.TRACK / 2
        self._run(self.left, vl)
        self._run(self.right, vr)
        return vl, vr

    def _run(self, motor, mm_s):
        duty = max(-1.0, min(1.0, mm_s / V_MAX)) * C.MOTOR_MAX
        if abs(duty) < 0.05:
            motor.stop()
        elif duty > 0:
            motor.forward(duty)
        else:
            motor.backward(-duty)

    def stop(self):
        self.left.stop()
        self.right.stop()
