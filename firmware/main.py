"""Nomi 样机主程序：sudo -E python3 main.py （灯环需要 root；-E 保留环境变量里的密钥）。

每个硬件模块都是可选的：哪个没接好，启动时会打印一行原因并跳过，其余照常工作。
"""
import re
import threading
import time
import config as C

state = {"v": 0.0, "w": 0.0, "manual_until": 0.0, "expr": "normal", "expr_until": 0.0, "desk": False, "dance_t0": 0.0}
DANCE_WORDS = re.compile(r"跳.{0,2}舞|转.?圈")        # 听到这些词直接跳，不用等大模型


def load(name, make):
    try:
        return make()
    except Exception as e:                      # 没接线、没装库、没开接口都会到这里
        print(f"[跳过] {name}: {e}")
        return None


def main():
    import drive, face, body, ir, voice, web
    d = load("底盘", drive.Drive)
    f = load("表情屏", face.Face)
    b = load("耳朵和灯环", body.Body)

    def on_tool(name, args):
        if name == "set_device":
            return "已发送" if ir.send(args.get("name", "")) else "没有学过这个遥控按键"
        if name == "move":
            a = args.get("action")
            if a == "跳舞":
                state["dance_t0"] = time.time()
                return "开始跳了"
            state["v"], state["w"] = {"前进": (150, 0), "后退": (-150, 0), "转一圈": (0, 2.2)}.get(a, (0, 0))
            state["manual_until"] = time.time() + (2.9 if a == "转一圈" else 1.2)
            return "好的"
        return "不认识的动作"

    v = voice.Voice(on_tool) if C.API_BASE else None
    if not v:
        print("[跳过] 对话: 没有设置 NOMI_API_BASE 等环境变量")
    threading.Thread(target=web.serve, args=(state,), daemon=True).start()

    talking = False
    while True:
        now = time.time()
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
                    if DANCE_WORDS.search(text):
                        state["dance_t0"] = time.time()
                        say, mood = "好呀，看我转个圈！", "happy"
                    else:
                        say, mood = v.chat(text)
                    state["expr"], state["expr_until"] = mood, time.time() + 6
                    if f:
                        f.talking = True
                    v.speak(say)
                except Exception as e:
                    print("[对话出错]", e)
                finally:
                    if f:
                        f.talking = False
            threading.Thread(target=answer, daemon=True).start()
        elif not v and touched:
            state["expr"], state["expr_until"] = "heart", now + 2      # 没配对话时，摸头就害羞

        if now > state["expr_until"]:
            state["expr"] = "normal"
        dancing = now - state["dance_t0"] < drive.DANCE_S
        if dancing:                                          # 跳舞：原地转圈，表情开心；遥控方向键会打断
            state["v"], state["w"] = 0.0, drive.dance_w(now - state["dance_t0"])
            state["expr"], state["expr_until"] = "happy", now + 1
        elif now > state["manual_until"]:
            state["v"] = state["w"] = 0.0
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
