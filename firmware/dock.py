"""自动回充的决策：电量低 → 找红外信标 → 屁股对准充电座 → 走到中线上 → 沿中线倒车 → 触点通电就停。

这里只做决策，不碰硬件。每一帧（约 30 ms）把下面三样交给 Docker.step()：
  · 后壳左右两个红外接收头这一帧听到的信标编码（"L" / "C" / "R" 的集合）
  · 充电触点有没有电
  · 这一帧的时长
它返回 (v, w)：线速度 mm/s（负数是倒车）、角速度 rad/s（正数是逆时针）。
main.py 在真机上用它，sim_dock.py 在电脑上用同一份代码模拟。

信标编码（面对充电座看）：
  "C" 中间那颗灯，光束很窄，只照正前方一条线；
  "L" 左边那颗灯，斜着照向充电座的左前方；"R" 右边那颗，照向右前方。
"""
import math

SEARCH, FACE, CROSS, APPROACH, ESCAPE, WANDER, DOCKED, HELP, IDLE = (
    "找信号", "掉头对准", "走到中线", "倒车上座", "退出来重试", "换个地方找", "充电中", "求助", "空闲")

TURN_W = 1.2              # 原地找信号时的转速 rad/s
APPROACH_V = -70.0        # 倒车速度 mm/s
APPROACH_MAX = 45.0       # 倒车超过这么久还没通电，就退出来重试
CROSS_ANGLE = math.radians(50)
CROSS_MAX = 9.0
WANDER_S, WANDER_V = 2.5, 120.0
MAX_ROUNDS, MAX_TRIES = 4, 3


class Docker:
    def __init__(self):
        self.state = IDLE
        self.why = ""

    # ---- 对外 ----
    def start(self):
        self.state, self.t, self.turned, self.rounds, self.tries = SEARCH, 0.0, 0.0, 0, 0
        self.ema = {"rx_l": 0.0, "rx_r": 0.0, "L": 0.0, "C": 0.0, "R": 0.0}
        self.lost = 0.0
        self.unplug = 0.0
        self.cross_dir = 0
        self.flips = 0
        self.why = ""

    def stop(self):
        self.state = IDLE

    @property
    def active(self):
        return self.state not in (IDLE, DOCKED, HELP)

    def step(self, dt, heard_l, heard_r, charging):
        if self.state == IDLE:
            return 0.0, 0.0
        self._listen(dt, heard_l, heard_r)
        self.t += dt
        if charging and self.state != DOCKED:
            self._go(DOCKED)
        return getattr(self, "_" + {SEARCH: "search", FACE: "face", CROSS: "cross", APPROACH: "approach",
                                    ESCAPE: "escape", WANDER: "wander", DOCKED: "docked", HELP: "help"}[self.state])(dt, charging)

    # ---- 内部 ----
    def _listen(self, dt, heard_l, heard_r):
        """把这一帧听到的东西做个平滑：每个量在 0..1 之间，大约 0.3 秒反应过来。"""
        k = min(1.0, dt / 0.3)
        both = set(heard_l) | set(heard_r)
        for name, on in (("rx_l", bool(heard_l)), ("rx_r", bool(heard_r)), ("L", "L" in both), ("C", "C" in both), ("R", "R" in both)):
            self.ema[name] += k * ((1.0 if on else 0.0) - self.ema[name])
        any_ = self.ema["rx_l"] > 0.15 or self.ema["rx_r"] > 0.15
        self.lost = 0.0 if any_ else self.lost + dt

    def _go(self, state):
        self.state, self.t = state, 0.0

    def _zone(self):
        e = self.ema
        if e["C"] > 0.3:
            return "C"
        if e["L"] > e["R"] + 0.2:
            return "L"
        if e["R"] > e["L"] + 0.2:
            return "R"
        return "?"

    def _search(self, dt, charging):
        """原地慢慢转一圈，边转边听。转满一圈还听不到，就往前走一段换个位置。"""
        self.turned += TURN_W * dt
        if self.ema["rx_l"] > 0.3 or self.ema["rx_r"] > 0.3:
            self._go(FACE)
            return 0.0, 0.0
        if self.turned > 2 * math.pi + 0.3:
            self.rounds += 1
            self.turned = 0.0
            if self.rounds > MAX_ROUNDS:
                self.why = "转了几圈都没听到信标"
                self._go(HELP)
                return 0.0, 0.0
            self._go(WANDER)
        return 0.0, TURN_W

    def _wander(self, dt, charging):
        if self.t > WANDER_S:
            self._go(SEARCH)
        return WANDER_V, 0.0

    def _face(self, dt, charging):
        """原地转，直到左右两个接收头都听得清、而且差不多一样强，说明屁股正对着充电座。"""
        if self.lost > 1.5:
            self.flips += 1
            if self.flips >= 3:                              # 站在光束边上，一转就丢：先往前挪个位置
                self.flips = 0
                self._go(WANDER)
            else:
                self._go(SEARCH)
            return 0.0, 0.0
        l, r = self.ema["rx_l"], self.ema["rx_r"]
        b = l - r
        if l > 0.5 and r > 0.5 and abs(b) < 0.25 and self.t > 0.4:
            z = self._zone()
            if z in ("L", "R") and self.cross_dir == 0:
                self.cross_dir = -1 if z == "L" else 1
                self._go(CROSS)
            else:
                self.cross_dir = 0
                self.flips = 0
                self._go(APPROACH)
            return 0.0, 0.0
        if self.t > 6.0 and max(l, r) > 0.5:                 # 只有一个接收头听得清（在光束边上），先倒过去，边走边修
            self._go(APPROACH)
        # 左后的接收头听得多 → 顺时针转（w < 0），屁股往左后摆
        w = -0.9 * (1 if b > 0 else -1) * (0.5 + 0.5 * min(1.0, abs(b) * 2))
        return 0.0, w

    def _cross(self, dt, charging):
        """在中线一侧：先多转 50°，让屁股斜着对向中线，再倒车，直到听到中间那颗灯，然后重新对准。"""
        turn_t = CROSS_ANGLE / 1.0
        if self.t < turn_t:
            return 0.0, 1.0 * self.cross_dir
        if self.ema["C"] > 0.35 or self.t > turn_t + CROSS_MAX or self.lost > 2.5:
            self._go(FACE)
            return 0.0, 0.0
        return APPROACH_V * 1.3, 0.0

    def _approach(self, dt, charging):
        """沿中线倒车：两个接收头哪边听得多，就往哪边修一点方向。跑偏到一侧，就再去走一次中线。"""
        if self.lost > 2.0:
            self._go(SEARCH)
            return 0.0, 0.0
        if self.t > APPROACH_MAX:
            self._go(ESCAPE)
            return 0.0, 0.0
        z = self._zone()
        if z in ("L", "R") and self.ema["C"] < 0.1 and self.t > 1.5:
            self.cross_dir = -1 if z == "L" else 1
            self._go(CROSS)
            return 0.0, 0.0
        # 两个修正叠在一起：b 让屁股一直对着信标；lat 是偏到中线哪一边（左灯听得多 = 偏到了座子左前方），
        # 偏左就顺时针多拧一点，让倒车的路线斜着回到中线上。离得越近两边的灯越容易同时听到，lat 自然变小。
        b = self.ema["rx_l"] - self.ema["rx_r"]
        lat = (self.ema["L"] - self.ema["R"]) * (1.0 - 0.6 * self.ema["C"])
        return APPROACH_V, max(-0.7, min(0.7, -1.2 * b - 0.9 * lat))

    def _escape(self, dt, charging):
        """没对上：往前开出来一点，再从对准那一步重来。试 3 次还不行就求助。"""
        if self.t < WANDER_S:
            return WANDER_V, 0.0
        self.tries += 1
        if self.tries > MAX_TRIES:
            self.why = "试了几次都没对上触点"
            self._go(HELP)
        else:
            self.cross_dir = 0
            self._go(FACE)
        return 0.0, 0.0

    def _docked(self, dt, charging):
        """停在座子上。触点断开超过 3 秒（被人抱走或碰开了），就结束这次回充；电还是低的话 main.py 会重新开始。"""
        self.unplug = 0.0 if charging else self.unplug + dt
        if self.unplug > 3.0:
            self.why = "离开了充电座"
            self._go(IDLE)
        return 0.0, 0.0

    def _help(self, dt, charging):
        return 0.0, 0.0
