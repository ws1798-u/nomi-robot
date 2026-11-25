"""认人：本地人脸检测 + 识别，画面不出机器。用 OpenCV 自带的 YuNet（找脸）和 SFace（认脸），树莓派 Zero 2 W 上约每秒 2 次。

需要两个模型文件，放在 firmware/models/ 里（第一次在树莓派上下载一次）：
  face_detection_yunet_2023mar.onnx    https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet
  face_recognition_sface_2021dec.onnx  https://github.com/opencv/opencv_zoo/tree/main/models/face_recognition_sface
没有模型或没装 opencv 时，这个模块跳过，主动问候改用手机连 Wi-Fi 判断谁回家了（presence.py）。

对外提供：
  people()  最近 3 秒内看到的人 {pid: (时间, 脸在画面里的横向位置 -1..1, 脸的大小 0..1)}，不认识的人 pid 是 "?"
  current() 现在正对着它的人（脸最大的那个），没有就是 None
  enroll(pid) 接下来几秒把看到的脸记到这个人名下
"""
import os
import threading
import time

DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
DET = os.path.join(DIR, "face_detection_yunet_2023mar.onnx")
REC = os.path.join(DIR, "face_recognition_sface_2021dec.onnx")
MATCH = 0.40          # 余弦相似度高于这个算同一个人（SFace 官方建议 0.363，稍微严一点，宁可认不出也不认错）
SEEN_S = 3.0


class Vision:
    def __init__(self, cam, memory, period=0.4):
        import cv2
        import numpy as np
        if not cam.ok:
            raise RuntimeError("没有摄像头")
        for p in (DET, REC):
            if not os.path.exists(p):
                raise RuntimeError(f"缺模型文件 {os.path.basename(p)}，见 vision.py 开头的说明")
        self.cv2, self.np = cv2, np
        self.cam, self.mem, self.period = cam, memory, period
        self.det = cv2.FaceDetectorYN.create(DET, "", (320, 240), 0.8, 0.3, 50)
        self.rec = cv2.FaceRecognizerSF.create(REC, "")
        self.lock = threading.Lock()
        self.seen = {}
        self.enrolling = None            # (pid, 截止时间, 已收几张)
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        cv2, np = self.cv2, self.np
        last_t = 0.0
        while True:
            time.sleep(self.period)
            a, t = self.cam.frame()
            if a is None or t == last_t:
                continue
            last_t = t
            try:
                h, w = a.shape[:2]
                small = cv2.resize(a, (320, 240))
                _, faces = self.det.detect(small)
                if faces is None:
                    continue
                known = self.mem.faces()
                for i, f in enumerate(sorted(faces, key=lambda f: -f[2] * f[3])[:3]):   # 最多看最大的 3 张脸
                    full = f.copy()
                    full[:14] *= np.array([w / 320, h / 240] * 7, dtype=full.dtype)
                    feat = self.rec.feature(self.rec.alignCrop(a, full)).flatten()
                    pid, best = "?", MATCH
                    for kp, kf in known:
                        s = float(np.dot(feat, kf) / (np.linalg.norm(feat) * np.linalg.norm(kf) + 1e-9))
                        if s > best:
                            pid, best = kp, s
                    cx = (f[0] + f[2] / 2) / 160 - 1
                    size = f[3] / 240
                    with self.lock:
                        e = self.enrolling
                        if e and t < e[1] and i == 0:                 # 录脸时只收最大的那张
                            self.mem.add_face(e[0], feat)
                            self.enrolling = (e[0], e[1], e[2] + 1)
                            pid = e[0]
                        if pid != "?":
                            self.mem.seen(pid, t)
                        old = self.seen.get(pid)
                        if old is None or old[0] < t or size > old[2]:
                            self.seen[pid] = (t, cx, size)
            except Exception as e:
                print("[认人出错]", e)

    def people(self, now=None):
        now = now or time.time()
        with self.lock:
            return {k: v for k, v in self.seen.items() if now - v[0] < SEEN_S}

    def current(self, now=None):
        ps = {k: v for k, v in self.people(now).items() if k != "?"}
        return max(ps, key=lambda k: ps[k][2]) if ps else None

    def enroll(self, pid, seconds=4.0):
        """对着镜头站几秒。返回收到了几张（最多 8 张，旧的会被挤掉）。"""
        with self.lock:
            self.enrolling = (pid, time.time() + seconds, 0)
        time.sleep(seconds + self.period)
        with self.lock:
            n = self.enrolling[2]
            self.enrolling = None
        return n
