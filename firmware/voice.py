"""对话：摸着头说话 → 语音转文字 → 大模型（可调用工具）→ 文字转语音 → 播放。

用的是 OpenAI 格式的三个接口：/audio/transcriptions、/chat/completions、/audio/speech。
国内外很多服务商都兼容这个格式，换服务商只改环境变量。
"""
import json
import re
import subprocess
import tempfile
import requests
import config as C

TOOLS = [
    {"type": "function", "function": {
        "name": "set_device", "description": "用红外控制家电。name 是之前学习遥控器时起的名字，例如 空调开、空调关、电视开关",
        "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}}},
    {"type": "function", "function": {
        "name": "move", "description": "让机器人自己动一下。主人让你跳舞、转圈圈时用 跳舞",
        "parameters": {"type": "object", "properties": {"action": {"type": "string", "enum": ["转一圈", "跳舞", "前进", "后退", "停"]}}, "required": ["action"]}}},
]


class Voice:
    def __init__(self, on_tool):
        self.on_tool = on_tool          # 回调：on_tool(name, args) -> 结果文字
        self.history = []
        self.rec = None
        self.wav = None

    def _headers(self):
        return {"Authorization": f"Bearer {C.API_KEY}"}

    # 录音：摸头开始，松开结束
    def start(self):
        self.wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
        self.rec = subprocess.Popen(["arecord", "-q", "-f", "S16_LE", "-r", "16000", "-c", "1", self.wav])

    def stop(self):
        if self.rec:
            self.rec.terminate()
            self.rec.wait()
            self.rec = None
        return self.wav

    def transcribe(self, wav):
        with open(wav, "rb") as f:
            r = requests.post(f"{C.API_BASE}/audio/transcriptions", headers=self._headers(),
                              files={"file": f}, data={"model": C.ASR_MODEL}, timeout=30)
        r.raise_for_status()
        return r.json().get("text", "").strip()

    def chat(self, text):
        """返回 (要说的话, 情绪)。模型要用工具时先执行，再让它把话说完。"""
        self.history.append({"role": "user", "content": text})
        self.history = self.history[-16:]
        for _ in range(3):
            r = requests.post(f"{C.API_BASE}/chat/completions", headers=self._headers(), timeout=60, json={
                "model": C.CHAT_MODEL, "tools": TOOLS,
                "messages": [{"role": "system", "content": C.PERSONA}] + self.history})
            r.raise_for_status()
            msg = r.json()["choices"][0]["message"]
            self.history.append(msg)
            calls = msg.get("tool_calls") or []
            if not calls:
                break
            for c in calls:
                args = json.loads(c["function"]["arguments"] or "{}")
                result = self.on_tool(c["function"]["name"], args)
                self.history.append({"role": "tool", "tool_call_id": c["id"], "content": str(result)})
        say = msg.get("content") or ""
        m = re.search(r"\[情绪:(\w+)\]", say)
        return re.sub(r"\[情绪:\w+\]", "", say).strip(), (m.group(1) if m else "normal")

    def speak(self, text):
        r = requests.post(f"{C.TTS_BASE}/audio/speech", headers=self._headers(), timeout=60, json={
            "model": C.TTS_MODEL, "voice": C.TTS_VOICE, "input": text, "response_format": "wav"})
        r.raise_for_status()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(r.content)
        subprocess.run(["aplay", "-q", f.name])
