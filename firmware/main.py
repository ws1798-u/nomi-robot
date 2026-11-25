"""Nomi 样机主程序：sudo -E python3 main.py （灯环需要 root；-E 保留环境变量里的密钥）。

每个硬件模块都是可选的：哪个没接好，启动时会打印一行原因并跳过，其余照常工作。
"""
import threading
import time
import config as C
import dock

state = {"v": 0.0, "w": 0.0, "manual_until": 0.0, "expr": "normal", "expr_until": 0.0, "desk": False, "dance_t0": 0.0,
         "battery": None, "charging": False, "dock": dock.IDLE, "go_dock": False, "cancel_dock": False,
         "greet_t0": 0.0, "greet_cx": 0.0}
GREET_TURN, GREET_FWD = 1.5, 0.6          # 迎接：先转向对方 1.5 秒，再往前挪 0.6 秒


def load(name, make):
    try:
        return make()
    except Exception as e:                      # 没接线、没装库、没开接口都会到这里
        print(f"[跳过] {name}: {e}")
        return None


def main():
    import drive, face, body, ir, voice, web, power, beacon, camera, vision, presence
    from settings import Settings
    from memory import Memory
    from mood import Mood
    from greet import Greeter
    from brain import Brain
    d = load("底盘", drive.Drive)
    f = load("表情屏", face.Face)
    b = load("耳朵和灯环", body.Body)
    pw = load("电量检测", power.Power)
    bc = load("回充信标接收", beacon.Beacon)
    docker = dock.Docker()

    def on_tool(name, args):
        if name == "set_device":
            return "已发送" if ir.send(args.get("name", "")) else "没有学过这个遥控按键"
        if name == "move":
            a = args.get("action")
            if a == "跳舞":
                if state["charging"]:
                    return "正在充电，充好了再跳"
                state["dance_t0"] = time.time()
                return "开始跳了"
            if a == "去充电":
                state["go_dock"] = True
                return "这就回去充电"
            state["v"], state["w"] = {"前进": (150, 0), "后退": (-150, 0), "转一圈": (0, 2.2)}.get(a, (0, 0))
            state["manual_until"] = time.time() + (2.9 if a == "转一圈" else 1.2)
            return "好的"
        return "不认识的动作"

    cfg = Settings()
    mem = Memory(creator=C.CREATOR)
    cam = camera.Camera()
    vis = load("认人", lambda: vision.Vision(cam, mem))
    pres = presence.Presence(mem)
    brain = Brain(cfg, mem, Mood(), voice.Voice(cfg), Greeter(cfg, mem), state, on_tool, face=f, vision=vis, presence=pres)
    if not brain.ready():
        print("[提示] 对话还没配置好：手机打开 http://<树莓派地址>:8080/setup 选模型、填 key")
    threading.Thread(target=web.serve, args=(state,), kwargs={"cam": cam, "brain": brain}, daemon=True).start()
    say = brain.say

    t_prev = time.time()
    t_power = 0.0
    low_since = None
    help_said = False
    retry_at = 0.0                                     # 求助过之后 10 分钟内不再自己出发
    while True:
        now = time.time()
        dt, t_prev = min(0.1, now - t_prev), now

        # 电量和充电：每秒读一次
        if pw and now - t_power > 1.0:
            t_power = now
            try:
                state["battery"], state["charging"] = pw.percent(), pw.charging()
            except Exception as e:
                print("[电量读取出错]", e)

        # 摸头说话、整理记忆、心情、主动问候都在 brain 里
        brain.touch(bool(b and b.touch.value), now)
        brain.tick(now)

        # 自动回充：电量低于 15% 持续 10 秒（不在桌面模式、没在充电），或者被叫去充电
        pct = state["battery"]
        low = pct is not None and pct < C.LOW_PCT and not state["charging"]
        low_since = (low_since or now) if low else None
        want = state["go_dock"] or (low_since and now - low_since > 10 and now > retry_at)
        state["go_dock"] = False
        if want and not docker.active and not state["charging"]:
            if state["desk"]:
                say("我现在在桌上，自己回不去充电座，把我放到地上吧。")
            elif not (bc and d):
                say("我没有装回充信标的接收头，请帮我放到充电座上。")
            else:
                docker.start()
                state["dance_t0"] = 0.0
                help_said = False
                if low:
                    brain.mood.event("low_battery")
                say("我有点累了，去充电啦。" if low else "好的，我回去充电。")
        if state["cancel_dock"]:                       # 遥控方向键随时接管
            state["cancel_dock"] = False
            docker.stop()

        dancing = now - state["dance_t0"] < drive.DANCE_S
        if docker.state != dock.IDLE:
            hl, hr = bc.heard() if bc else (set(), set())
            dv, dw = docker.step(dt, hl, hr, state["charging"])
            if docker.active:
                state["v"], state["w"] = dv, dw
                state["expr"], state["expr_until"] = "scan", now + 1
            elif docker.state == dock.DOCKED:
                state["v"] = state["w"] = 0.0
                state["expr"], state["expr_until"] = "sleep", now + 1
            elif docker.state == dock.HELP:
                state["v"] = state["w"] = 0.0
                if not help_said:
                    help_said = True
                    print("[回充失败]", docker.why)
                    say("我找不到充电座了，可以抱我回去吗？")
                    state["expr"], state["expr_until"] = "scan", now + 30
                    retry_at = now + 600
                    docker.stop()
        elif dancing:                                        # 跳舞：原地转圈，表情开心；遥控方向键会打断
            state["v"], state["w"] = 0.0, drive.dance_w(now - state["dance_t0"])
            state["expr"], state["expr_until"] = "happy", now + 1
        elif now - state["greet_t0"] < GREET_TURN + GREET_FWD and now > state["manual_until"] and not state["desk"] \
                and not state["charging"] and cfg["proactive"].get("move"):
            # 迎接：转向对方（脸在画面左边就往左转），再往前迎两步。桌面模式、充电时不动，只做表情
            if now - state["greet_t0"] < GREET_TURN:
                state["v"], state["w"] = 0.0, max(-1.5, min(1.5, -2.5 * state["greet_cx"]))
            else:
                state["v"], state["w"] = 120.0, 0.0
        elif now > state["manual_until"]:
            state["v"] = state["w"] = 0.0
        state["dock"] = docker.state
        if state["charging"] and not docker.active:
            state["v"] = max(0.0, state["v"])              # 在座子上不许倒车，只能往前开下来
            if now - state["dance_t0"] < drive.DANCE_S:
                state["dance_t0"] = 0.0
        if d:
            d.desk_mode = state["desk"]
            d.set(state["v"], state["w"])
        if f:
            f.expr = state["expr"]
            f.draw()
        if b:
            b.mood(state["expr"])
        time.sleep(0.03)


if __name__ == "__main__":
    main()
