"""在电脑上模拟自动回充，用的是和真机同一份 dock.py（决策）和 motion.py（软启停）。

    python3 sim_dock.py            # 跑 400 次随机起点，打印成功率和用时
    python3 sim_dock.py plot.png   # 另外画一张轨迹图（需要 matplotlib）

模拟了什么：充电座三颗信标灯的照射范围（中间 ±7° 窄光束，左右各斜 27°、±22°），机器人后壳两个接收头的位置和视角，
每帧有 10% 的概率漏收；左右轮速度各有 ±5% 的固定偏差和 3% 的抖动（模拟打滑、电机不一致）；漏斗导轨、挡块和浮动接口台。
没模拟的：家具遮挡、反光、地毯、门槛，这些要靠实物测试。坐标单位 mm，充电座接口台中心是原点，后墙在 -Y。
"""
import math
import random
import sys
import dock
from motion import Ramp
import config as C

DT = 0.03
WALL_Y = -(62 * 1.15 + 8)                       # 后墙正面，和 make_shell.py 一样
LEDS = [("C", 0.0, 90.0, 7.0, 3000.0), ("L", 9.0, 63.0, 22.0, 2000.0), ("R", -9.0, 117.0, 22.0, 2000.0)]
RX_R, RX_A, RX_FOV = 67.4, 0.55, math.radians(70)
ROOM = 1800.0


def ang(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def rx_positions(x, y, psi):
    out = {}
    for k, s in (("l", -1), ("r", 1)):
        b = psi + math.pi + s * RX_A
        out[k] = (x + RX_R * math.cos(b), y + RX_R * math.sin(b), b)
    return out


def hears(rx, rng):
    """一个接收头这一帧听到哪些编码。"""
    px, py, b = rx
    got = set()
    for code, lx, aim, half, rmax in LEDS:
        dx, dy = px - lx, py - WALL_Y
        if dy <= 0 or math.hypot(dx, dy) > rmax:
            continue
        if abs(ang(math.atan2(dy, dx) - math.radians(aim))) > math.radians(half):
            continue
        if abs(ang(math.atan2(-dy, -dx) - b)) > RX_FOV:
            continue
        if rng.random() < 0.9:
            got.add(code)
    return got


def funnel_gap(y):
    return 2.0 + max(0.0, min(12.0, (y - 5.0) * 12.0 / 33.0))


def run(seed, start=None, t_max=240.0, keep_path=False):
    rng = random.Random(seed)
    if start is None:
        while True:
            x, y = rng.uniform(-1500, 1500), rng.uniform(150, 1700)
            if math.hypot(x, y) > 250:
                break
        psi = rng.uniform(-math.pi, math.pi)
    else:
        x, y, psi = start
    bias = (1 + rng.gauss(0, 0.05), 1 + rng.gauss(0, 0.05))
    d, ramp = dock.Docker(), Ramp()
    d.start()
    t, path, charging = 0.0, [], False
    while t < t_max:
        rxs = rx_positions(x, y, psi)
        v_cmd, w_cmd = d.step(DT, hears(rxs["l"], rng), hears(rxs["r"], rng), charging)
        if d.state in (dock.DOCKED, dock.HELP):
            break
        v, w = ramp.step(v_cmd, w_cmd, DT)
        vl = (v - w * C.TRACK / 2) * bias[0] * (1 + rng.gauss(0, 0.03))
        vr = (v + w * C.TRACK / 2) * bias[1] * (1 + rng.gauss(0, 0.03))
        v, w = (vl + vr) / 2, (vr - vl) / C.TRACK         # 和 drive.py 同一个约定：w 正 = 逆时针（右轮快）
        nx, ny, npsi = x + v * math.cos(psi) * DT, y + v * math.sin(psi) * DT, psi + w * DT
        # 漏斗导轨：只在倒车进来、而且方向差不多对时才能滑进去，否则被导轨挡住
        if -15 < ny < 40 and abs(nx) > funnel_gap(ny):
            mis = abs(ang(npsi - math.pi / 2))
            if mis < math.radians(30) and abs(x) < funnel_gap(ny) + 15:
                nx = math.copysign(funnel_gap(ny), nx)
                npsi += -0.15 * ang(npsi - math.pi / 2)
            elif abs(x) < 80:
                nx, ny = x, y
        ny = max(ny, 0.0) if abs(nx) < 60 else ny                 # 挡块
        if abs(nx) < 100 and ny < 0:
            ny = 0.0
        nx, ny = max(-ROOM, min(ROOM, nx)), max(WALL_Y - 400 if abs(nx) > 110 else 0.0, min(ROOM, ny))
        x, y, psi = nx, ny, npsi
        charging = abs(x) <= 2.6 and y <= 1.0 and abs(ang(psi - math.pi / 2)) < math.radians(8)
        if keep_path:
            path.append((x, y, d.state))
        t += DT
    return d.state == dock.DOCKED, t, path, d.why


def covered(x, y):
    """起点在不在信标照得到的范围里。"""
    for code, lx, aim, half, rmax in LEDS:
        dx, dy = x - lx, y - WALL_Y
        if dy > 0 and math.hypot(dx, dy) <= rmax and abs(ang(math.atan2(dy, dx) - math.radians(aim))) <= math.radians(half):
            return True
    return False


def main():
    n = 400
    stat = {True: [0, []], False: [0, []]}
    fails = {}
    for i in range(n):
        rng = random.Random(i)                         # 和 run() 里取起点的方式一样，用来判断起点在不在光束里
        while True:
            x, y = rng.uniform(-1500, 1500), rng.uniform(150, 1700)
            if math.hypot(x, y) > 250:
                break
        c = covered(x, y)
        good, t, _, why = run(i)
        stat[c][0] += 1
        if good:
            stat[c][1].append(t)
        else:
            k = ("光束里起步：" if c else "光束外起步：") + (why or "4 分钟内没充上")
            fails[k] = fails.get(k, 0) + 1
    for c, name in ((True, "在信标照得到的地方起步"), (False, "在照不到的地方起步（座子侧后方或 2 米外）")):
        m, ts = stat[c][0], sorted(stat[c][1])
        if m:
            med = f"，用时中位数 {ts[len(ts) // 2]:.0f} 秒" if ts else ""
            print(f"{name}：{m} 次，充上 {len(ts)} 次（{len(ts) / m:.0%}）{med}")
    for k, v in sorted(fails.items()):
        print(f"  没充上 · {k} × {v}")
    if len(sys.argv) > 1:
        plot(sys.argv[1])


def plot(fname):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager as fm
    for f in ("/System/Library/Fonts/STHeiti Medium.ttc", "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"):
        try:
            fm.fontManager.addfont(f)
            plt.rcParams["font.family"] = fm.FontProperties(fname=f).get_name()
            break
        except Exception:
            pass
    fig, ax = plt.subplots(figsize=(8, 6.2), dpi=130)
    for code, lx, aim, half, rmax in LEDS:
        a0, a1 = math.radians(aim - half), math.radians(aim + half)
        col = {"C": "#f2a623", "L": "#d85a30", "R": "#534ab7"}[code]
        ax.fill([lx, lx + rmax * math.cos(a0), lx + rmax * math.cos(a1)], [WALL_Y, WALL_Y + rmax * math.sin(a0), WALL_Y + rmax * math.sin(a1)],
                color=col, alpha=0.10 if code != "C" else 0.25, lw=0)
    starts = [(-1200, 900, 0.3), (1300, 1300, 2.5), (300, 1600, -1.2), (-600, 300, 1.0), (900, 250, -2.8), (-1400, 1500, -0.4), (100, 700, 3.0), (1500, 600, 1.6)]
    for i, s in enumerate(starts):
        good, t, path, _ = run(1000 + i, start=s, keep_path=True)
        xs, ys = [p[0] for p in path], [p[1] for p in path]
        ax.plot(xs, ys, lw=1.1, color="#0f6e56" if good else "#a32d2d")
        ax.plot(s[0], s[1], "o", ms=5, color="#333")
        ax.text(s[0] + 40, s[1] + 40, f"{t:.0f} 秒充上" if good else "照不到，求助", fontsize=8, color="#333")
    ax.add_patch(plt.Rectangle((-35, WALL_Y - 22), 70, 22, color="#b8ad97"))
    ax.text(60, WALL_Y - 60, "充电座", fontsize=9)
    ax.set_xlim(-1700, 1700)
    ax.set_ylim(-150, 1800)
    ax.set_aspect("equal")
    ax.set_xlabel("mm")
    ax.set_title("自动回充模拟：8 个起点的轨迹（黑点是起点；绿线充上了，红线在光束外没找到）", fontsize=10.5)
    ax.text(-1650, 1700, "橙色窄条：中间灯　紫色：右灯　粉色：左灯（面对充电座看）", fontsize=8, color="#555")
    fig.tight_layout()
    fig.savefig(fname)
    print("轨迹图：", fname)


if __name__ == "__main__":
    main()
