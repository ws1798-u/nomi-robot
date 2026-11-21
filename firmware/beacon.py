"""收充电座的红外信标。后壳左右各一个 VS1838B，收到 38 kHz 红外光时输出低电平。

信标一帧 = 3 ms 引导 + 1 ms 空 + 一段编码光：0.8 ms 是左灯 "L"，1.3 ms 是中灯 "C"，1.8 ms 是右灯 "R"。
三颗灯轮流发，每颗每秒约 19 帧。这里量每一段低电平有多长，先认出 3 ms 的引导，再看后面那段是哪颗灯。
电视遥控器的信号（引导 9 ms 或没有引导）对不上格式，会被丢掉。
"""
import threading
import time
import config as C

CODES = (("L", 600, 1050), ("C", 1100, 1550), ("R", 1600, 2100))   # (编码, 最短 µs, 最长 µs)
HEAD = (2500, 3500)


class Beacon:
    def __init__(self, pins=None):
        import lgpio
        self.lg = lgpio
        self.h = lgpio.gpiochip_open(0)
        self.pins = pins or C.BEACON_RX
        self.lock = threading.Lock()
        self.low_at = {}
        self.head_at = {}
        self.hits = {k: [] for k in self.pins}
        self.cbs = []
        for k, p in self.pins.items():
            lgpio.gpio_claim_alert(self.h, p, lgpio.BOTH_EDGES, lgpio.SET_PULL_UP)
            self.cbs.append(lgpio.callback(self.h, p, lgpio.BOTH_EDGES, self._edge(k)))

    def _edge(self, k):
        def cb(chip, gpio, level, tick):          # tick：纳秒
            if level == 0:
                self.low_at[k] = tick
                return
            if level != 1 or k not in self.low_at:
                return
            us = (tick - self.low_at[k]) / 1000
            if HEAD[0] <= us <= HEAD[1]:
                self.head_at[k] = tick
                return
            h = self.head_at.pop(k, None)
            if h is None or (tick - h) / 1000 > 4000:     # 编码光必须紧跟在引导后面
                return
            for code, lo, hi in CODES:
                if lo <= us <= hi:
                    with self.lock:
                        self.hits[k].append((time.time(), code))
                    break
        return cb

    def heard(self, window=0.12):
        """最近 window 秒里，左右两个接收头各听到了哪些编码：({"C", ...}, {...})。"""
        now = time.time()
        with self.lock:
            for k in self.hits:
                self.hits[k] = [(t, c) for t, c in self.hits[k] if now - t < 1.0]
            return tuple({c for t, c in self.hits[k] if now - t < window} for k in ("l", "r"))
