"""手机网页：同一个 Wi-Fi 下打开 http://<树莓派地址>:8080
  /        遥控台：看画面、遥控、换表情
  /setup   后台：选对话模型、填自己的 key、语音服务、主动问候和免打扰、家庭成员（录脸、手机 IP）、查看 / 修改 / 删除记忆
"""
import os
import threading
import time
from flask import Flask, Response, request, jsonify, send_file

SETUP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "setup.html")

PAGE = """<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Nomi</title><style>
body{margin:0;font:16px system-ui;background:#eef0f3;color:#0b0c0e;text-align:center}
img{width:100%;max-width:640px;background:#000;display:block;margin:0 auto}
.pad{display:grid;grid-template-columns:repeat(3,72px);gap:8px;justify-content:center;margin:16px}
button{height:56px;border:0;border-radius:14px;background:#fff;font-size:18px;touch-action:none}
button:active{background:#0c8f79;color:#fff}.row button{padding:0 16px;margin:4px}
</style><img src=/video><div class=pad>
<i></i><button data-v=200 data-w=0>▲</button><i></i>
<button data-v=0 data-w=2>◀</button><button data-v=0 data-w=0>■</button><button data-v=0 data-w=-2>▶</button>
<i></i><button data-v=-200 data-w=0>▼</button><i></i></div>
<div class=row><button data-e=normal>平静</button><button data-e=happy>开心</button><button data-e=heart>爱心</button>
<button data-e=scan>警戒</button><button data-e=sleep>犯困</button><button data-d=1>桌面模式开/关</button><button data-dance=1>跳舞</button>
<button data-dock=1>回去充电</button></div><p id=st style="color:#555"></p><p><a href=/setup>后台设置 · 记忆</a></p>
<script>
const post=o=>fetch('/cmd',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(o)});
document.querySelectorAll('[data-v]').forEach(b=>{
  b.onpointerdown=()=>post({v:+b.dataset.v,w:+b.dataset.w});
  b.onpointerup=b.onpointerleave=()=>post({v:0,w:0});});
document.querySelectorAll('[data-e]').forEach(b=>b.onclick=()=>post({expr:b.dataset.e}));
document.querySelector('[data-d]').onclick=()=>post({desk:'toggle'});
document.querySelector('[data-dance]').onclick=()=>post({dance:1});
document.querySelector('[data-dock]').onclick=()=>post({dock:1});
const st=()=>fetch('/status').then(r=>r.json()).then(s=>{document.getElementById('st').textContent=
  `电量 ${s.battery==null?'未知':s.battery+'%'} · ${s.charging?'正在充电':'没在充电'} · 回充：${s.dock}`;}).catch(()=>{});
st();setInterval(st,2000);
</script>"""


def serve(state, port=8080, cam=None, brain=None):
    """state：main.py 里的共享字典，这里只改它，不直接碰硬件。cam：camera.Camera；brain：brain.Brain（后台设置和记忆）。"""
    app = Flask(__name__)

    @app.get("/")
    def index():
        return PAGE

    @app.get("/video")
    def video():
        def gen():
            while True:
                jpg = cam.jpeg() if cam else b""
                if jpg:
                    yield b"--f\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n"
                time.sleep(0.08)
        return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=f")

    @app.post("/cmd")
    def cmd():
        d = request.get_json(force=True)
        if "v" in d:
            state["v"], state["w"], state["manual_until"] = float(d["v"]), float(d["w"]), time.time() + 1.0
            state["dance_t0"] = 0.0                     # 方向键随时打断跳舞和自动回充
            state["cancel_dock"] = True
        if d.get("dance") and not state.get("charging"):
            state["dance_t0"] = time.time()
        if d.get("dock"):
            state["go_dock"] = True
        if "expr" in d:
            state["expr"], state["expr_until"] = d["expr"], time.time() + 4
        if d.get("desk") == "toggle":
            state["desk"] = not state["desk"]
        return jsonify(ok=True, desk=state["desk"])

    @app.get("/status")
    def status():
        return jsonify(battery=state.get("battery"), charging=state.get("charging"), dock=state.get("dock"), desk=state["desk"])

    # ---------- 后台 ----------
    @app.get("/setup")
    def setup():
        return send_file(SETUP)

    @app.get("/api/settings")
    def get_settings():
        d = brain.cfg.public()
        d["ready"] = brain.ready()
        try:
            brain.backend()
            d["chat_ok"] = True
        except Exception:
            d["chat_ok"] = False
        d["voice_ok"] = brain.voice.ready()
        d["has_cam"] = bool(brain.vision)
        return jsonify(d)

    @app.post("/api/settings")
    def set_settings():
        brain.cfg.update(request.get_json(force=True))
        return jsonify(ok=True, ready=brain.ready())

    @app.post("/api/test")
    def test_chat():
        """试一句：确认 key 和模型能用。"""
        try:
            return jsonify(ok=True, reply=brain.backend().once("你是家庭陪伴机器人，回答要很短。", "用一句话跟我打个招呼。"))
        except Exception as e:
            return jsonify(ok=False, error=str(e))

    @app.get("/api/people")
    def people():
        return jsonify(people=brain.mem.public(), mood=brain.mood.public(), muted_until=brain.greeter.muted_until)

    @app.post("/api/person")
    def person():
        d = request.get_json(force=True)
        m = brain.mem
        if d.get("op") == "add":
            return jsonify(ok=True, id=m.add_person(d.get("name", "家人"), d.get("call", "")))
        if d.get("op") == "edit":
            m.edit_person(d["id"], **{k: d[k] for k in ("name", "call", "phone") if k in d})
        elif d.get("op") == "remove":
            m.remove_person(d["id"])
        elif d.get("op") == "clear_faces":
            m.clear_faces(d["id"])
        elif d.get("op") == "face":
            if not brain.vision:
                return jsonify(ok=False, error="没有装认人模型")
            return jsonify(ok=True, n=brain.vision.enroll(d["id"]))
        return jsonify(ok=True)

    @app.post("/api/fact")
    def fact():
        d = request.get_json(force=True)
        m = brain.mem
        if d.get("op") == "add":
            m.add(d["pid"], d.get("text", ""), d.get("kind", "长期"), d.get("due", ""))
        elif d.get("op") == "edit":
            m.edit(d["id"], d.get("text", ""))
        elif d.get("op") == "forget":
            m.forget(d["id"])
        return jsonify(ok=True)

    @app.post("/api/mute")
    def mute():
        brain.greeter.mute(float(request.get_json(force=True).get("minutes", 0)))
        return jsonify(ok=True, muted_until=brain.greeter.muted_until)

    app.run(host="0.0.0.0", port=port, threaded=True)
