"""手机网页遥控台：同一个 Wi-Fi 下打开 http://<树莓派地址>:8080 ，看画面、遥控、换表情。"""
import io
import threading
import time
from flask import Flask, Response, request, jsonify

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
<button data-e=scan>警戒</button><button data-e=sleep>犯困</button><button data-d=1>桌面模式开/关</button></div>
<script>
const post=o=>fetch('/cmd',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(o)});
document.querySelectorAll('[data-v]').forEach(b=>{
  b.onpointerdown=()=>post({v:+b.dataset.v,w:+b.dataset.w});
  b.onpointerup=b.onpointerleave=()=>post({v:0,w:0});});
document.querySelectorAll('[data-e]').forEach(b=>b.onclick=()=>post({expr:b.dataset.e}));
document.querySelector('[data-d]').onclick=()=>post({desk:'toggle'});
</script>"""


def serve(state, port=8080):
    """state：main.py 里的共享字典，这里只改它，不直接碰硬件。"""
    app = Flask(__name__)
    lock = threading.Lock()
    frame = {"jpg": b""}

    def camera():
        try:
            from picamera2 import Picamera2
        except ImportError:
            return                                  # 没装摄像头也能遥控
        cam = Picamera2()
        cam.configure(cam.create_video_configuration(main={"size": (640, 480)}))
        cam.start()
        while True:
            buf = io.BytesIO()
            cam.capture_file(buf, format="jpeg")
            with lock:
                frame["jpg"] = buf.getvalue()
            time.sleep(0.08)

    threading.Thread(target=camera, daemon=True).start()

    @app.get("/")
    def index():
        return PAGE

    @app.get("/video")
    def video():
        def gen():
            while True:
                with lock:
                    jpg = frame["jpg"]
                if jpg:
                    yield b"--f\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n"
                time.sleep(0.08)
        return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=f")

    @app.post("/cmd")
    def cmd():
        d = request.get_json(force=True)
        if "v" in d:
            state["v"], state["w"], state["manual_until"] = float(d["v"]), float(d["w"]), time.time() + 1.0
        if "expr" in d:
            state["expr"], state["expr_until"] = d["expr"], time.time() + 4
        if d.get("desk") == "toggle":
            state["desk"] = not state["desk"]
        return jsonify(ok=True, desk=state["desk"])

    app.run(host="0.0.0.0", port=port, threaded=True)
