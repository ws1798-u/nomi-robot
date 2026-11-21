"""电量和充电检测：ADS1115 读两路电压。
A0 是电池（两节 18650 串联，6.4–8.4 V），A1 是充电触点上的 VBUS（座子通电时约 5 V）。"""
import time
import config as C

# 两节 18650 串联、静置时的电压 → 剩余电量（%）。行走时电压会往下掉 0.1–0.2 V，所以取 10 秒平均。
CURVE = [(6.4, 0), (6.8, 4), (7.0, 10), (7.1, 15), (7.2, 22), (7.4, 40), (7.6, 58), (7.8, 74), (8.0, 86), (8.2, 95), (8.4, 100)]


def percent(volts):
    if volts <= CURVE[0][0]:
        return 0
    for (v0, p0), (v1, p1) in zip(CURVE, CURVE[1:]):
        if volts <= v1:
            return round(p0 + (p1 - p0) * (volts - v0) / (v1 - v0))
    return 100


class Power:
    def __init__(self):
        import board
        import busio
        try:                                     # adafruit-circuitpython-ads1x15 3.x
            from adafruit_ads1x15 import ADS1115, AnalogIn, ads1x15
            pins = (ads1x15.Pin.A0, ads1x15.Pin.A1)
        except ImportError:                      # 2.x
            import adafruit_ads1x15.ads1115 as ADS
            from adafruit_ads1x15.analog_in import AnalogIn
            ADS1115, pins = ADS.ADS1115, (ADS.P0, ADS.P1)
        ads = ADS1115(busio.I2C(board.SCL, board.SDA), address=C.ADC_ADDR)
        self.bat_ch, self.dock_ch = (AnalogIn(ads, p) for p in pins)
        self.avg = None
        self.t = 0.0

    def battery_v(self):
        """电池电压，10 秒左右的滑动平均。"""
        v = self.bat_ch.voltage * C.BAT_DIV
        now = time.time()
        k = 1.0 if self.avg is None else min(1.0, (now - self.t) / 10.0)
        self.avg = v if self.avg is None else self.avg + k * (v - self.avg)
        self.t = now
        return self.avg

    def percent(self):
        return percent(self.battery_v())

    def charging(self):
        """触点上有 4 V 以上，就是座子在给它供电。"""
        return self.dock_ch.voltage * C.VBUS_DIV > 4.0
