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

# 外壳轮廓（和 3D 模型、尺寸图是同一个公式）
YC, RB, BL, BU, Y0, YCAP, YTOP = 60, 62, 56, 68, 6, 119, 128


def prof(h):
    """离地 h（已乘比例）处的外半径。"""
    y = h / K
    t = min(1.0, abs(y - YC) / (BL if y < YC else BU))
    return K * (RB * (1 - t ** 3) ** (1 / 3) if y < YC else RB * math.sqrt(max(0.0, 1 - t * t)))


# 实际零件尺寸（不缩放）
WHEEL_D, WHEEL_W = 44.0, 10.0
# 底部接口（夹座、充电座、机器人共用，买来的零件，不缩放）：
#   机器人底面：钢环 Ø27 / Ø17 × 0.8，中间一块 Ø16 × 1.6 的四环触点板（嘉立创打样，沉金）
#   座子凸台：环形钕铁硼磁铁 Ø26 / Ø18 × 3，中间插 Ø1.5 × 8 的弹簧顶针
#   四根针分在四个方向：中心 VBUS、3.4 D+、5.4 D−、7.3 GND（离中心的距离，mm）
PINS_USB = ((0.0, 0), (3.4, 90), (5.4, 180), (7.3, 270))
PINS_POWER = ((0.0, 0), (7.3, 270))       # 地面充电座只要 VBUS 和 GND
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
    inner = [(max(prof(h) - WALL, 0.5), h) for h in hs[::-1]]
    return revolve(outer + inner)


def sector(a0, a1, r0, r1, z0, z1, n=24):
    """俯视的扇环（角度从正前方 +Y 起算，向 +X 为正），拉伸成柱。"""
    pts = [(r1 * math.sin(a), r1 * math.cos(a)) for a in np.linspace(a0, a1, n)]
    pts += [(r0 * math.sin(a), r0 * math.cos(a)) for a in np.linspace(a1, a0, n)]
    return Manifold.extrude(CrossSection([ccw(pts)]), z1 - z0).translate([0, 0, z0])


def cutters():
    """外壳上所有的开口。"""
    c = []
    # 轮舱：轮子从两侧下方露出
    for s in (1, -1):
        c.append(box(min(s * (WHEEL_X - 7), s * (WHEEL_X + 9)), max(s * (WHEEL_X - 7), s * (WHEEL_X + 9)),
                     -WHEEL_D / 2 - 3, WHEEL_D / 2 + 3, -1, AXLE_Z * 2 + 3))
    # 表情窗：离地 58..96，左右各 0.8 弧度
    c.append(sector(-0.8, 0.8, 30 * K, 80 * K, 58.5 * K, 95.5 * K))
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
    seat = Manifold.cylinder(12, 8.2, 8.2, 64).translate([0, 0, d - 1.0]).rotate([-(90 - 29), 0, 0])
    c.append(seat.translate(list(o)))
    # 避障传感器（ToF）窗口另外做，见 tof_window()
    # 出音孔：背面一片 Ø3 的小孔
    for gz in np.arange(69, 101, 6.0):
        for gx in np.arange(-21, 22, 6.0):
            if (gx / 24) ** 2 + ((gz - 84) / 19) ** 2 < 1:
                c.append(cyl_y(1.5, -80 * K, -30 * K, gx * K, gz * K, 12))
    # 回充红外接收头的孔：Ø5.4，沿半径方向，VS1838B 的圆头从里面塞进来，热熔胶固定
    for s_ in (1, -1):
        a = math.pi + s_ * IR_RX_A
        c.append(cyl_y(2.7, 30 * K, 90 * K, 0, IR_RX_Z * K, 24).rotate([0, 0, -math.degrees(a)]))
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
DOOR_T = 1.5                      # 门厚


def inner_r(h):
    return prof(h) - WALL


def band(z0, z1, r_out, r_in, n=30):
    """贴着外壳内壁的一圈带子：半径从 内壁+r_out 到 内壁-r_in，高度 z0..z1（已乘比例）。"""
    hs = np.linspace(z0, z1, n)
    return revolve([(inner_r(h) + r_out, h) for h in hs] + [(max(inner_r(h) - r_in, 0.5), h) for h in hs[::-1]])


def door_rails():
    """后壳内侧的上下两道导轨，L 形：一条贴壁的托条 + 一道内唇，门的上下沿卡在里面。"""
    a0, a1 = math.pi - DOOR_HALF - 0.07, math.pi + DOOR_HALF + DOOR_OPEN + 0.07
    lo0, lo1 = (WIN_Z0 - 1.6) * K, (WIN_Z0 - 0.6) * K           # 门下沿在 WIN_Z0 - 0.6 附近
    hi0, hi1 = (WIN_Z1 + 0.6) * K, (WIN_Z1 + 1.6) * K
    dz0, dz1 = lo1 + 0.2, hi0 - 0.2                              # 门的上下沿
    rails = band(lo0 - 1.2, lo0, 0.5, DOOR_T + 1.6) + band(hi1, hi1 + 1.2, 0.5, DOOR_T + 4)     # 托条（上面那条要伸到内唇）
    # 内唇做成等半径的一圈：壳在这里很斜，跟着壳面走的唇会顶到门。唇比门的内表面再往里 0.2，压住门沿 0.6 mm
    for za, zb, href in ((lo0 - 0.6, dz0 + 0.6, dz0), (dz1 - 0.6, hi1 + 0.6, dz1 - 0.6)):
        r1 = inner_r(href) - 0.2 - DOOR_T - 0.2
        rails = rails + (cyl_z(r1, za, zb, seg=SEG) - cyl_z(r1 - 1.2, za - 1, zb + 1, seg=SEG))
    return rails ^ sector(a0, a1, 1, 200, 0, 60 * K, 48)


def usb_door():
    """滑门本体 + 从窗口露出来的拨片。门在关闭位置（居中对着正后方）。"""
    z0, z1 = (WIN_Z0 - 0.6) * K + 0.2, (WIN_Z1 + 0.6) * K - 0.2
    d = band(z0, z1, -0.2, 0.2 + DOOR_T) ^ sector(math.pi - DOOR_HALF, math.pi + DOOR_HALF, 1, 200, 0, 60 * K, 48)
    zk = (WIN_Z0 + WIN_Z1) / 2 * K
    knob = band(zk - 2.5, zk + 2.5, 1.7, 0.5) ^ sector(math.pi - 0.22 - 0.025, math.pi - 0.22 + 0.025, 1, 200, 0, 60 * K, 8)
    return d + knob


def seam_tabs(front):
    """前后壳合缝处的螺丝耳：M2 螺丝从后往前穿，四个。"""
    tabs, holes = [], []
    for zz in (30 * K, 100 * K):
        for s in (1, -1):
            r = prof(zz) - WALL
            x0, x1 = sorted((s * (r - 9), s * (r + 0.5)))
            y0, y1 = (0, 6) if front else (-6, 0)
            tabs.append(box(x0, x1, y0, y1, zz - 4, zz + 4))
            holes.append(cyl_y(1.2, -8, 8, s * (r - 5), zz, 24))
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
    pocket = place(box(-COVER_W / 2 - 0.2, COVER_W / 2 + 0.2, 0, 20, -COVER_H / 2 - 0.2, COVER_H / 2 + 0.2))
    hole = place(box(-TOF_W / 2, TOF_W / 2, -BOSS_T - 1, 1, -TOF_H / 2, TOF_H / 2))
    # 盖片外面的开口按光束张角做成喇叭口：上沿往上张 25°、左右各张 15°（大于光束的 18.5° / 13.5°），光束不会擦到眉檐
    hw, hh = COVER_W / 2 + 0.2, COVER_H / 2 + 0.2
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
    tabs, holes = seam_tabs(front)
    solid_inside = revolve([(0.01, Y0 * K), (prof(Y0 * K), Y0 * K)] + [(prof(h), h) for h in np.linspace(Y0 * K, YCAP * K, 60)] + [(0.01, YCAP * K)])
    for t in tabs:
        body = body + (t ^ solid_inside)       # 耳朵不能戳出外壳
    for h in holes:
        body = body - h
    return body


def cap():
    """顶盖：离地 119 以上，带一圈向下的止口；两条槽让耳朵的摆杆穿出来。"""
    hs = np.linspace(YCAP * K, YTOP * K - 0.01, 40)
    outer = [(prof(h), h) for h in hs] + [(0.0, YTOP * K)]
    inner = [(0.0, YTOP * K - 1.8)] + [(max(prof(h) - 1.8, 0.0), max(h - 0.9, YCAP * K)) for h in hs[::-1][3:]]
    dome = revolve(outer + inner)
    r = prof(YCAP * K) - WALL - 0.25
    lip = revolve([(r - 1.6, (YCAP - 3) * K), (r, (YCAP - 3) * K), (r, YCAP * K + 0.5), (r - 1.6, YCAP * K + 0.5)])
    part = dome + lip
    for s in (1, -1):
        x0, x1 = sorted((s * 16.5 * K, s * 23.5 * K))        # 耳朵摆杆的槽，中心在 ±20 × 比例
        part = part - box(x0, x1, -9 * K, 9 * K, (YCAP - 4) * K, (YTOP + 2) * K)
    return part


def base_plate():
    """底盘：嵌在外壳底部开口里，带四个滑垫、三个悬崖传感器窗、四个螺丝孔。
    滑垫分在左右两侧（x = ±24.5），中间留出一条空道：倒车上充电座时，滑垫从接口台两边走过去，不会撞上。"""
    z0 = Y0 * K
    r = prof(z0) - WALL - 0.4
    p = revolve([(0.01, z0), (r - 0.8, z0), (r, z0 + 0.8), (r, z0 + 2.5), (0.01, z0 + 2.5)])   # 下沿倒角 0.8，过板边更顺
    for x, y in PADS:
        p = p + cyl_z(PAD_R, 1.0, z0 + 0.1, x, y, 32)            # 滑垫底面比轮子最低点高 1 mm
    # 悬崖传感器窗：放得下 TCRT5000 本体（10.2 × 5.8），长边前后方向；后面那个往右偏 9
    for x, y in ((-11, 15), (11, 15), (9, -17)):
        p = p - box(x * K - 3.1, x * K + 3.1, y * K - 5.3, y * K + 5.3, z0 - 1, z0 + 4)
    p = p - cyl_z(13.7, z0 - 1, z0 + 0.8, seg=64)                 # 钢环槽：Ø27 × 0.8 的钢环，和底面齐平，给座子的磁铁吸
    p = p - cyl_z(8.2, z0 - 1, z0 + 1.6, seg=48)                  # 触点板槽：Ø16 × 1.6 的四环触点板，和底面齐平
    p = p - cyl_z(2.5, z0 - 1, z0 + 4, seg=24)                    # 触点板背面的 4 根线从这里穿上去
    p = p + box(-9, 9, -(r - 1), -(r - 9), z0 + 2.4, z0 + 5.5)    # 后缘垫块：USB-C 充电板粘在上面，口朝后对准窗口（往下压 0.1 和底盘连成一体）
    for a in (45, 135, 225, 315):
        rr = r - 4.5
        p = p - cyl_z(1.2, z0 - 1, z0 + 4, rr * math.cos(math.radians(a)), rr * math.sin(math.radians(a)), 24)
    return p


def frame():
    """内部骨架：一块立板（在左右方向的平面里）加三层搁板，电池、主板、舵机都放在上面。
    电机卡在立板下方的两个缺口里。这是起步版，孔位请按你买到的零件核对后再打印。"""
    hs = np.linspace(Y0 * K + 3, 112 * K, 70)
    outline = [(prof(h) - WALL - 1.0, h) for h in hs]
    pts = outline + [(-r, h) for r, h in outline[::-1]]
    plate = Manifold.extrude(CrossSection([ccw(pts)]), 3).translate([0, 0, -1.5]).rotate([90, 0, 0])   # XZ 平面的立板，厚 3
    inside = revolve([(0.01, Y0 * K + 3)] + outline + [(0.01, 112 * K)])
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
            f = f - cyl_z(1.4, 60 * K - 4, 60 * K + 1, s * 29, dy, 24)
    # 走线孔
    f = f - cyl_y(7, -5, 5, 0, 48 * K, 32) - cyl_y(7, -5, 5, 0, 80 * K, 32)
    return f


def ear():
    """耳朵：胶囊形，下面带一根摆杆，摆杆末端的孔锁在舵机摇臂上。用 TPU 软料打印。"""
    r, h = 6 * K, 14 * K
    cap_ = cyl_z(r, 0, h, seg=48) + Manifold.sphere(r, 48) + Manifold.sphere(r, 48).translate([0, 0, h])
    stem = box(-2, 2, -3.5, 3.5, -22 * K, 0)
    return (cap_ + stem - cyl_x(1.1, -4, 4, 0, -22 * K + 4, 20)).translate([0, 0, 22 * K])


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
    """在托盘 / 底板上加接口凸台：环形磁铁坑、弹针孔、凸台下面的走线腔，以及一条通到后边缘的走线槽。
    t 的上表面是 Z=0，底板厚 floor。r_edge：后边缘离中心的距离，走线槽通到这里。"""
    boss_h = Y0 * K - 0.5                                        # 凸台顶离底盘钢环 0.5 mm
    t = t + Manifold.cylinder(boss_h, 14.5, 14, 64)              # 接口凸台（在前后两个滑垫之间）
    t = t - (cyl_z(13.15, boss_h - 3.1, boss_h + 1, seg=64) - cyl_z(9.0, boss_h - 4, boss_h + 2, seg=48))   # 环形磁铁坑
    t = t - cyl_z(8.5, -(floor - 1), boss_h - 3.6, seg=48)       # 走线腔：弹针尾巴在这里焊线
    for r, a in pins:                                            # 弹针孔 Ø1.6，针头露出凸台约 1.2 mm
        t = t - cyl_z(0.8, boss_h - 3.7, boss_h + 1, r * math.cos(math.radians(a)), r * math.sin(math.radians(a)), 16)
    t = t - box(-1.5, 1.5, -(r_edge + 1), -6, -(floor - 1), 0.1)  # 走线槽，宽 3 深 2，装好后用胶带盖住
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
    t = t - cyl_x(1.7, -40, 40, -36, -10, 24)                    # 铰链轴孔，穿 M3 螺丝
    # 托盘后侧的 USB-C 小板仓：放一块带 D+/D− 的 USB-C 母座转接板（约 15 × 10），口朝后，线接电脑
    yb = -(ri + 2.5)
    t = t + box(-10, 10, yb - 13, yb + 1, -3, 8)
    t = t - box(-8.5, 8.5, yb - 11.5, yb, -1.5, 9)               # 上面敞口，放好板子后用胶带或热熔胶封
    t = t - box(-5, 5, yb - 14, yb - 11.4, 0.6, 4.6)             # 母座开口 10 × 4
    t = t - box(-1.5, 1.5, yb - 0.5, -(ri - 1), -2, 2)           # 穿过围边，接上走线槽
    return t


# ---------------- 地面充电座（能自己倒车开上来的版本） ----------------
# 坐标：接口台中心是原点，后墙在 -Y，机器人从 +Y 那边倒车进来。底板上表面 Z=0，地面 Z=-3。
DOCK_R = 84 * K                   # 底板半径
RAMP_W, RAMP_LIP = 20.0, 0.6      # 底板外圈 20 mm 宽的缓坡：边缘只有 0.6 mm 厚，坡度约 7°
DOCK_YF = -(RB * K + 8)           # 后墙正面
DOCK_WD = 22.0                    # 后墙厚度（里面放信标板、USB-C 转接板和配重）
RAIL_X = WHEEL_X + WHEEL_W / 2 + 2    # 导轨内侧：轮子外侧再留 2 mm
RAIL_H, RAIL_T = 5.0, 3.0
PLUG_R, PLUG_FL, PLUG_FT = 14.0, 15.2, 1.0    # 浮动接口台：本体半径、底部凸缘半径、凸缘厚
PLUG_FLOAT = 2.0                  # 接口台能左右（X 方向）各滑 2 mm：轮子在导轨里还有 ±2 mm 余量，靠磁铁把接口台拉到钢环正下方
PLUG_DOWN, PLUG_UP = 3.6, 6.9 + 0.3           # 接口台顶面：平时落在 3.6（弹针头 4.6，比机器人后倾时外壳最低处 4.7 还低）；被磁铁吸起最多到 7.2，底盘在 6.9 先贴上
SLEEVE_TOP = 3.6
CAP_R, CAP_T = 18.0, 0.8
PLUG_Z0 = -3 + CAP_T              # 接口台落下时底面的高度（压在底盖环上）
PLUG_H = PLUG_DOWN - PLUG_Z0
LIP_Z = PLUG_Z0 + PLUG_FT + (PLUG_UP - PLUG_DOWN) + 0.1     # 套筒内唇下沿：凸缘顶到这里就停（内唇厚约 1 mm）
BEACON_Z = IR_RX_Z * K            # 信标灯高度 = 机器人接收头高度
BEACON_SIDE = 27                  # 左右两颗信标灯斜着照的角度（度）
# 后墙下方两块挡块：机器人倒车时外壳碰到它就停，这时机身中心正好在接口台上方（前后误差 < 0.5 mm）。
# 挡块在轮轴附近的高度（离地 17–27），机身前后点头时这里几乎不移动；贴 1 mm 毛毡。
STOP_X0, STOP_X1, STOP_Z0, STOP_Z1, FELT = 17.0, 25.0, 17.0, 27.0, 1.0


def stadium(hx, hy, z0, z1):
    """俯视是跑道形（X 方向长）的柱子：半长 hx、半宽 hy。"""
    d = max(hx - hy, 0.01)
    return box(-d, d, -hy, hy, z0, z1) + cyl_z(hy, z0, z1, -d, 0, 64) + cyl_z(hy, z0, z1, d, 0, 64)


def rail(x_sign):
    """一侧导轨：靠墙一段笔直，前面一段往外张开 20°，像个漏斗，把轮子引到正中。"""
    xs = x_sign
    pts = [(xs * RAIL_X, DOCK_YF + 1), (xs * RAIL_X, 5.0), (xs * (RAIL_X + 12), 38.0),
           (xs * (RAIL_X + 12 + RAIL_T), 38.0), (xs * (RAIL_X + RAIL_T), 5.0), (xs * (RAIL_X + RAIL_T), DOCK_YF + 1)]
    m = Manifold.extrude(CrossSection([ccw(pts)]), RAIL_H + 3).translate([0, 0, -3])
    return m


def beacon_block():
    """后墙里的信标块：三颗 5 mm 红外灯。中间一颗在 8 mm 长的 Ø2.4 细孔后面，光束很窄，只照正前方一条线；
    左右两颗斜着 27° 往两边照（和中间那束有一点重叠，不留空隙）。返回 (实体, 要挖掉的孔)。"""
    y0, y1 = DOCK_YF - 16, DOCK_YF
    z = BEACON_Z
    solid = box(-17, 17, y0, y1, z - 7, z + 7)
    holes = cyl_y(1.2, DOCK_YF - 9, DOCK_YF + 1, 0, z, 24)                 # 中间：细长光阑
    holes = holes + cyl_y(2.65, y0 - 1, DOCK_YF - 8.9, 0, z, 32)            # 中间：灯座
    holes = holes + cyl_y(3.0, y0 - 1, y0 + 1.0, 0, z, 32)                  # 灯的凸缘
    for s_ in (1, -1):
        h = cyl_y(2.65, -12, 14, 0, 0, 32).rotate([0, 0, -s_ * BEACON_SIDE]).translate([s_ * 9, DOCK_YF - 7, z])
        holes = holes + h
    return solid, holes


def dock_base():
    """地面充电座：
    · 底板外圈是一圈 7° 的缓坡，边缘只有 0.6 mm 厚，轮子和滑垫都能顺着开上来；
    · 左右两条低导轨（高 5）做成漏斗，把轮子引到正中，最后左右各只留 2 mm 余量；
    · 中间是套筒，里面放浮动接口台（dock_plug，单独打印）：平时落下去，机器人倒车经过时碰不到；
      到位后磁铁把它吸起来、左右拉正，贴住底盘钢环，两根弹针接通 VBUS 和 GND；
    · 后墙下方两块挡块定住前后位置：机器人倒车碰到挡块就停，正好在接口台上方；
    · 后墙正面有三颗红外信标灯（左、中、右）和状态灯缝，背面下方是 USB-C 电源口，墙里放信标小板和配重。"""
    plate = revolve([(0.01, -3), (DOCK_R, -3), (DOCK_R, -3 + RAMP_LIP), (DOCK_R - RAMP_W, 0), (0.01, 0)])
    yf, d = DOCK_YF, DOCK_WD
    w, h = 30 * K, 85 * K
    wall = box(-w, w, yf - d, yf, -3, h) - box(-w + 2, w - 2, yf - d + 2, yf - 2, -1, h - 2)
    bs, bh = beacon_block()
    wall = wall + (bs ^ box(-w, w, yf - d, yf, -3, h))
    wall = wall - bh
    wall = wall - box(-5, 5, yf - d - 1, yf - d + 3, 1.5, 5.5)                # 背面 USB-C 开口 10 × 4
    wall = wall - box(-15 * K, 15 * K, yf - 3, yf + 1, 70 * K, 70 * K + 3)    # 正面状态灯缝
    # 挡块：面到机身中心的距离 = 外壳在这里的半径（按挡块内侧边、上沿算）+ 毛毡厚
    ys = -math.sqrt(prof(STOP_Z1) ** 2 - STOP_X0 ** 2) - FELT
    for s_ in (1, -1):
        x0, x1 = sorted((s_ * STOP_X0, s_ * STOP_X1))
        wall = wall + box(x0, x1, yf - 1, ys, -3, STOP_Z1)
    t = plate + wall + rail(1) + rail(-1)
    # 接口台套筒：俯视是跑道形，左右长（接口台能左右滑 2 mm），顶面离底板 3.6（比机器人外壳最低处还低），
    # 上口一圈内唇在前后两边压住接口台的凸缘，吸起来也拔不出去
    fx, fy = PLUG_FL + 0.3 + PLUG_FLOAT, PLUG_FL + 0.3
    t = t + stadium(fx + 1.2, fy + 1.5, -0.5, SLEEVE_TOP)
    t = t - stadium(fx, fy, PLUG_Z0, LIP_Z)                                    # 凸缘上下、左右滑的腔
    t = t - stadium(PLUG_R + 0.3 + PLUG_FLOAT, PLUG_R + 0.3, -2.5, SLEEVE_TOP + 1)   # 本体穿出内唇
    t = t - cyl_z(CAP_R + 0.2, -4, PLUG_Z0, seg=64)                              # 底面沉槽，放底盖环
    # 底面走线槽：从套筒通到后墙里，宽 3 深 1.5；进墙的地方往上打穿
    t = t - box(-1.5, 1.5, yf - 8, -14, -4, -1.5)
    t = t - box(-1.5, 1.5, yf - 8, yf - 3, -4, 0.5)
    return t


def dock_plug():
    """浮动接口台：放在充电座的套筒里，上下能滑 3.6 mm，左右能滑 2 mm。顶面一圈 Ø26 环形磁铁，中间两根弹针（VBUS、GND）。
    平时靠自重落在底盖环上（顶面离底板 3.6）；机器人停到位，磁铁隔着空气把它吸上去，贴住底盘的钢环。打印时凸缘朝下。"""
    H = PLUG_H
    p = cyl_z(PLUG_FL, 0, PLUG_FT, seg=64) + revolve([(0.01, PLUG_FT - 0.1), (PLUG_R, PLUG_FT - 0.1), (PLUG_R, H - 0.6), (PLUG_R - 0.6, H), (0.01, H)])
    p = p - (cyl_z(13.15, H - 3.1, H + 1, seg=64) - cyl_z(9.0, H - 4, H + 2, seg=48))   # 环形磁铁坑
    p = p - cyl_z(8.5, -1, H - 3.6, seg=48)                                              # 弹针尾巴焊线的腔
    for r, a in PINS_POWER:
        p = p - cyl_z(0.8, H - 3.7, H + 1, r * math.cos(math.radians(a)), r * math.sin(math.radians(a)), 16)
    return p


def dock_cap():
    """底盖环：从充电座底面卡进沉槽，托住接口台，用 502 或热熔胶粘住。中间的孔和一道缺口让弹针的线出来，接到走线槽。"""
    c = cyl_z(CAP_R, 0, CAP_T, seg=64) - cyl_z(9.0, -1, CAP_T + 1, seg=48)
    return c - box(-1.6, 1.6, -CAP_R - 1, -8, -1, CAP_T + 1)


def clip_leg():
    """夹座的后撑脚：绕 M3 螺丝转，靠扭簧或橡皮筋压在屏幕背面。铰链轴心在原点，撑脚向下。"""
    leg = cyl_x(4.5, -20.5, 20.5, 0, 0, 32) + box(-20.5, 20.5, -3, 3, -80, 0)
    leg = leg + box(-20.5, 20.5, -3, 9, -80, -64)                # 末端加厚，贴硅胶垫
    leg = leg - cyl_x(1.7, -25, 25, 0, 0, 24)
    for x in (-12, 12):                                          # 两个挂橡皮筋的小钩槽
        leg = leg - box(x - 2, x + 2, -4, -1, -30, -24)
    return leg


if __name__ == "__main__":
    print(f"比例 {K:.2f}：整机约 {2 * RB * K:.0f} × {2 * RB * K:.0f} × {YTOP * K:.0f} mm，壁厚 {WALL} mm")
    parts = {"shell_front": half(True), "shell_back": half(False), "top_cap": cap(), "base_plate": base_plate(), "frame": frame(), "ear": ear(), "clip_tray": clip_tray(), "clip_leg": clip_leg(), "usb_door": usb_door(), "dock_base": dock_base(), "dock_plug": dock_plug(), "dock_cap": dock_cap()}
    for n, m in parts.items():
        save(n, m)
