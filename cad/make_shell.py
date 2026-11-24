"""生成 Nomi 样机的可打印零件（STL）。

    pip install manifold3d numpy trimesh
    python make_shell.py            # 默认放大到 115%，输出到 stl/
    python make_shell.py 1.0        # 1:1（现成模块会很挤）

坐标：X 向右，Y 向前（脸的方向），Z 向上，单位毫米。外壳尺寸随比例 K 缩放；
买来的零件（轮子、电机、舵机、树莓派的孔位）是实际尺寸，不缩放。
"""
import math
import os
import sys
import numpy as np
import trimesh
from manifold3d import Manifold, CrossSection

K = float(sys.argv[1]) if len(sys.argv) > 1 else 1.15
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stl")
WALL = 2.0                       # 壁厚
SEG = 96                         # 圆周分段
# 配合间隙（每边）：两个零件套在一起、滑动、转动，或者买来的零件塞进打印件里，都留这么多。
# 打印商家要求至少 0.3 mm（尼龙 ±0.2–0.3，光固化 ±0.1–0.2），0.3 是能装上的前提下最紧的值。
FIT = 0.3


# 攻牙底孔：商家打印后用丝锥攻 M2 牙（M2 标准底孔 Ø1.6）。这里不加间隙，商家先用 Ø1.6 钻头过一遍再攻。
TAP_M2 = 0.8
# 底盘固定：三颗 M2 螺丝从底下穿过底盘，拧进外壳内壁底部的三根螺丝柱（柱上攻 M2 牙）。
# 位置用程序在一圈里扫过：避开轮子、电机、骨架、USB 滑门和它推开的范围、悬崖传感器和模块板、滑垫、充电板垫块。
BASE_SCREWS = (90, 220, 320)      # 角度：从 +X 逆时针（90 = 正前方）
BASE_SCREW_R = 26.5               # 离中心
BOSS_H = 5.0                      # 螺丝柱高（从底盘上表面往上）


def hole(r, seg):
    """圆孔是用 seg 段直线拼的。按“外切”算半径，让每段直线的中点也在 r 上，孔不会比标称尺寸小。"""
    return r / math.cos(math.pi / seg)

# 外壳轮廓（和 3D 模型、尺寸图是同一个公式）
YC, RB, BL, BU, Y0, YCAP, YTOP = 60, 62, 56, 68, 6, 119, 128


def prof(h):
    """离地 h（已乘比例）处的外半径。"""
    y = h / K
    t = min(1.0, abs(y - YC) / (BL if y < YC else BU))
    return K * (RB * (1 - t ** 3) ** (1 / 3) if y < YC else RB * math.sqrt(max(0.0, 1 - t * t)))


# 内壁：沿壳面的法向往里收 WALL（之前是沿半径收，底部和顶部壳面很斜，垂直于壳面只剩 0.4–1 mm）。
# 最底下按法向收会把底口收得太小，所以底口保持原来的半径 R_OPEN（底盘照样放得进去），
# 这一段变成一圈 2 mm 宽的实心平底，往上再接法向等厚的内壁。
R_OPEN = None
_IN_H = _IN_R = None


def _inner_table():
    global _IN_H, _IN_R, R_OPEN
    hs = np.linspace(4.05 * K, 127.9 * K, 6000)
    r = np.array([prof(h) for h in hs])
    dr = np.gradient(r, hs)
    n = np.sqrt(1 + dr * dr)
    _IN_R, _IN_H = r - WALL / n, hs + WALL * dr / n          # 外壁点沿法向往里挪 WALL
    R_OPEN = prof(Y0 * K) - WALL


def inner_off(h):
    """外壁沿法向往里 WALL 的那条曲线在离地 h 处的半径（不管底口）。"""
    if _IN_H is None:
        _inner_table()
    return float(np.interp(h, _IN_H, _IN_R))


def inner_r(h):
    """离地 h 处的内壁半径：垂直于壳面处处 WALL 厚，底口不小于 R_OPEN。"""
    v = inner_off(h)
    return max(R_OPEN, v)


# 表情窗（前壳正面）：左右各 WIN_A 弧度，离地 WIN_Z0F..WIN_Z1F（未缩放），和 3D 模型一样四角大圆弧：
# 角度方向圆角 WIN_RA 弧度、高度方向 WIN_RH（未缩放），左右两头接近半圆。窗里嵌一片打印的弧面镜片，见 lens()
WIN_A, WIN_Z0F, WIN_Z1F = 0.781, 59.19, 94.81
WIN_RA, WIN_RH = 0.2625, 16.6

# 实际零件尺寸（不缩放）
WHEEL_D, WHEEL_W = 44.0, 10.0
# 底部接口（夹座、充电座、机器人共用，买来的零件，不缩放）：
#   机器人底面：DIN988 锰钢垫片 17 × 24 × 1（现货，能被磁铁吸），中间一块 Ø16 × 1.6 的四环触点板（嘉立创打样，沉金）
#   座子凸台：6 颗 Ø6 × 3 钕铁硼圆片磁铁排成一圈（现货）。v1.2 之前用 Ø26 / Ø18 × 3 环形磁铁和 Ø27 / Ø17 × 0.8 钢环，都没现货
#   整块环形磁铁的原方案留档（以后定型可定做）：问答/设计备忘/磁吸接口_整块环形磁铁方案.md（私有仓库）
MAG_D, MAG_T, MAG_R = 6.0, 3.0, 10.0
MAG_ANG = (22.5, 67.5, 112.5, 157.5, 202.5, 337.5)   # 避开 270° 方向：那边是离中心 6.2 的 GND 弹针
#   座子凸台中间插 Ø1.5 × 8 的弹簧顶针
#   四根针分在四个方向：中心 VBUS、3.2 D+、4.7 D−、6.2 GND（离中心的距离，mm）。触点板：中心圆点 Ø2，三圈环宽 0.8。
#   v1.2 从 3.4 / 5.4 / 7.3 改过来：最外圈弹针孔离环形磁铁坑原来只有 0.35 mm，现在 1.45；中心孔和第一圈孔之间 1.1
PINS_USB = ((0.0, 0), (3.2, 90), (4.7, 180), (6.2, 270))
PINS_POWER = ((0.0, 0), (6.2, 270))       # 地面充电座只要 VBUS 和 GND
AXLE_Z = WHEEL_D / 2             # 轮轴离地
WHEEL_X = 41 * K                 # 轮子中心到机身中心
# 滑垫：四个 Ø5，分在左右两侧（x = ±24.5，y = ±14），中间留一条约 44 宽的空道给充电座的接口台
PAD_R = 2.5
PADS = [(sx * 24.5, sy * 14.0) for sx in (1, -1) for sy in (1, -1)]
# 回充红外接收头：后壳上左右各一个（VS1838B，Ø5 圆头），离地 30 × 比例，偏离正后方 ±0.55 弧度
IR_RX_Z, IR_RX_A = 30, 0.55


def box(x0, x1, y0, y1, z0, z1):
    return Manifold.cube([x1 - x0, y1 - y0, z1 - z0]).translate([x0, y0, z0])


def cyl_z(r, z0, z1, x=0, y=0, seg=48):
    return Manifold.cylinder(z1 - z0, r, r, seg).translate([x, y, z0])


def cyl_y(r, y0, y1, x=0, z=0, seg=48):
    return Manifold.cylinder(y1 - y0, r, r, seg).rotate([-90, 0, 0]).translate([x, y0, z])


def cyl_x(r, x0, x1, y=0, z=0, seg=48):
    return Manifold.cylinder(x1 - x0, r, r, seg).rotate([0, 90, 0]).translate([x0, y, z])


def ccw(points):
    """多边形统一成逆时针，否则建模库会把它当成空的。"""
    pts = [(float(x), float(y)) for x, y in points]
    area = sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))
    return pts if area > 0 else pts[::-1]


def revolve(points):
    """points：(半径, 高度) 的闭合多边形，绕 Z 轴转一圈。"""
    return Manifold.revolve(CrossSection([ccw(points)]), SEG)


def shell_body():
    """离地 Y0..YCAP 的空心壳体，上下都开口。"""
    hs = np.linspace(Y0 * K, YCAP * K, 90)
    outer = [(prof(h), h) for h in hs]
    his = np.linspace(Y0 * K, YCAP * K, 240)                   # 内壁底部有个拐点，取密一点
    inner = [(inner_r(h), h) for h in his[::-1]]
    return revolve(outer + inner)


def sector(a0, a1, r0, r1, z0, z1, n=24):
    """俯视的扇环（角度从正前方 +Y 起算，向 +X 为正），拉伸成柱。"""
    pts = [(r1 * math.sin(a), r1 * math.cos(a)) for a in np.linspace(a0, a1, n)]
    pts += [(r0 * math.sin(a), r0 * math.cos(a)) for a in np.linspace(a1, a0, n)]
    return Manifold.extrude(CrossSection([ccw(pts)]), z1 - z0).translate([0, 0, z0])


def win_prism(d, r_ref, r0=30 * K, r1=80 * K, nc=24):
    """表情窗形状的立体：在（角度 a，高度 h）平面里画圆角矩形，沿半径从 r0 拉到 r1。
    d 是四周等距外扩的距离（mm，负数是内缩）：把角度乘 r_ref 换成弧长，在（弧长，高度）平面里沿法向偏移 d，
    圆角处也处处是 d（不是简单地把两个圆角半径各加 d）。"""
    hc = (WIN_Z0F + WIN_Z1F) / 2 * K
    A, HH = WIN_A, (WIN_Z1F - WIN_Z0F) / 2 * K
    RA, RH = WIN_RA, WIN_RH * K
    ca, ch = A - RA, HH - RH
    pts = []
    for sa, sh, t0 in ((1, 1, 0.0), (-1, 1, 90.0), (-1, -1, 180.0), (1, -1, 270.0)):
        for t in np.linspace(math.radians(t0), math.radians(t0 + 90), nc + 1):
            pts.append((sa * ca + RA * math.cos(t), hc + sh * ch + RH * math.sin(t)))
    # 直边细分（直边在三维里是弧线，要多分几段）
    full = []
    m = len(pts)
    for i in range(m):
        p, q = pts[i], pts[(i + 1) % m]
        seg = max(1, int(math.ceil(max(abs(q[0] - p[0]) / 0.02, abs(q[1] - p[1]) / 1.5))))
        for k in range(seg):
            f = k / seg
            full.append((p[0] + (q[0] - p[0]) * f, p[1] + (q[1] - p[1]) * f))
    if d:
        P = np.array([(a * r_ref, h) for a, h in full])
        T = np.roll(P, -1, 0) - np.roll(P, 1, 0)                  # 逆时针走，外法向 = 切向右转 90°
        N = np.stack([T[:, 1], -T[:, 0]], 1)
        N /= np.linalg.norm(N, axis=1, keepdims=True)
        P = P + d * N
        full = [(x / r_ref, h) for x, h in P]
    n = len(full)
    V = [(r * math.sin(a), r * math.cos(a), h) for r in (r0, r1) for a, h in full]
    V += [(0.0, r0, hc), (0.0, r1, hc)]
    F = []
    for i in range(n):
        j = (i + 1) % n
        F += [(i, j, n + j), (i, n + j, n + i)]
        F += [(2 * n, j, i), (2 * n + 1, n + i, n + j)]
    tm = trimesh.Trimesh(np.array(V), np.array(F), process=True)
    trimesh.repair.fix_normals(tm)
    assert tm.is_volume, "win_prism 不封闭"
    from manifold3d import Mesh
    return Manifold(Mesh(vert_properties=np.asarray(tm.vertices, np.float32), tri_verts=np.asarray(tm.faces, np.uint32)))


def cutters():
    """外壳上所有的开口。"""
    c = []
    # 轮舱：轮子从两侧下方露出
    for s in (1, -1):
        c.append(box(min(s * (WHEEL_X - 7), s * (WHEEL_X + 9)), max(s * (WHEEL_X - 7), s * (WHEEL_X + 9)),
                     -WHEEL_D / 2 - 3, WHEEL_D / 2 + 3, -1, AXLE_Z * 2 + 3))
    # 表情窗：四角大圆弧的圆角矩形，见 win_prism()
    c.append(win_prism(0.0, 1.0))
    # 摄像头孔：离地 104，朝前上方 29°
    cam = Manifold.cylinder(40 * K, 6.8, 6.8, 48).translate([0, 0, 20 * K]).rotate([-(90 - 29), 0, 0])
    c.append(cam.translate([0, 18 * K, 93 * K]))
    # 摄像头盖片沉台：光轴穿出外壳的地方，沿光轴往里铣一个 Ø16.4、深 1 mm 的平底台，
    # 放一片 Ø16 × 1 的平面盖片（透明亚克力或玻璃），盖片外表面中心和壳面齐平，镜头不凸出来
    ax = np.array([0, math.sin(math.radians(61)), math.cos(math.radians(61))])
    o = np.array([0, 18 * K, 93 * K])
    d = 0.0
    while math.hypot(*(o + d * ax)[:2]) < prof((o + d * ax)[2]):
        d += 0.05
    seat = Manifold.cylinder(12, hole(8 + FIT, 64), hole(8 + FIT, 64), 64).translate([0, 0, d - 1.0]).rotate([-(90 - 29), 0, 0])
    c.append(seat.translate(list(o)))
    # 避障传感器（ToF）窗口另外做，见 tof_window()
    # 出音孔：背面一片 Ø3 的小孔
    for gz in np.arange(69, 101, 6.0):
        for gx in np.arange(-21, 22, 6.0):
            if (gx / 24) ** 2 + ((gz - 84) / 19) ** 2 < 1:
                c.append(cyl_y(1.5, -80 * K, -30 * K, gx * K, gz * K, 12))
    # 回充红外接收头的孔：Ø5 + 间隙，沿半径方向，VS1838B 的圆头从里面塞进来，热熔胶固定
    for s_ in (1, -1):
        a = math.pi + s_ * IR_RX_A
        c.append(cyl_y(hole(2.5 + FIT, 24), 30 * K, 90 * K, 0, IR_RX_Z * K, 24).rotate([0, 0, -math.degrees(a)]))
    # 隐藏 USB-C 的窗口：底部后缘，平时被壳内侧的旋转滑门挡住，见 usb_door()
    c.append(sector(math.pi - DOOR_WIN, math.pi + DOOR_WIN, 20 * K, 80 * K, WIN_Z0 * K, WIN_Z1 * K))
    out = c[0]
    for m in c[1:]:
        out = out + m
    return out


# 隐藏 USB-C 滑门（样机版）：一片顺着壳内壁弯的弧形门，夹在上下两道带内唇的导轨之间，绕机身竖轴滑动。
# 门上的拨片从窗口里露出来，用指甲往右一推就滑开 0.45 弧度；拨片碰到窗口两边就是两头的限位。
# 量产版把门做在壳外侧、和壳面平齐（见 3D 模型），样机打印做不了那么薄，所以放在内侧，关上时比外壳凹进 2 mm。
WIN_Z0, WIN_Z1 = 10.0, 17.0       # 窗口上下（未缩放的离地高度）；再往下导轨会碰到底盘
DOOR_WIN = 0.25                   # 窗口半宽（弧度）
DOOR_HALF = 0.33                  # 门的半宽（弧度），比窗口宽，关上时四周都盖住
DOOR_OPEN = 0.45                  # 滑开的角度
DOOR_T = 2.6                      # 门厚（沿半径）。壁在这里很斜：垂直于门板量约 1.1–1.7 mm（v1.1 是 1.5，只有 0.7）
DOOR_T_LOW, DOOR_Z_LOW = 3.8, 11.9 # 门最下沿（充电板下面，没东西挡）再加厚，免得成一道斜刃


def door_t(h):
    """门在离地 h 处沿半径的厚度：下沿 DOOR_T_LOW，往上 0.6 mm 过渡到 DOOR_T。"""
    if h <= DOOR_Z_LOW:
        return DOOR_T_LOW
    if h >= DOOR_Z_LOW + 0.6:
        return DOOR_T
    return DOOR_T_LOW + (DOOR_T - DOOR_T_LOW) * (h - DOOR_Z_LOW) / 0.6




def nfit(z0, z1):
    """壳壁是斜的：沿半径方向留 FIT，垂直于壁面的实际间隙只有 FIT × cos(倾角)。
    按 z0..z1 这一段最斜的地方放大，保证垂直于壁面也有 FIT。"""
    dh = 0.05
    worst = max(abs(inner_r(h + dh) - inner_r(h - dh)) / (2 * dh) for h in np.linspace(z0, z1, 40))   # 门贴着的是内壁，按内壁的斜度算
    facet = prof(z1) * (1 - math.cos(math.pi / SEG))                # 圆周分成 SEG 段平面，平面中间比圆凹进去这么多
    hs = np.linspace(Y0 * K, YCAP * K, 240)                          # 内壁的取样点（和 shell_body 一样），点之间是直线
    zs = np.linspace(z0, z1, 200)
    chord = max(abs(np.interp(zs, hs, [inner_r(h) for h in hs]) - np.array([inner_r(z) for z in zs])))
    return FIT * math.sqrt(1 + worst * worst) + 2 * facet + chord


def band(z0, z1, r_out, r_in, n=30):
    """贴着外壳内壁的一圈带子：半径从 内壁+r_out 到 内壁-r_in，高度 z0..z1（已乘比例）。"""
    hs = np.linspace(z0, z1, n)
    return revolve([(inner_r(h) + r_out, h) for h in hs] + [(max(inner_r(h) - r_in, 0.5), h) for h in hs[::-1]])


def door_rails():
    """后壳内侧的上下两道导轨，L 形：一条贴壁的托条 + 一道内唇，门的上下沿卡在里面。"""
    a0, a1 = math.pi - DOOR_HALF - 0.07, math.pi + DOOR_HALF + DOOR_OPEN + 0.07
    lo0, lo1 = (WIN_Z0 - 1.6) * K, (WIN_Z0 - 0.6) * K           # 门下沿在 WIN_Z0 - 0.6 附近
    hi0, hi1 = (WIN_Z1 + 0.6) * K, (WIN_Z1 + 1.6) * K
    dz0, dz1 = lo1 + FIT, hi0 - FIT                              # 门的上下沿
    g = nfit(dz0, dz1)                                           # 门和壳壁、门和内唇的间隙（沿半径）
    # 内唇做成等半径的一圈：壳在这里很斜，跟着壳面走的唇会顶到门。唇比门的内表面再往里 FIT，压住门沿 0.6 mm
    # 内唇半径：取唇和门重叠那一段里，门内表面最靠里的地方，再往里 g
    door_in = lambda za, zb: min(inner_r(h) - g - door_t(h) for h in np.linspace(za, zb, 25))
    r1l = door_in(dz0, dz0 + 0.6) - g
    r1u = door_in(dz1 - 0.6, dz1) - g
    # 托条：贴壁的一条，往里伸到内唇里 0.6，和内唇连成一体
    rails = band(lo0 - 1.2, lo0, 0.5, max(DOOR_T + 1.6, inner_r(lo0) - (r1l - 1.2) + 0.6)) \
        + band(hi1, hi1 + 1.2, 0.5, max(DOOR_T + 4, inner_r(hi1 + 1.2) - (r1u - 1.2) + 0.6))
    for za, zb, r1 in ((lo0 - 0.6, dz0 + 0.6, r1l), (dz1 - 0.6, hi1 + 0.6, r1u)):
        rails = rails + (cyl_z(r1, za, zb, seg=SEG) - cyl_z(r1 - 1.2, za - 1, zb + 1, seg=SEG))
    rails = rails ^ sector(a0, a1, 1, 200, 0, 60 * K, 48)
    # 壁加厚以后下托条落到了底盘上方：让开底盘（半径 R_OPEN、到底盘上表面再加 FIT）
    inner_r(Y0 * K)
    return rails - cyl_z(R_OPEN + 0.5, Y0 * K - 1, Y0 * K + 2.5 + FIT, seg=SEG)   # 半径多 0.5，切口不和底口内壁重合


def usb_door():
    """滑门本体 + 从窗口露出来的拨片。门在关闭位置（居中对着正后方）。"""
    z0, z1 = (WIN_Z0 - 0.6) * K + FIT, (WIN_Z1 + 0.6) * K - FIT
    g = nfit(z0, z1)
    hs = np.linspace(z0, z1, 40)
    outer = [(inner_r(h) - g, h) for h in hs]
    inner = [(inner_r(h) - g - door_t(h), h) for h in hs[::-1]]
    d = revolve(outer + inner) ^ sector(math.pi - DOOR_HALF, math.pi + DOOR_HALF, 1, 200, 0, 60 * K, 48)
    zk = (WIN_Z0 + WIN_Z1) / 2 * K
    # 拨片：端面在壳面下 0.3，往里伸进门板 0.8，和门连成一体
    knob = band(zk - 2.5, zk + 2.5, prof(zk) - inner_r(zk) - 0.3, g + 0.8) ^ sector(math.pi - 0.22 - 0.025, math.pi - 0.22 + 0.025, 1, 200, 0, 60 * K, 8)
    return d + knob


def seam_tabs(front):
    """前后壳合缝处的螺丝耳：四颗 M2 × 10 从后壳穿过来，拧进前壳的攻牙孔。"""
    tabs, holes = [], []
    for zz in (30 * K, 100 * K):
        for s in (1, -1):
            r = inner_r(zz)
            x0, x1 = sorted((s * (r - 9), s * (r + 0.5)))
            y0, y1 = (0, 6) if front else (-6, 0)
            tabs.append(box(x0, x1, y0, y1, zz - 4, zz + 4))
            if front:      # 前壳这侧攻 M2 牙：螺丝从后壳穿过来，直接拧进前壳，不用在壳里塞螺母
                holes.append(cyl_y(hole(TAP_M2, 24), -8, 8, s * (r - 5), zz, 24))
            else:          # 后壳这侧是 M2 过孔
                holes.append(cyl_y(hole(1.0 + FIT, 24), -8, 8, s * (r - 5), zz, 24))
    return tabs, holes


# ToF 避障窗口（VL53L1X）：窗口中心离地 22（随比例缩放），光轴上仰 10°。
# 盖片和传感器是买来的实际尺寸，不缩放：盖片 10 × 6 × 1（样机用 1 mm 红外透光亚克力），开口 8 × 4。
TOF_Z, TOF_TILT = 22, 10
COVER_W, COVER_H, COVER_T = 10.0, 6.0, 1.0
TOF_W, TOF_H = 8.0, 4.0
BOSS_T = 2.0                     # 凸台厚度：VL53L1X 芯片高 1.56，模块板贴在凸台背面，芯片顶面离盖片约 0.44


def tof_window():
    """返回 (凸台, 盖片槽 + 开口)。局部坐标：x 向右，y 沿光轴向前，z 沿窗口向上；盖片内表面在 y=0。
    盖片做成平的、垂直于光轴，下沿和外壳表面齐平，上沿因为外壳往外鼓，会缩进去 3 mm 多，像一道小眉檐。"""
    a = math.radians(TOF_TILT)
    zc = TOF_Z * K
    # 让盖片外表面的下沿刚好落在外壳表面上
    yc = 0.0
    for _ in range(30):
        zb = zc + COVER_T * math.sin(a) - (COVER_H / 2) * math.cos(a)
        yc = prof(zb) - COVER_T * math.cos(a) - (COVER_H / 2) * math.sin(a)
    place = lambda m: m.rotate([TOF_TILT, 0, 0]).translate([0, yc, zc])
    boss = place(box(-9, 9, -BOSS_T, 15, -6.5, 6.5))
    pocket = place(box(-COVER_W / 2 - FIT, COVER_W / 2 + FIT, 0, 20, -COVER_H / 2 - FIT, COVER_H / 2 + FIT))
    hole = place(box(-TOF_W / 2, TOF_W / 2, -BOSS_T - 1, 1, -TOF_H / 2, TOF_H / 2))
    # 盖片外面的开口按光束张角做成喇叭口：上沿往上张 25°、左右各张 15°（大于光束的 18.5° / 13.5°），光束不会擦到眉檐
    hw, hh = COVER_W / 2 + FIT, COVER_H / 2 + FIT
    front = box(-30, 30, COVER_T, 25, -hh, 30)
    up = box(-hw, hw, 0, 40, -40, 0).rotate([25, 0, 0]).translate([0, COVER_T, hh])
    sides = [(box(-40, 0, 0, 40, -hh, hh) if s > 0 else box(0, 40, 0, 40, -hh, hh)).rotate([0, 0, -s * 15]).translate([s * hw, COVER_T, 0]) for s in (1, -1)]
    flare = (up + box(-hw, hw, COVER_T, 25, -hh, hh)) ^ front
    for sd, s in zip(sides, (1, -1)):
        flare = flare + ((sd ^ front) ^ box(-30 if s < 0 else 0, 30 if s > 0 else 0, COVER_T, 25, -hh, hh))
    return boss, pocket + hole + place(flare)


def half(front):
    body = shell_body() - cutters()
    if front:
        boss, cut = tof_window()
        solid = revolve([(0.01, Y0 * K)] + [(prof(h), h) for h in np.linspace(Y0 * K, YCAP * K, 90)] + [(0.01, YCAP * K)])
        body = (body + (boss ^ solid)) - cut
    big = 200 * K
    body = body ^ (box(-big, big, 0, big, -big, big) if front else box(-big, big, -big, 0, -big, big))
    if not front:
        body = body + door_rails()
    for th in BASE_SCREWS:
        if (math.sin(math.radians(th)) > 0) == front:
            body = body + base_boss(th)
    tabs, holes = seam_tabs(front)
    solid_inside = revolve([(0.01, Y0 * K), (prof(Y0 * K), Y0 * K)] + [(prof(h), h) for h in np.linspace(Y0 * K, YCAP * K, 60)] + [(0.01, YCAP * K)])
    for t in tabs:
        body = body + (t ^ solid_inside)       # 耳朵不能戳出外壳
    for h in holes:
        body = body - h
    return body


def base_boss(th):
    """外壳内壁底部的一根螺丝柱（Ø6.5，高 BOSS_H）加一条连到壳壁的筋，底面正好顶住底盘上表面。柱上是 M2 攻牙底孔。"""
    z0 = Y0 * K
    zb0, zb1 = z0 + 2.5, z0 + 2.5 + BOSS_H
    t = math.radians(th)
    x, y = BASE_SCREW_R * math.cos(t), BASE_SCREW_R * math.sin(t)
    boss = cyl_z(3.25, zb0, zb1, x, y, 32)                     # Ø6.5，攻 M2 后柱壁约 2.2 mm
    # 筋伸到壁里、但停在外表面里面 0.5（壁厚 2，照样连牢）；上下各多 1，不和柱顶、柱底共面
    inside = revolve([(0.01, zb0 - 1)] + [(prof(h) - 0.5, h) for h in np.linspace(zb0 - 1, zb1 + 1, 24)] + [(0.01, zb1 + 1)])
    rib = (box(BASE_SCREW_R, 80, -2, 2, zb0, zb1).rotate([0, 0, th])) ^ inside
    return (boss + rib) - cyl_z(hole(TAP_M2, 24), zb0 - 1, zb1 + 1, x, y, 24)


LENS_LIP, LENS_LIP_T = 3.0, 1.2    # 镜片背面翻边：比窗口四周大 3 mm，厚 1.2
LENS_RISE = 0.5                    # 镜片外表面比壳面高 0.5，外沿倒 R0.5 圆边（3D 模型里高 0.7）：
                                   # 摸过去是一道圆滑的小台阶，不会摸到沟；打印 ±0.1–0.2 的高低差也藏在台阶里


def lens():
    """表情窗的弧面镜片（透明树脂打印，内外抛光，内面喷透明茶色漆）。
    · 嵌进窗口的部分：四周比窗口小 FIT，外表面比壳面高 LENS_RISE、外沿是 R LENS_RISE 的圆边，
      往里伸到内壁再往里 0.3，和翻边连成一体；
    · 背面一圈翻边：比窗口四周大 LENS_LIP、厚 LENS_LIP_T，贴在前壳内壁上，用胶粘住。
      翻边顶住内壁，镜片就推不出去，外表面的高度由翻边定住，不靠手感去对。"""
    z0, z1 = WIN_Z0F * K, WIN_Z1F * K                             # 上下由 win_prism 再缩 FIT
    hs = np.linspace(Y0 * K, YCAP * K, 90)                       # 和 shell_body 外壁同一组点
    ro = np.array([prof(h) for h in hs])
    hz = [z0 - 1] + [h for h in hs if z0 - 1 < h < z1 + 1] + [z1 + 1]
    hi = np.linspace(z0 - 1, z1 + 1, 120)
    inner = [(inner_r(h) - 0.3, h) for h in hi[::-1]]
    rmin = min(inner_r(h) for h in hi)
    # 和窗口同一个圆角矩形，四周缩 FIT（角度方向按最小半径换算，外圈间隙更宽）。
    # 圆边用 7 层叠出来：第 k 层往里缩 e、高出壳面 t，(e, t) 落在 R LENS_RISE 的四分之一圆上（每层只差 0.01–0.1，打磨后是圆的）
    inset = None
    for th in np.linspace(0, math.pi / 2, 7):
        e, t = LENS_RISE * (1 - math.cos(th)), LENS_RISE * math.sin(th)
        outer = [(float(np.interp(h, hs, ro)) + t, h) for h in hz]
        layer = revolve(outer + inner) ^ win_prism(-FIT - e, rmin)
        inset = layer if inset is None else inset + layer
    zf0, zf1 = WIN_Z0F * K - LENS_LIP, WIN_Z1F * K + LENS_LIP
    rf = min(inner_r(h) for h in np.linspace(zf0, zf1, 60))
    flange = band(zf0, zf1, -0.05, 0.05 + LENS_LIP_T, n=120) ^ win_prism(LENS_LIP, rf)
    return inset + flange


# ---------------- 表情屏支架 + 遮光罩 ----------------
# 表情屏是一块平的 2.4 寸 SPI 屏（ST7789），横着装在镜片后面；镜片只是一扇深色的窗，不显示东西。
# 屏幕画面的背景全黑，和茶色镜片融成一片，看不出屏幕的方框，只有发光的眼睛透出来。
# 外壳横竖两个方向都弯，越往上越收：平屏的四角会先碰到壳壁，所以屏幕上沿往后仰 SCR_TILT，
# 屏幕中心在镜片背面后面约 18 mm（脚本运行时打印实际值）。中间这段用一个黑色漏斗形遮光罩包住：
# 前口是整个表情窗（屏幕两边的窗也是黑的，看不到里面的线和骨架），后口是屏幕的显示区。
# 屏幕模块尺寸（买来的零件，不缩放；按自己买到的屏量一下，改这里再重新生成）：
SCR_GLASS = (60.3, 42.7, 2.6)     # 玻璃 + 背光：宽、高、厚
SCR_AA = (48.96, 36.72)           # 显示区（240 × 320 横放）
SCR_PCB_X = (-31.2, 46.0)         # PCB 左右范围（以玻璃中心为 0）：排针那头多出约 15，默认排针在右边（从正面看）
SCR_PCB_T, SCR_BACK = 1.6, 3.0    # PCB 厚、PCB 背面元件高
SCR_TILT = 13.0                   # 屏幕上沿往后仰的角度（度）
SCR_DZ = -5.0                     # 屏幕中心比表情窗中心低多少（往下挪一点，上面两个角才放得进去）
SHROUD_W = 1.6                    # 屏幕框四周的壁厚
SHROUD_RIM = 3.0                  # 遮光罩前口贴壳内壁的那圈宽度（在镜片翻边外面）


def _scr_place(m, ys):
    """屏幕局部坐标（x 右，y 沿屏幕法线向前，z 上；玻璃正面中心是原点）→ 机身坐标。"""
    zc = (WIN_Z0F + WIN_Z1F) / 2 * K + SCR_DZ
    return m.rotate([SCR_TILT, 0, 0]).translate([0, ys, zc])


def screen_ys(margin=0.8):
    """屏幕能往前放到哪：玻璃、PCB、背面元件的每个角都离镜片翻边背面 / 壳内壁至少 margin。"""
    zc = (WIN_Z0F + WIN_Z1F) / 2 * K + SCR_DZ
    a = math.radians(SCR_TILT)
    gw, gh, gt = SCR_GLASS
    pts = [(x, 0.0, z) for x in (-gw / 2, gw / 2) for z in (-gh / 2, gh / 2)]
    for d in (-gt, -gt - SCR_PCB_T, -gt - SCR_PCB_T - SCR_BACK):
        pts += [(x, d, z) for x in SCR_PCB_X for z in (-gh / 2, gh / 2)]
    lim = lambda h: inner_r(h) - LENS_LIP_T - 0.35 - margin

    def ok(ys):
        for x, d, z in pts:
            y, h = ys + d * math.cos(a) - z * math.sin(a), zc + z * math.cos(a) + d * math.sin(a)
            if math.hypot(x, y) >= lim(h):
                return False
        return True
    lo, hi = 20.0, 80.0
    for _ in range(50):
        m = (lo + hi) / 2
        lo, hi = (m, hi) if ok(m) else (lo, m)
    return lo


def screen_shroud():
    """表情屏支架 + 遮光罩（一个黑色打印件）：
    · 后面是屏幕框：玻璃从后面放进框里，前面一圈 1 mm 的唇挡住玻璃，唇上的开口正好是显示区 + 每边 0.5；
      PCB 压在框的背面，用两条胶带或几点热熔胶固定；
    · 中间是漏斗：从显示区一直张到整个表情窗，内壁全黑；
    · 前口一圈贴在前壳内壁上（在镜片翻边外面），里圈压住镜片翻边，留 0.35 的胶缝。
      用 B-7000 把前口粘在壳内壁和翻边上：遮光罩一圈都封住，屏幕边上不漏光，同时把镜片从里面压住。"""
    ys = screen_ys()
    gw, gh, gt = SCR_GLASS
    aw, ah = SCR_AA
    lip = 1.0
    # 外形：前口那圈（贴壳内壁的一条带子）和屏幕框外形取凸包，再裁到壳内壁以内
    z0, z1 = WIN_Z0F * K - LENS_LIP - SHROUD_RIM - 1, WIN_Z1F * K + LENS_LIP + SHROUD_RIM + 1
    rf = min(inner_r(h) for h in np.linspace(z0, z1, 60))
    rim = band(z0, z1, -0.1, 3.0, n=120) ^ win_prism(LENS_LIP + SHROUD_RIM, rf)
    frame_out = _scr_place(box(-gw / 2 - SHROUD_W, gw / 2 + SHROUD_W, -gt - 0.3, lip, -gh / 2 - SHROUD_W, gh / 2 + SHROUD_W), ys)
    inside = revolve([(0.01, z0 - 5)] + [(inner_r(h) - 0.1, h) for h in np.linspace(z0 - 5, z1 + 5, 120)] + [(0.01, z1 + 5)])
    body = Manifold.batch_hull([rim, frame_out]) ^ inside
    # 让开镜片翻边（+0.35 胶缝）
    keep = band(z0, z1, 1.0, LENS_LIP_T + 0.05 + 0.35, n=120) ^ win_prism(LENS_LIP + 0.35, rf)
    body = body - keep
    # 漏斗内腔：前面是整个表情窗，后面是唇上的显示区开口
    front = band(z0, z1, 1.0, LENS_LIP_T + 0.05 + 0.35 + 0.01, n=120) ^ win_prism(0.0, rf)
    back = _scr_place(box(-aw / 2 - 0.5, aw / 2 + 0.5, lip - 0.01, lip + 0.01, -ah / 2 - 0.5, ah / 2 + 0.5), ys)
    body = body - Manifold.batch_hull([front, back])
    body = body - _scr_place(box(-aw / 2 - 0.5, aw / 2 + 0.5, -1, lip + 0.5, -ah / 2 - 0.5, ah / 2 + 0.5), ys)   # 唇上的开口
    body = body - _scr_place(box(-gw / 2 - 0.3, gw / 2 + 0.3, -gt - 5, 0, -gh / 2 - 0.3, gh / 2 + 0.3), ys)   # 放玻璃的框
    # 让开摄像头（孔、沉台和后面的模组）
    camk = Manifold.cylinder(60, 10, 10, 48).translate([0, 0, -30]).rotate([-(90 - 29), 0, 0]).translate([0, 18 * K, 93 * K])
    body = body - camk     # 不能减 cutters()：里面的表情窗切口沿半径一直伸到壳里，会把整个漏斗切掉
    body = max(body.decompose(), key=lambda p: p.volume())    # 裁切边上会剩下体积为 0 的碎片，只留主体
    return body.simplify(0.01)    # 去掉存成 STL 后会变成零面积的细小三角形（否则切片软件报“问题边”）


def cap():
    """顶盖：离地 119 以上，带一圈向下的止口；两条槽让耳朵的摆杆穿出来。"""
    hs = np.linspace(YCAP * K, YTOP * K - 0.01, 40)
    outer = [(prof(h), h) for h in hs] + [(0.0, YTOP * K)]
    # 内表面也沿法向往里 WALL（和外壳一样），盖子边缘不会变成薄片
    top_in = YTOP * K - WALL
    his = [h for h in np.linspace(YCAP * K, top_in, 60) if inner_off(h) > 0.2]
    inner = [(0.0, top_in)] + [(inner_off(h), h) for h in his[::-1]]
    dome = revolve(outer + inner)
    r = min(inner_r(h) for h in np.linspace((YCAP - 3) * K, YCAP * K, 40)) - FIT
    # 止口往上伸进盖子里，直到碰到盖子内壁（多伸 0.5），和盖子连成一体
    join = next(h for h in np.linspace(YCAP * K, top_in, 400) if inner_off(h) <= r - 0.8) + 0.5
    lip = revolve([(r - 1.6, (YCAP - 3) * K), (r, (YCAP - 3) * K), (r, join), (r - 1.6, join)])
    part = dome + lip
    for s in (1, -1):
        x0, x1 = sorted((s * 16.5 * K, s * 23.5 * K))        # 耳朵摆杆的槽，中心在 ±20 × 比例
        part = part - box(x0, x1, -9 * K, 9 * K, (YCAP - 4) * K, (YTOP + 2) * K)
    return part


def base_plate():
    """底盘：嵌在外壳底部开口里，带四个滑垫、三个悬崖传感器窗、三个螺丝孔（M2 拧进外壳的螺丝柱）。
    滑垫分在左右两侧（x = ±24.5），中间留出一条空道：倒车上充电座时，滑垫从接口台两边走过去，不会撞上。"""
    z0 = Y0 * K
    inner_r(z0)
    r = R_OPEN - FIT
    p = revolve([(0.01, z0), (r - 0.8, z0), (r, z0 + 0.8), (r, z0 + 2.5), (0.01, z0 + 2.5)])   # 下沿倒角 0.8，过板边更顺
    for x, y in PADS:
        p = p + cyl_z(PAD_R, 1.0, z0 + 0.1, x, y, 32)            # 滑垫底面比轮子最低点高 1 mm
    # 悬崖传感器窗：放得下 TCRT5000 本体（10.2 × 5.8），长边前后方向；后面那个往右偏 9
    for x, y in ((-11, 15), (11, 15), (9, -17)):
        p = p - box(x * K - 2.9 - FIT, x * K + 2.9 + FIT, y * K - 5.1 - FIT, y * K + 5.1 + FIT, z0 - 1, z0 + 4)
    p = p - cyl_z(hole(12 + FIT, 64), z0 - 1, z0 + 1.0, seg=64)                   # 垫片槽：DIN988 17 × 24 × 1 锰钢垫片，和底面齐平，给座子的磁铁吸
    p = p - cyl_z(hole(8 + FIT, 48), z0 - 1, z0 + 1.6, seg=48)                  # 触点板槽：Ø16 × 1.6 的四环触点板，和底面齐平
    p = p + cyl_z(10.5, z0 + 2.4, z0 + 2.5 + 1.0, seg=64)          # 中间加厚 1 mm：触点板槽（深 1.6）上方从 0.9 变成 1.9 mm
    p = p - cyl_z(2.5, z0 - 1, z0 + 5, seg=24)                    # 触点板背面的 4 根线从这里穿上去
    p = p + box(-9, 9, -(r - 1), -(r - 9), z0 + 2.4, z0 + 5.5)    # 后缘垫块：USB-C 充电板粘在上面，口朝后对准窗口（往下压 0.1 和底盘连成一体）
    for a in BASE_SCREWS:              # 三个 M2 过孔，螺丝从底下穿上去拧进外壳的螺丝柱
        p = p - cyl_z(hole(1.0 + FIT, 24), z0 - 1, z0 + 4, BASE_SCREW_R * math.cos(math.radians(a)), BASE_SCREW_R * math.sin(math.radians(a)), 24)
    return p


def frame():
    """内部骨架：一块立板（在左右方向的平面里）加三层搁板，电池、主板、舵机都放在上面。
    电机卡在立板下方的两个缺口里。这是起步版，孔位请按你买到的零件核对后再打印。"""
    FB = Y0 * K + 2.5 + 1.0 + 0.5                                # 骨架底边：底盘中间圆台顶再往上 0.5
    hs = np.linspace(FB, 112 * K, 70)
    def gap(h):                       # 离内壁：沿半径 1 mm，壁很斜的地方再放大，保证垂直于壁面至少 FIT
        sl = abs(inner_r(h + 0.05) - inner_r(h - 0.05)) / 0.1
        return max(1.0, (FIT + 0.05) * math.sqrt(1 + sl * sl))
    outline = [(inner_r(h) - gap(h), h) for h in hs]
    pts = outline + [(-r, h) for r, h in outline[::-1]]
    plate = Manifold.extrude(CrossSection([ccw(pts)]), 3).translate([0, 0, -1.5]).rotate([90, 0, 0])   # XZ 平面的立板，厚 3
    inside = revolve([(0.01, FB)] + outline + [(0.01, 112 * K)])
    shelves = [
        box(-40 * K, 40 * K, -22, 22, 35 * K - 2, 35 * K),          # 电池盒搁板
        box(-36, 36, -16, 26, 60 * K - 2, 60 * K),                  # 主板搁板（树莓派 Zero 65 × 30）
        box(-42, 42, -15, 15, 97 * K - 2, 97 * K),                  # 舵机搁板
    ]
    f = plate
    for sh in shelves:
        f = f + (sh ^ inside)
    for s in (1, -1):
        # 电机缺口（N20：截面 10 × 12，含减速箱长约 24）和两条扎带槽
        x0, x1 = sorted((s * (WHEEL_X - 32), s * (WHEEL_X - 5)))
        f = f - box(x0, x1, -5, 5, AXLE_Z - 6.2, AXLE_Z + 6.2)
        for zz in (AXLE_Z - 10, AXLE_Z + 8):
            f = f - box(min(x0, x1) + 8, min(x0, x1) + 12, -5, 5, zz, zz + 2)
        # 给轮子让位
        xa, xb = sorted((s * (WHEEL_X - 7), s * 200))
        f = f - box(xa, xb, -30, 30, -1, AXLE_Z * 2 + 4)
        # 树莓派 Zero 的四个安装孔：58 × 23，M2.5
        for dy in (-6.5, 16.5):
            f = f - cyl_z(hole(1.25 + FIT, 24), 60 * K - 4, 60 * K + 1, s * 29, dy, 24)
    # 让开前后壳合缝处的螺丝耳（M2 螺丝从这里穿过）
    for zz in (30 * K, 100 * K):
        for s in (1, -1):
            r = inner_r(zz)
            x0, x1 = sorted((s * (r - 9 - FIT), s * (r + 1)))
            f = f - box(x0, x1, -6 - FIT, 6 + FIT, zz - 4 - FIT, zz + 4 + FIT)
    # 走线孔
    f = f - cyl_y(7, -5, 5, 0, 48 * K, 32) - cyl_y(7, -5, 5, 0, 80 * K, 32)
    return f


def ear():
    """耳朵：胶囊形，下面带一根摆杆，摆杆末端的孔锁在舵机摇臂上。用 TPU 软料打印。"""
    r, h = 6 * K, 14 * K
    cap_ = cyl_z(r, 0, h, seg=48) + Manifold.sphere(r, 48) + Manifold.sphere(r, 48).translate([0, 0, h])
    stem = box(-2, 2, -3.5, 3.5, -22 * K, 0)
    return (cap_ + stem - cyl_x(hole(1.0 + FIT, 20), -4, 4, 0, -22 * K + 4, 20)).translate([0, 0, 22 * K])


def save(name, m):
    mesh = m.to_mesh()
    tm = trimesh.Trimesh(vertices=np.asarray(mesh.vert_properties)[:, :3], faces=np.asarray(mesh.tri_verts), process=False)
    os.makedirs(OUT, exist_ok=True)
    tm.export(os.path.join(OUT, name + ".stl"))
    lo, hi = tm.bounds
    print(f"{name:12s} 封闭={tm.is_watertight}  体积={tm.volume / 1000:6.1f} cm³  "
          f"尺寸={hi[0] - lo[0]:.1f} × {hi[1] - lo[1]:.1f} × {hi[2] - lo[2]:.1f} mm  三角面={len(tm.faces)}")
    return tm


def iface(t, r_edge, pins, floor=3):
    """在托盘 / 底板上加接口凸台：6 个圆片磁铁坑、弹针孔、凸台下面的走线腔，以及一条通到后边缘的走线槽。
    t 的上表面是 Z=0，底板厚 floor。r_edge：后边缘离中心的距离，走线槽通到这里。"""
    boss_h = Y0 * K - 0.5                                        # 凸台顶离底盘垫片 0.5 mm
    t = t + Manifold.cylinder(boss_h, 16, 15.5, 64)              # 接口凸台：磁铁坑外圈约 1.7 mm（v1.1 是 0.7）
    for a in MAG_ANG:                                            # 6 个 Ø6 × 3 磁铁坑，深 3.1（磁铁顶面比凸台低 0.1）
        t = t - cyl_z(hole(MAG_D / 2 + FIT, 32), boss_h - MAG_T - 0.1, boss_h + 1, MAG_R * math.cos(math.radians(a)), MAG_R * math.sin(math.radians(a)), 32)
    t = t - cyl_z(8.5, -(floor - 1.5), boss_h - 4.6, seg=48)     # 走线腔：弹针尾巴在这里焊线；上面离磁铁坑 1.5，底下留 1.5
    for r, a in pins:                                            # 弹针孔：Ø1.5 的针 + 间隙，胶固定；针头露出凸台约 1.2 mm
        t = t - cyl_z(hole(0.75 + FIT, 16), -(floor - 1.5), boss_h + 1, r * math.cos(math.radians(a)), r * math.sin(math.radians(a)), 16)
    t = t - box(-1.5, 1.5, -(r_edge + 1), -6, -(floor - 1.5), 0.1)  # 走线槽，宽 3 深 1.5（槽底留 1.5），装好后用胶带盖住
    return t


def clip_tray():
    """显示器夹座的上半部分：托盘 + 围边 + 磁铁凸台 + 夹板 + 前唇 + 铰链耳。托盘上表面是 Z=0。"""
    reach = math.hypot(WHEEL_X + WHEEL_W / 2, WHEEL_D / 2)       # 机器人原地转一圈，轮子外角扫过的半径
    ri = reach + 2.5                                             # 托盘内半径
    t = Manifold.cylinder(3, ri + 2.5, ri + 2.5, SEG).translate([0, 0, -3])                 # 托盘底，厚 3
    t = t + (Manifold.cylinder(8, ri + 2.5, ri + 2.5, SEG) - Manifold.cylinder(9, ri, ri, SEG))   # 围边，高 8
    t = iface(t, ri + 2.5, PINS_USB)
    t = t + box(-32, 32, -34, 16, -6, -3)                        # 压在屏幕顶面的夹板，宽 64
    t = t + box(-32, 32, 13, 16, -22, -6)                        # 前唇，向下 16
    for s in (1, -1):                                            # 铰链耳
        x0, x1 = sorted((s * 21, s * 29))
        t = t + box(x0, x1, -42, -30, -15, -3)
    t = t - cyl_x(hole(1.5 + FIT, 24), -40, 40, -36, -10, 24)              # 铰链轴孔，穿 M3 螺丝
    # 托盘后侧的 USB-C 小板仓：放一块带 D+/D− 的 USB-C 母座转接板（约 15 × 10），口朝后，线接电脑
    yb = -(ri + 2.5)
    t = t + box(-10, 10, yb - 13, yb + 1, -3, 8)
    t = t - box(-8.5, 8.5, yb - 11.5, yb, -1.5, 9)               # 上面敞口，放好板子后用胶带或热熔胶封
    t = t - box(-5, 5, yb - 14, yb - 11.4, 0.6, 4.6)             # 母座开口 10 × 4
    t = t - box(-1.5, 1.5, yb - 0.5, -(ri - 1), -2, 2)           # 穿过围边，接上走线槽
    return t


# ---------------- 地面充电座（能自己倒车开上来的版本） ----------------
# 坐标：接口台中心是原点，后墙在 -Y，机器人从 +Y 那边倒车进来。底板上表面 Z=0，地面 Z=GROUND。
# v1.2：底板从 3 加厚到 4.1，放得下更厚的底盖环、凸缘和内唇；直接平放在地上，不再垫 2 mm 脚垫
# （脚垫会把缓坡边缘垫高到 2.6 mm，比机器人滑垫离地的 1 mm 还高，倒车会顶住）。
GROUND = -4.1
DOCK_R = 84 * K                   # 底板半径
RAMP_W, RAMP_LIP = 29.0, 0.6      # 底板外圈 29 mm 宽的缓坡，坡度约 7°；边缘 0.6 mm 不能再厚：要比机器人滑垫离地的 1 mm 低
DOCK_YF = -(RB * K + 8)           # 后墙正面
DOCK_WD = 22.0                    # 后墙厚度（里面放信标板、USB-C 转接板和配重）
RAIL_X = WHEEL_X + WHEEL_W / 2 + 2    # 导轨内侧：轮子外侧再留 2 mm
RAIL_H, RAIL_T = 5.0, 3.0
PLUG_R, PLUG_FT = 14.8, 1.2       # 浮动接口台：本体半径（磁铁坑外圈 1.5 mm）、底部凸缘厚
PLUG_FL = PLUG_R + FIT + 1.2      # 凸缘半径：比内唇开口多 1.2，卡得住
PLUG_FLOAT = 2.0                  # 接口台能左右（X 方向）各滑 2 mm：轮子在导轨里还有 ±2 mm 余量，靠磁铁把接口台拉到垫片正下方
PLUG_DOWN, PLUG_UP = 3.6, 6.9 + 0.1           # 接口台顶面：平时落在 3.6（弹针头 4.6，比机器人后倾时外壳最低处 4.7 还低）；被磁铁吸起最多到 7.0，底盘在 6.9 先贴上
SLEEVE_TOP = 3.6
CAP_T = 1.6                       # 底盖环厚（v1.1 是 0.8）
CAP_R = PLUG_FL + FIT + PLUG_FLOAT + 2.0     # 盖住套筒底口，四周多 2 mm 粘胶
PLUG_Z0 = GROUND + CAP_T          # 接口台落下时底面的高度（压在底盖环上）
PLUG_H = PLUG_DOWN - PLUG_Z0
LIP_Z = PLUG_Z0 + PLUG_FT + (PLUG_UP - PLUG_DOWN) + 0.1     # 套筒内唇下沿：凸缘顶到这里就停（内唇厚约 1 mm）
BEACON_Z = IR_RX_Z * K            # 信标灯高度 = 机器人接收头高度
BEACON_SIDE = 27                  # 左右两颗信标灯斜着照的角度（度）
# 后墙下方两块挡块：机器人倒车时外壳碰到它就停，这时机身中心正好在接口台上方（前后误差 < 0.5 mm）。
# 挡块在轮轴附近的高度（离地 17–27），机身前后点头时这里几乎不移动；贴 1 mm 毛毡。
STOP_X0, STOP_X1, STOP_Z0, STOP_Z1, FELT = 17.0, 25.0, 17.0, 27.0, 1.0


def stadium(hx, hy, z0, z1, cut=False):
    """俯视是跑道形（X 方向长）的柱子：半长 hx、半宽 hy。cut=True 时当孔用，圆头按外切算，不会比标称小。"""
    if cut:
        e = hole(hy, 128) - hy
        hx, hy = hx + e, hy + e
    d = max(hx - hy, 0.01)
    return box(-d, d, -hy, hy, z0, z1) + cyl_z(hy, z0, z1, -d, 0, 128) + cyl_z(hy, z0, z1, d, 0, 128)


def rail(x_sign):
    """一侧导轨：靠墙一段笔直，前面一段往外张开 20°，像个漏斗，把轮子引到正中。"""
    xs = x_sign
    pts = [(xs * RAIL_X, DOCK_YF + 1), (xs * RAIL_X, 5.0), (xs * (RAIL_X + 12), 38.0),
           (xs * (RAIL_X + 12 + RAIL_T), 38.0), (xs * (RAIL_X + RAIL_T), 5.0), (xs * (RAIL_X + RAIL_T), DOCK_YF + 1)]
    m = Manifold.extrude(CrossSection([ccw(pts)]), RAIL_H - GROUND + 0.5).translate([0, 0, GROUND - 0.5])
    return m


def beacon_block():
    """后墙里的信标块：三颗 5 mm 红外灯。中间一颗在 8 mm 长的 Ø2.4 细孔后面，光束很窄，只照正前方一条线；
    左右两颗斜着 27° 往两边照（和中间那束有一点重叠，不留空隙）。返回 (实体, 要挖掉的孔)。"""
    y0, y1 = DOCK_YF - 16, DOCK_YF
    z = BEACON_Z
    solid = box(-17, 17, y0, y1, z - 7, z + 7)
    holes = cyl_y(1.2, DOCK_YF - 9, DOCK_YF + 1, 0, z, 24)                 # 中间：细长光阑
    holes = holes + cyl_y(hole(2.5 + FIT, 32), y0 - 1, DOCK_YF - 8.9, 0, z, 32)       # 中间：灯座
    holes = holes + cyl_y(hole(2.9 + FIT, 32), y0 - 1, y0 + 1.0, 0, z, 32)            # 灯的凸缘
    for s_ in (1, -1):
        h = cyl_y(hole(2.5 + FIT, 32), -12, 14, 0, 0, 32).rotate([0, 0, -s_ * BEACON_SIDE]).translate([s_ * 9, DOCK_YF - 7, z])
        holes = holes + h
    return solid, holes


def dock_base():
    """地面充电座：
    · 底板外圈是一圈 7° 的缓坡，边缘只有 0.6 mm 厚，轮子和滑垫都能顺着开上来；
    · 左右两条低导轨（高 5）做成漏斗，把轮子引到正中，最后左右各只留 2 mm 余量；
    · 中间是套筒，里面放浮动接口台（dock_plug，单独打印）：平时落下去，机器人倒车经过时碰不到；
      到位后磁铁把它吸起来、左右拉正，贴住底盘垫片，两根弹针接通 VBUS 和 GND；
    · 后墙下方两块挡块定住前后位置：机器人倒车碰到挡块就停，正好在接口台上方；
    · 后墙正面有三颗红外信标灯（左、中、右）和状态灯缝，背面下方是 USB-C 电源口，墙里放信标小板和配重。"""
    plate = revolve([(0.01, GROUND), (DOCK_R, GROUND), (DOCK_R, GROUND + RAMP_LIP), (DOCK_R - RAMP_W, 0), (0.01, 0)])
    yf, d = DOCK_YF, DOCK_WD
    w, h = 30 * K, 85 * K
    wall = box(-w, w, yf - d, yf, GROUND - 0.5, h) - box(-w + 2, w - 2, yf - d + 2, yf - 2, -1, h - 2)
    bs, bh = beacon_block()
    wall = wall + (bs ^ box(-w, w, yf - d, yf, GROUND - 0.5, h))
    wall = wall - bh
    wall = wall - box(-5, 5, yf - d - 1, yf - d + 3, 1.5, 5.5)                # 背面 USB-C 开口 10 × 4
    wall = wall - box(-15 * K, 15 * K, yf - 3, yf + 1, 70 * K, 70 * K + 3)    # 正面状态灯缝
    # 挡块：面到机身中心的距离 = 外壳在这里的半径（按挡块内侧边、上沿算）+ 毛毡厚
    ys = -math.sqrt(prof(STOP_Z1) ** 2 - STOP_X0 ** 2) - FELT
    for s_ in (1, -1):
        x0, x1 = sorted((s_ * STOP_X0, s_ * STOP_X1))
        wall = wall + box(x0, x1, yf - 1, ys, GROUND - 0.5, STOP_Z1)
    t = (plate + wall + rail(1) + rail(-1)) ^ box(-300, 300, -300, 300, GROUND, 300)   # 墙、导轨先往下多伸 0.5，再沿地面切平：底面是一个干净的平面
    # 接口台套筒：俯视是跑道形，左右长（接口台能左右滑 2 mm），顶面离底板 3.6（比机器人外壳最低处还低），
    # 上口一圈内唇在前后两边压住接口台的凸缘，吸起来也拔不出去
    fx, fy = PLUG_FL + FIT + PLUG_FLOAT, PLUG_FL + FIT
    t = t + stadium(fx + 1.2, fy + 1.5, -0.5, SLEEVE_TOP)
    t = t - stadium(fx, fy, PLUG_Z0, LIP_Z, cut=True)                                    # 凸缘上下、左右滑的腔
    t = t - stadium(PLUG_R + FIT + PLUG_FLOAT, PLUG_R + FIT, LIP_Z - 1, SLEEVE_TOP + 1, cut=True)   # 本体穿出内唇
    t = t - cyl_z(hole(CAP_R + FIT, 64), GROUND - 1, PLUG_Z0, seg=64)                      # 底面沉槽，放底盖环（和底面齐平）
    # 底面走线槽：从套筒通到后墙里，宽 3 深 1.5；进墙的地方往上打穿
    t = t - box(-1.5, 1.5, yf - 8, -(CAP_R - 2), GROUND - 1, GROUND + 1.5)
    t = t - box(-1.5, 1.5, yf - 8, yf - 3, GROUND - 1, 0.5)
    # 底面 4 个 1 mm 深的浅坑，贴 1 mm 自粘防滑垫后和底面齐平（不垫高充电座）
    for a in (45, 135, 225, 315):
        t = t - cyl_z(8.3, GROUND - 1, GROUND + 1.0, 55 * math.cos(math.radians(a)), 55 * math.sin(math.radians(a)), 48)
    return t


def dock_plug():
    """浮动接口台：放在充电座的套筒里，上下能滑 3.6 mm，左右能滑 2 mm。顶面一圈 6 颗 Ø6 × 3 圆片磁铁，中间两根弹针（VBUS、GND）。
    平时靠自重落在底盖环上（顶面离底板 3.6）；机器人停到位，磁铁隔着空气把它吸上去，贴住底盘的锰钢垫片。打印时凸缘朝下。"""
    H = PLUG_H
    p = cyl_z(PLUG_FL, 0, PLUG_FT, seg=64) + revolve([(0.01, PLUG_FT - 0.1), (PLUG_R, PLUG_FT - 0.1), (PLUG_R, H - 0.3), (PLUG_R - 0.3, H), (0.01, H)])
    for a in MAG_ANG:                                                                    # 6 个 Ø6 × 3 磁铁坑
        p = p - cyl_z(hole(MAG_D / 2 + FIT, 32), H - MAG_T - 0.1, H + 1, MAG_R * math.cos(math.radians(a)), MAG_R * math.sin(math.radians(a)), 32)
    p = p - cyl_z(8.5, -1, H - 4.6, seg=48)                                              # 弹针尾巴焊线的腔（上面离磁铁坑 1.5）
    for r, a in PINS_POWER:
        p = p - cyl_z(hole(0.75 + FIT, 16), -1, H + 1, r * math.cos(math.radians(a)), r * math.sin(math.radians(a)), 16)
    return p


def dock_cap():
    """底盖环：从充电座底面卡进沉槽，托住接口台，用 502 或热熔胶粘住。中间的孔和一道缺口让弹针的线出来，接到走线槽。"""
    c = cyl_z(CAP_R, 0, CAP_T, seg=64) - cyl_z(9.0, -1, CAP_T + 1, seg=48)
    return c - box(-1.6, 1.6, -CAP_R - 1, -8, -1, CAP_T + 1)   # 缺口对着底面走线槽


# 轮子：打印轮毂 + 两根并排的标准 O 型圈（内径 38、线径 3）当轮胎，套上后外径约 44、宽 10，和 WHEEL_D / WHEEL_W 一样。
# 市面上配 N20 的 D 孔轮只有 43 × 19（太宽，塞不进轮舱）和 34 × 7（太小），所以自己打印轮毂。
HUB_ROOT, HUB_GROOVE_W, HUB_FLANGE = 38.4, 6.6, 2.3   # 槽底直径、槽宽、挡边比槽底高多少


def wheel_hub():
    """轮毂：中间 3 mm D 形孔套 N20 电机轴（平边离轴心 1.0），孔只留 0.05，紧配后滴 502。打印 2 个。"""
    W = WHEEL_W
    rr, rf = HUB_ROOT / 2, HUB_ROOT / 2 + HUB_FLANGE
    e = (W - HUB_GROOVE_W) / 2                                    # 两边挡边各宽 1.7
    hub = revolve([(0.01, 0), (rf, 0), (rf, e), (rr, e), (rr, W - e), (rf, W - e), (rf, W), (0.01, W)])
    for k in range(6):                                            # 6 个减重孔
        a = math.radians(30 + 60 * k)
        hub = hub - cyl_z(3.5, -1, W + 1, 11.5 * math.cos(a), 11.5 * math.sin(a), 32)
    d = cyl_z(1.5 + 0.05, -1, W + 1, seg=48) - box(1.0 + 0.05, 5, -5, 5, -2, W + 2)   # D 形孔：Ø3.1，平边在 x = 1.05
    return hub - d


def clip_leg():
    """夹座的后撑脚：绕 M3 螺丝转，靠扭簧或橡皮筋压在屏幕背面。铰链轴心在原点，撑脚向下。"""
    leg = cyl_x(4.5, -20.5, 20.5, 0, 0, 32) + box(-20.5, 20.5, -3, 3, -80, 0)
    leg = leg + box(-20.5, 20.5, -3, 9, -80, -64)                # 末端加厚，贴硅胶垫
    leg = leg - cyl_x(hole(1.5 + FIT, 24), -25, 25, 0, 0, 24)
    for x in (-12, 12):                                          # 两个挂橡皮筋的小钩槽
        leg = leg - box(x - 2, x + 2, -4, -1, -30, -24)
    return leg


if __name__ == "__main__":
    print(f"比例 {K:.2f}：整机约 {2 * RB * K:.0f} × {2 * RB * K:.0f} × {YTOP * K:.0f} mm，壁厚 {WALL} mm")
    parts = {"lens": lens(), "screen_shroud": screen_shroud(), "shell_front": half(True), "shell_back": half(False), "top_cap": cap(), "base_plate": base_plate(), "frame": frame(), "ear": ear(), "clip_tray": clip_tray(), "clip_leg": clip_leg(), "usb_door": usb_door(), "dock_base": dock_base(), "dock_plug": dock_plug(), "dock_cap": dock_cap(), "wheel_hub": wheel_hub()}
    for n, m in parts.items():
        save(n, m)
