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
    # 避障传感器（ToF）窗口另外做，见 tof_window()
    # 出音孔：背面一片 Ø3 的小孔
    for gz in np.arange(69, 101, 6.0):
        for gx in np.arange(-21, 22, 6.0):
            if (gx / 24) ** 2 + ((gz - 84) / 19) ** 2 < 1:
                c.append(cyl_y(1.5, -80 * K, -30 * K, gx * K, gz * K, 12))
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
    """底盘：嵌在外壳底部开口里，带两个滑垫、三个悬崖传感器窗、四个螺丝孔。"""
    z0 = Y0 * K
    r = prof(z0) - WALL - 0.4
    p = cyl_z(r, z0, z0 + 2.5, seg=SEG)
    for y in (20 * K * 0.8, -20 * K * 0.8):
        p = p + cyl_z(4, 1.0, z0 + 0.1, 0, y, 32)            # 滑垫底面比轮子最低点高 1 mm
    # 悬崖传感器窗：放得下 TCRT5000 本体（10.2 × 5.8），长边前后方向；后面那个往右偏 9，避开后滑垫
    for x, y in ((-11, 15), (11, 15), (9, -17)):
        p = p - box(x * K - 3.1, x * K + 3.1, y * K - 5.3, y * K + 5.3, z0 - 1, z0 + 4)
    p = p - cyl_z(13.7, z0 - 1, z0 + 0.8, seg=64)                 # 钢环槽：Ø27 × 0.8 的钢环，和底面齐平，给座子的磁铁吸
    p = p - cyl_z(8.2, z0 - 1, z0 + 1.6, seg=48)                  # 触点板槽：Ø16 × 1.6 的四环触点板，和底面齐平
    p = p - cyl_z(2.5, z0 - 1, z0 + 4, seg=24)                    # 触点板背面的 4 根线从这里穿上去
    p = p + box(-9, 9, -(r - 1), -(r - 9), z0 + 2.5, z0 + 5.5)    # 后缘垫块：USB-C 充电板粘在上面，口朝后对准窗口
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


def dock_base():
    """地面充电座（样机版）：底板 + 和夹座一样的接口凸台（只装 VBUS、GND 两根针）+ 后墙。
    后墙是空心的，背面下方开 USB-C 口，里面放转接板；正面开一条状态灯缝。
    样机先靠手把机器人放上去；量产版的接口台是浮动的，机器人能自己倒车开上来，见制造页。"""
    rp = 84 * K
    t = Manifold.cylinder(3, rp, rp - 1.5, SEG).translate([0, 0, -3])           # 底板，边上倒个斜角
    yf = -(RB * K + 8)                                                          # 后墙正面
    t = iface(t, -yf, PINS_POWER)
    w, h, d = 30 * K, 85 * K, 14
    wall = box(-w, w, yf - d, yf, -3, h) - box(-w + 2, w - 2, yf - d + 2, yf - 2, -1, h - 2)
    wall = wall - box(-5, 5, yf - d - 1, yf - d + 3, 1.5, 5.5)                 # 背面 USB-C 开口 10 × 4
    wall = wall - box(-15 * K, 15 * K, yf - 3, yf + 1, 70 * K, 70 * K + 3)      # 正面状态灯缝
    t = (t + wall) ^ cyl_z(rp, -4, h + 1, seg=SEG)
    return t - box(-1.5, 1.5, yf - 2.5, yf + 0.5, -2, 0.1)                     # 走线槽通进墙里


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
    parts = {"shell_front": half(True), "shell_back": half(False), "top_cap": cap(), "base_plate": base_plate(), "frame": frame(), "ear": ear(), "clip_tray": clip_tray(), "clip_leg": clip_leg(), "usb_door": usb_door(), "dock_base": dock_base()}
    for n, m in parts.items():
        save(n, m)
