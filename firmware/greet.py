"""什么时候主动开口：只做判断，不碰硬件，电脑上就能测（test_brain.py）。

会主动开口的几种情况：
  arrive  有人回家了：离开超过 away_h 小时后再次出现（摄像头认出来；没摄像头时看手机连上 Wi-Fi，等 60 秒人进门）
  morning 今天第一次见到，而且是早上（免打扰结束到 11 点）
  night   该睡觉了：免打扰开始前一小时内见到，一天一次
  remind  今天第一次见到，正好有今天 / 明天要做的事（也会顺带放进上面几种的台词里）

克制的规则（“惦记”和“打扰”的分寸）：
  - 总开关关了，或者说过“安静一会儿”，就不开口
  - 免打扰时段只做表情和灯光，不出声
  - 对同一个人至少隔 cooldown_min 分钟；连着被无视几次，间隔翻倍（最多 8 倍），对方回应一次就恢复
  - 一天总共最多 max_per_day 次
  - 正在对话、正在回充时不插话
  - 说完一句就收：没人接话就不追问，见 brain.py 的接话窗口
"""
import time
from dataclasses import dataclass, field

from mood import is_quiet

NO_CAM_DELAY = 60        # 没摄像头时，手机连上 Wi-Fi 后等多久再打招呼（人还在走进门）


@dataclass
class Cue:
    kind: str
    pid: str
    speak: bool = True             # False：免打扰时段，只做表情
    away_h: float = 0.0
    remind: list = field(default_factory=list)


class Greeter:
    def __init__(self, settings, memory):
        self.cfg, self.mem = settings, memory
        self.last_seen = {p["id"]: p.get("last_seen", 0) for p in memory.people.values()}
        self.spoken = {}             # pid -> 上次主动开口的时间
        self.ignored = {}            # pid -> 连续被无视的次数
        self.done = {}               # (pid, kind) -> 日期字符串，morning / night / remind 一天一次
        self.count = (None, 0)       # (日期, 今天开口次数)
        self.muted_until = 0.0
        self.pending = {}            # 没摄像头时：pid -> 手机连上 Wi-Fi 的时间

    # ---------- 外部反馈 ----------
    def mute(self, minutes, now=None):
        self.muted_until = (now or time.time()) + minutes * 60

    def replied(self, pid):
        self.ignored[pid] = 0

    def was_ignored(self, pid):
        self.ignored[pid] = self.ignored.get(pid, 0) + 1

    # ---------- 判断 ----------
    def _day(self, now):
        return time.strftime("%Y-%m-%d", time.localtime(now))

    def _can_speak(self, pid, now):
        p = self.cfg["proactive"]
        day = self._day(now)
        if self.count[0] != day:
            self.count = (day, 0)
        if self.count[1] >= p["max_per_day"]:
            return False
        gap = p["cooldown_min"] * 60 * 2 ** min(3, self.ignored.get(pid, 0))
        return now - self.spoken.get(pid, 0) >= gap

    def step(self, now, seen, home=None, has_cam=True, busy=False):
        """seen：摄像头这会儿认出的人（集合）；home：手机在家的人 {pid: 这次在家的起始时间}。返回要做的 Cue 列表（最多一个）。"""
        p = self.cfg["proactive"]
        home = home or {}
        cues = []
        # 没摄像头时，手机连上 Wi-Fi 一会儿后当作“看到了”
        if not has_cam:
            seen = set(seen)
            for pid, since in home.items():
                if now - since >= NO_CAM_DELAY:
                    seen.add(pid)
        for pid in seen:
            if pid == "?":
                continue
            prev = self.last_seen.get(pid, 0)
            self.last_seen[pid] = now
            away = (now - prev) / 3600 if prev else 0.0
            # 摄像头很久没看到，但手机一直在家：只是在别的房间，不算回家
            phone_stayed = pid in home and home[pid] < prev
            kind = None
            lt = time.localtime(now)
            hm = lt.tm_hour * 60 + lt.tm_min
            q0, q1 = (int(x[:2]) * 60 + int(x[3:]) for x in p["quiet"])
            if prev and away >= p["away_h"] and not phone_stayed:
                kind = "arrive"
            elif self.done.get((pid, "morning")) != self._day(now) and q1 <= hm < 11 * 60 and not is_quiet(now, p["quiet"]):
                kind = "morning"
            elif self.done.get((pid, "night")) != self._day(now) and 0 <= (q0 - hm) % 1440 <= 60 and not is_quiet(now, p["quiet"]):
                kind = "night"
            remind = []
            if self.done.get((pid, "remind")) != self._day(now):
                remind = self.mem.due_today(pid, now)
                if remind and not kind:
                    kind = "remind"
            if not kind:
                continue
            if not p["on"] or now < self.muted_until or busy:
                continue
            speak = not is_quiet(now, p["quiet"])
            if speak and not self._can_speak(pid, now):
                continue
            cues.append(Cue(kind, pid, speak, away, remind))
        if not cues:
            return []
        c = max(cues, key=lambda c: ("arrive", "remind", "morning", "night").index(c.kind) * -1)
        if c.speak:
            self.spoken[c.pid] = now
            self.count = (self.count[0], self.count[1] + 1)
            if c.kind in ("morning", "night"):
                self.done[(c.pid, c.kind)] = self._day(now)
            if c.remind:
                self.done[(c.pid, "remind")] = self._day(now)
        return [c]


SITUATION = {
    "arrive": "{call}刚回家，出去了大约{away}。你主动迎接TA。",
    "morning": "今天第一次见到{call}，现在是早上。你主动跟TA道早安。",
    "night": "快到睡觉时间了，{call}还没睡。你温柔地提醒TA早点休息。",
    "remind": "看到{call}了，你想起TA有件事要做。",
}
FALLBACK = {
    "arrive": "{call}，你回来啦！我等你好久了。",
    "morning": "{call}早上好呀！",
    "night": "{call}，时间不早了，早点休息吧。",
    "remind": "{call}，别忘了{what}哦。",
}


def away_text(h):
    if h >= 48:
        return f"{int(h // 24)}天"
    if h >= 20:
        return "一整天"
    return f"{max(1, round(h))}个小时"


def instruction(cue, call):
    """让大模型写一句开场白的要求。"""
    t = SITUATION[cue.kind].format(call=call, away=away_text(cue.away_h))
    if cue.remind:
        t += "顺带提一句这件事：" + "；".join(cue.remind) + "。"
    return t + ("只说一到两句短话，像家人一样自然，可以接着你记得的事说，可以留一个TA愿意就能接的话头，"
                "但不要连着问好几个问题，不要说“有什么可以帮你”。最后单独一行写 [情绪:xxx]。")


def fallback(cue, call):
    what = cue.remind[0].split("：", 1)[-1] if cue.remind else ""
    return FALLBACK[cue.kind].format(call=call, what=what)
