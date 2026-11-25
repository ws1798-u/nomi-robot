"""声音：录音、听写（语音转文字）、说话（文字转语音）。对话本身在 brain.py / llm.py。

听写和说话用 OpenAI 格式的两个接口：/audio/transcriptions、/audio/speech。DeepSeek 和 Claude 没有这两个接口，
所以语音服务在后台单独配（settings.json 的 voice）；没单独配时，借用对话服务的地址和 key（只在对话服务也是 OpenAI 格式时有用）。
说话也可以指到自己的 tts_server.py（CosyVoice 2 合成那个女孩声音）。

两种录音：
  start() / stop()  摸着头说话，松开结束
  listen(seconds)   主动问候或回答之后开着耳朵等一会儿：有人说话就录下来，没人说话就返回 None（体面散场）
"""
import array
import math
import subprocess
import tempfile
import time
import wave
import requests

RATE = 16000
CHUNK = 480                     # 30 ms 一块


class Voice:
    def __init__(self, settings):
        self.cfg = settings
        self.rec = None
        self.wav = None

    def _svc(self, tts=False):
        v, c = self.cfg["voice"], self.cfg["chat"]
        borrow = c.get("provider") == "openai"
        base = (v.get("tts_base") if tts else "") or v.get("base") or (c.get("base") if borrow else "")
        key = v.get("key") or (c.get("key") if borrow else "")
        return base.rstrip("/"), {"Authorization": f"Bearer {key}"} if key else {}

    def ready(self):
        v = self.cfg["voice"]
        return bool(self._svc()[0] and v.get("asr_model") and self._svc(True)[0])

    # ---------- 录音 ----------
    def start(self):
        self.wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
        self.rec = subprocess.Popen(["arecord", "-q", "-f", "S16_LE", "-r", str(RATE), "-c", "1", self.wav])

    def stop(self):
        if self.rec:
            self.rec.terminate()
            self.rec.wait()
            self.rec = None
        return self.wav

    def listen(self, seconds=6.0, max_s=12.0, tail=0.8, stop_flag=None):
        """先用 0.3 秒量一下环境噪声，之后音量连续几块高过噪声 3 倍就算开口，停顿 tail 秒算说完。
        seconds 内没人开口返回 None；stop_flag() 为真时（比如有人摸头了）立刻放弃。"""
        p = subprocess.Popen(["arecord", "-q", "-t", "raw", "-f", "S16_LE", "-r", str(RATE), "-c", "1"], stdout=subprocess.PIPE)
        frames, floor, loud, quiet_n, started, t0 = [], [], 0, 0, False, time.time()
        try:
            while True:
                buf = p.stdout.read(CHUNK * 2)
                if not buf or (stop_flag and stop_flag()):
                    return None
                rms = rms_of(buf)
                el = time.time() - t0
                if el < 0.3:
                    floor.append(rms)
                    continue
                thr = max(400.0, 3 * (sum(floor) / len(floor)))
                if not started:
                    frames = (frames + [buf])[-10:]              # 留 0.3 秒开口前的声音
                    loud = loud + 1 if rms > thr else 0
                    if loud >= 3:
                        started = True
                    elif el > seconds:
                        return None
                else:
                    frames.append(buf)
                    quiet_n = quiet_n + 1 if rms < thr * 0.6 else 0
                    if quiet_n * CHUNK / RATE > tail or el > max_s:
                        break
        finally:
            p.terminate()
            p.wait()
        path = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(b"".join(frames))
        return path

    # ---------- 听写和说话 ----------
    def transcribe(self, wav):
        base, h = self._svc()
        with open(wav, "rb") as f:
            r = requests.post(f"{base}/audio/transcriptions", headers=h, files={"file": f},
                              data={"model": self.cfg["voice"]["asr_model"]}, timeout=30)
        r.raise_for_status()
        return r.json().get("text", "").strip()

    def speak(self, text):
        base, h = self._svc(True)
        v = self.cfg["voice"]
        r = requests.post(f"{base}/audio/speech", headers=h, timeout=60, json={
            "model": v.get("tts_model", ""), "voice": v.get("tts_voice", ""), "input": text, "response_format": "wav"})
        r.raise_for_status()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(r.content)
        subprocess.run(["aplay", "-q", f.name])


def rms_of(buf):
    a = array.array("h", buf)
    return math.sqrt(sum(x * x for x in a) / max(1, len(a)))
