"""Nomi 样机主程序：sudo -E python3 main.py （灯环需要 root；-E 保留环境变量里的密钥）。

每个硬件模块都是可选的：哪个没接好，启动时会打印一行原因并跳过，其余照常工作。
"""
import re
import threading
import time
import config as C
import dock

state = {"v": 0.0, "w": 0.0, "manual_until": 0.0, "expr": "normal", "expr_until": 0.0, "desk": False, "dance_t0": 0.0,
         "battery": None, "charging": False, "dock": dock.IDLE, "go_dock": False, "cancel_dock": False}
DANCE_WORDS = re.compile(r"跳.{0,2}舞|转.?圈")        # 听到这些词直接跳，不用等大模型
DOCK_WORDS = re.compile(r"去充电|回去充电|充电去|没电了")


def load(name, make):
    try:
        return make()
    except Exception as e:                      # 没接线、没装库、没开接口都会到这里
        print(f"[跳过] {name}: {e}")
        return None


def main():
    import drive, face, body, ir, voice, web, power, beacon
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

    v = voice.Voice(on_tool) if C.API_BASE else None
    if not v:
        print("[跳过] 对话: 没有设置 NOMI_API_BASE 等环境变量")
    threading.Thread(target=web.serve, args=(state,), daemon=True).start()

    def say(text):
        print("[说]", text)
        if v:
            threading.Thread(target=lambda: v.speak(text), daemon=True).start()

    talking = False
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

        # 摸头：按住说话，松开后去问大模型
        touched = bool(b and b.touch.value)
        if v and touched and not talking:
            talking = True
            v.start()
            state["expr"], state["expr_until"] = "scan", now + 60
        elif v and talking and not touched:
            talking = False
            wav = v.stop()

            def answer():
                try:
                    text = v.transcribe(wav)
                    if not text:
                        return
                    if DANCE_WORDS.search(text) and not state["charging"]:
                        state["dance_t0"] = time.time()
                        say_, mood = "好呀，看我转个圈！", "happy"
                    elif DOCK_WORDS.search(text):
                        state["go_dock"] = True
                        say_, mood = "好的，我这就回去充电。", "normal"
                    else:
                        say_, mood = v.chat(text)
                    state["expr"], state["expr_until"] = mood, time.time() + 6
                    if f:
                        f.talking = True
                    v.speak(say_)
                except Exception as e:
                    print("[对话出错]", e)
                finally:
                    if f:
                        f.talking = False
            threading.Thread(target=answer, daemon=True).start()
        elif not v and touched:
            state["expr"], state["expr_until"] = "heart", now + 2      # 没配对话时，摸头就害羞

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
        elif now > state["manual_until"]:
            state["v"] = state["w"] = 0.0
        state["dock"] = docker.state

        if now > state["expr_until"]:
            state["expr"] = "normal"
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
