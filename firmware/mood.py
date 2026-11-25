"""心情和亲密度：让它的情绪有来由、会延续，而不是每句话随机挑个表情。

- 心情 joy（-100..100）：被摸、被陪着聊天会变好；被冷落、电量低会变差；没事时每小时往 0 回落一半。
- 精神 energy（0..100）：跟着电量和时间走，深夜和电量低时犯困。
- 亲密度 bond（每个人 0..100）：一起聊天、摸头、回应它的问候会涨；很久不见会慢慢掉，但不会掉到底。
- 想念：某个人好几天没见，再见到时会特别开心（迎接时的台词也会提到）。
这些状态写进系统提示词（describe），也决定空闲时的表情（idle_expr）。存在 memory/mood.json。
"""
import json
import os
import threading
import time

from memory import DIR

HALF_LIFE_H = 1.0             # 心情回落的半衰期


class Mood:
    def __init__(self, path=None):
        self.path = path or os.path.join(DIR, "mood.json")
        self.lock = threading.Lock()
        self.joy, self.energy, self.bond, self.t = 20.0, 80.0, {}, time.time()
        try:
            with open(self.path, encoding="utf-8") as f:
                d = json.load(f)
            self.joy, self.energy, self.bond, self.t = d["joy"], d["energy"], d["bond"], d["t"]
        except (OSError, ValueError, KeyError):
            pass

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"joy": self.joy, "energy": self.energy, "bond": self.bond, "t": self.t}, f)
        os.replace(tmp, self.path)

    def tick(self, now, battery=None, night=False):
        """每秒调用一次左右。"""
        with self.lock:
            h = max(0.0, now - self.t) / 3600
            self.t = now
            self.joy *= 0.5 ** (h / HALF_LIFE_H)
            target = 85.0
            if battery is not None:
                target = min(target, 25 + battery)
            if night:
                target = min(target, 30)
            self.energy += (target - self.energy) * min(1.0, h * 2)
            for pid in self.bond:                         # 一天不见掉 1 点，最低 20
                self.bond[pid] = max(20.0, self.bond[pid] - h / 24)

    def event(self, what, pid=None):
        """发生了什么：touch 摸头、talk 聊了一轮、greet_back 主动问候有人接话、ignored 问候没人理、
        arrive 有人回家、low_battery 电量低、dance 跳舞。"""
        d_joy, d_bond = {"touch": (12, 1.5), "talk": (6, 0.8), "greet_back": (10, 2), "ignored": (-4, 0),
                         "arrive": (18, 0.5), "low_battery": (-10, 0), "dance": (10, 0.5)}.get(what, (0, 0))
        with self.lock:
            self.joy = max(-100.0, min(100.0, self.joy + d_joy))
            if pid:
                self.bond[pid] = max(0.0, min(100.0, self.bond.get(pid, 40.0) + d_bond))

    def idle_expr(self, now, night=False):
        """空闲时的表情。"""
        if night or self.energy < 25:
            return "sleep"
        if self.joy > 55 and (now % 20) < 3:             # 心情很好时，时不时眯眼笑一下
            return "happy"
        return "normal"

    def describe(self, pid=None, away_h=None):
        """写进系统提示词的一句话。"""
        j = self.joy
        feel = "非常开心" if j > 60 else "心情不错" if j > 25 else "平静" if j > -15 else "有点失落" if j > -50 else "很难过"
        t = f"你现在{feel}"
        if self.energy < 30:
            t += "，有点困"
        b = self.bond.get(pid, 40.0) if pid else None
        if b is not None:
            t += "，和对方" + ("非常亲近" if b > 75 else "很熟" if b > 50 else "还在慢慢熟悉")
        if away_h and away_h >= 24:
            t += f"，已经{int(away_h // 24)}天没见到TA了，特别想TA"
        elif away_h and away_h >= 3:
            t += f"，TA出去了{int(away_h)}个多小时，你一直在等TA回来"
        return t + "。语气跟着心情走，但不要直接说出这些数值。"

    def public(self):
        return {"joy": round(self.joy), "energy": round(self.energy), "bond": {k: round(v) for k, v in self.bond.items()}}


def is_quiet(now, quiet):
    """quiet = ["22:30", "07:30"]，可以跨午夜。"""
    if not quiet or len(quiet) != 2 or quiet[0] == quiet[1]:
        return False
    lt = time.localtime(now)
    m = lt.tm_hour * 60 + lt.tm_min
    a, b = (int(x.split(":")[0]) * 60 + int(x.split(":")[1]) for x in quiet)
    return a <= m < b if a < b else (m >= a or m < b)

