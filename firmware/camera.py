"""摄像头：一个线程一直拍，最新一帧同时给网页（JPEG）和认人（数组）用。没装摄像头时 ok 为 False，其余照常。"""
import io
import threading
import time


class Camera:
    def __init__(self, size=(640, 480), fps=12):
        self.lock = threading.Lock()
        self.jpg, self.arr, self.t = b"", None, 0.0
        self.ok = False
        try:
            from picamera2 import Picamera2
            self.cam = Picamera2()
            # RGB888 在内存里是 B、G、R 顺序，正好是 OpenCV 要的格式
            self.cam.configure(self.cam.create_video_configuration(main={"size": size, "format": "RGB888"}))
            self.cam.start()
            self.ok = True
        except Exception as e:                       # 没接摄像头、没装 picamera2
            print("[跳过] 摄像头:", e)
            return
        self.dt = 1.0 / fps
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        from PIL import Image
        while True:
            try:
                a = self.cam.capture_array()
                buf = io.BytesIO()
                Image.fromarray(a[:, :, ::-1]).save(buf, format="JPEG", quality=75)
                with self.lock:
                    self.arr, self.jpg, self.t = a, buf.getvalue(), time.time()
            except Exception as e:
                print("[摄像头出错]", e)
                time.sleep(1)
            time.sleep(self.dt)

    def frame(self):
        """(BGR 数组, 拍摄时间)；没有画面时数组是 None。"""
        with self.lock:
            return self.arr, self.t

    def jpeg(self):
        with self.lock:
            return self.jpg
