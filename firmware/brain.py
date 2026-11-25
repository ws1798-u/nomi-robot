"""大脑：把对话、长期记忆、心情、认人、主动问候串起来。main.py 每一帧调 touch() 和 tick()，硬件动作通过共享的 state 字典交给主循环。

一段对话（session）：同一个人、两次说话间隔不超过 2 分钟算一段。一段开始时把这个人的记忆、现在的心情写进系统提示词；
一段结束时把这段对话交给大模型提炼记忆（memory.extract），然后清空对话历史。
"""
import json
import re
import threading
import time

import config as C
import dock
import greet
from llm import LLMError, make
from memory import OWNER
from mood import is_quiet

SESSION_GAP = 120         # 两次说话隔多久算新的一段对话
MAX_TURNS = 20            # 一段对话最多这么多轮，再多就整理一次记忆、重新开始
DANCE_WORDS = re.compile(r"跳.{0,2}舞|转.?圈")        # 听到这些词直接跳，不用等大模型
DOCK_WORDS = re.compile(r"去充电|回去充电|充电去|没电了")
EMO = re.compile(r"\[情绪[:：]\s*(\w+)\]")

TOOLS = [
    {"type": "function", "function": {
        "name": "set_device", "description": "用红外控制家电。name 是之前学习遥控器时起的名字，例如 空调开、空调关、电视开关",
        "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}}},
    {"type": "function", "function": {
        "name": "move", "description": "让机器人自己动一下。主人让你跳舞、转圈圈时用 跳舞；让你去充电、说你没电了时用 去充电",
        "parameters": {"type": "object", "properties": {"action": {"type": "string", "enum": ["转一圈", "跳舞", "前进", "后退", "停", "去充电"]}}, "required": ["action"]}}},
    {"type": "function", "function": {
        "name": "remember", "description": "对方明确让你记住某件事时用（平时的对话结束后会自动整理记忆，不用每句都调）",
        "parameters": {"type": "object", "properties": {"text": {"type": "string", "description": "一句话，以对方为主语"},
                                                        "kind": {"type": "string", "enum": ["长期", "近期"]},
                                                        "due": {"type": "string", "description": "相关日期 YYYY-MM-DD，没有就空"}}, "required": ["text"]}}},
    {"type": "function", "function": {
        "name": "forget", "description": "对方让你忘掉、别记、删掉某件事时用。words 是那件事里的关键词",
        "parameters": {"type": "object", "properties": {"words": {"type": "string"}}, "required": ["words"]}}},
    {"type": "function", "function": {
        "name": "quiet", "description": "对方嫌你吵、让你安静一会儿、别主动说话时用。minutes 是多久，没说就 120",
        "parameters": {"type": "object", "properties": {"minutes": {"type": "integer"}}, "required": ["minutes"]}}},
    {"type": "function", "function": {
        "name": "learn_face", "description": "对方让你记住TA的脸、认识TA时用。name 是TA的名字，call 是你该怎么称呼TA（比如 妈妈）。调用后对方要对着你的摄像头站 4 秒",
        "parameters": {"type": "object", "properties": {"name": {"type": "string"}, "call": {"type": "string"}}, "required": ["name"]}}},
]


class Brain:
    def __init__(self, settings, memory, mood, voice, greeter, state, on_tool, face=None, vision=None, presence=None):
        self.cfg, self.mem, self.mood, self.voice, self.greeter = settings, memory, mood, voice, greeter
        self.state, self.hw_tool, self.face, self.vision, self.presence = state, on_tool, face, vision, presence
        self.lock = threading.Lock()
        self.busy = False                 # 正在想、正在说、正在等接话
        self.recording = False
        self.cancel = False               # 摸头打断“等接话”
        self.chat, self.chat_sig = None, None
        self.session = None               # {"pid", "dialog": [(谁, 说了什么)], "last", "system"}
        self.t_tick = 0.0
        self.day = None
        self.err_said = 0.0

    # ---------- 基础 ----------
    def backend(self):
        sig = json.dumps(self.cfg["chat"], sort_keys=True)
        if sig != self.chat_sig:
            self.chat_sig, self.chat = sig, None
            self.session = None
            self.chat = make(self.cfg["chat"])         # 没填好会抛 LLMError
        if self.chat is None:
            raise LLMError("auth", "对话服务没配置好")
        return self.chat

    def ready(self):
        try:
            self.backend()
        except Exception:
            return False
        return self.voice.ready()

    def who(self, now=None):
        return (self.vision and self.vision.current(now)) or OWNER

    def night(self, now):
        return is_quiet(now, self.cfg["proactive"]["quiet"])

    def system(self, pid, now, extra="", away=None):
        p = self.mem.person(pid)
        lt = time.localtime(now)
        parts = [C.PERSONA,
                 f"现在是{lt.tm_mon}月{lt.tm_mday}日 {lt.tm_hour}点{lt.tm_min:02d}分，星期{'一二三四五六日'[lt.tm_wday]}。",
                 self.mem.context(pid, now),
                 self.mood.describe(pid, away),
                 "你是机器人，有人问起就如实说。你会记住家人跟你说过的事；有人让你忘掉某件事就调用 forget，嫌你吵就调用 quiet。",
                 extra]
        if p.get("call") and pid != OWNER:
            parts.append(f"称呼对方为“{p['call']}”。")
        return "\n".join(x for x in parts if x)

    def set_expr(self, e, secs=6):
        self.state["expr"], self.state["expr_until"] = e, time.time() + secs

    def speak(self, text):
        if not text:
            return
        print("[说]", text)
        try:
            if self.face:
                self.face.talking = True
            self.voice.speak(text)
        except Exception as e:
            print("[说话出错]", e)
        finally:
            if self.face:
                self.face.talking = False

    def say(self, text):
        """不经过大模型，直接说一句（回充提示之类）。"""
        threading.Thread(target=self.speak, args=(text,), daemon=True).start()

    # ---------- 对话段 ----------
    def begin(self, pid, now, extra=""):
        s = self.session
        if s and (s["pid"] != pid or now - s["last"] > SESSION_GAP or len(s["dialog"]) >= MAX_TURNS * 2):
            self.end()
        if not self.session:
            self.backend().reset()
            self.session = {"pid": pid, "dialog": [], "last": now, "system": self.system(pid, now, extra)}
        return self.session

    def end(self):
        """这段对话结束：后台整理记忆，清空历史。"""
        s, self.session = self.session, None
        if self.chat:
            self.chat.reset()
        if s and s["dialog"]:
            pid, dialog, chat = s["pid"], s["dialog"], self.chat
            call = self.mem.person(pid)["call"]
            named = [(call if w == "人" else C.NAME, t) for w, t in dialog]

            def work():
                try:
                    n = self.mem.extract(chat.once, pid, named)
                    print(f"[记忆] 整理完 {call} 的一段对话，改动 {n} 条")
                except Exception as e:
                    print("[整理记忆出错]", e)
            threading.Thread(target=work, daemon=True).start()
        self.mem.save()
        self.mood.save()

    def answer(self, text, pid):
        """回答一句话，返回 (要说的话, 表情)。"""
        now = time.time()
        if DANCE_WORDS.search(text) and not self.state.get("charging"):
            self.state["dance_t0"] = now
            self.mood.event("dance", pid)
            return "好呀，看我转个圈！", "happy"
        if DOCK_WORDS.search(text):
            self.state["go_dock"] = True
            return "好的，我这就回去充电。", "normal"
        s = self.begin(pid, now)
        s["dialog"].append(("人", text))
        reply = self.backend().turn(text, s["system"], TOOLS, lambda n, a: self.tool(n, a, pid))
        m = EMO.search(reply)
        reply = EMO.sub("", reply).strip()
        s["dialog"].append(("我", reply))
        s["last"] = time.time()
        self.mood.event("talk", pid)
        return reply, (m.group(1) if m else "normal")

    def tool(self, name, args, pid):
        if name == "remember":
            fid = self.mem.add(pid, args.get("text", ""), args.get("kind", "长期"), args.get("due", ""))
            return "记住了" if fid else "这件事本来就记得"
        if name == "forget":
            n = self.mem.forget_matching(pid, args.get("words", ""))
            return f"删掉了 {n} 条" if n else "没有找到相关的记忆"
        if name == "quiet":
            m = int(args.get("minutes") or 120)
            self.greeter.mute(m)
            return f"接下来 {m} 分钟不主动说话"
        if name == "learn_face":
            if not self.vision:
                return "没有装认人的摄像头模型，认不了脸"
            nm = args.get("name", "").strip()
            target = self.mem.find(nm) or self.mem.find(args.get("call", "")) or self.mem.add_person(nm, args.get("call", ""))
            self.set_expr("scan", 6)
            n = self.vision.enroll(target)
            return f"记住了 {n} 张脸" if n else "没看清脸，让TA正对着你再试一次"
        return self.hw_tool(name, args)

    # ---------- 一轮说话 ----------
    def _converse(self, wav, pid, follow=True):
        """听写 → 回答 → 说出来；然后开着耳朵等接话，最多连着 3 轮。"""
        for _ in range(3):
            try:
                text = self.voice.transcribe(wav) if wav else ""
            except Exception as e:
                print("[听写出错]", e)
                return
            if not text:
                return
            print("[听到]", text)
            try:
                reply, emo = self.answer(text, pid)
            except LLMError as e:
                print("[对话出错]", e)
                reply, emo = self.error_line(e), "normal"
            self.set_expr(emo)
            self.speak(reply)
            if not follow or not self.cfg["proactive"].get("listen_s"):
                return
            self.set_expr("scan", self.cfg["proactive"]["listen_s"] + 1)
            wav = self.voice.listen(self.cfg["proactive"]["listen_s"], stop_flag=lambda: self.cancel)
            if not wav:
                self.set_expr("normal", 1)
                return

    def error_line(self, e):
        if e.kind == "refusal":
            return "这个我不太方便说呢，我们聊点别的吧。"
        if time.time() - self.err_said < 600:
            return ""
        self.err_said = time.time()
        return {"auth": "我的大脑连不上了，去后台看看对话模型的密钥吧。",
                "rate": "我的大脑今天有点累，额度好像用完了。",
                "network": "我连不上网了，等一下再聊好吗？"}.get(e.kind, "我脑子卡了一下，再说一次好吗？")

    def _run(self, fn, *a):
        def wrap():
            try:
                fn(*a)
            except Exception as e:
                print("[大脑出错]", e)
            finally:
                self.busy = False
        self.busy = True
        self.cancel = False
        threading.Thread(target=wrap, daemon=True).start()

    # ---------- 主循环接口 ----------
    def touch(self, touched, now):
        """摸头：按住说话，松开后回答。配置没填好时只害羞一下。"""
        if touched and not self.recording:
            self.mood.event("touch", self.who(now))
            if not self.ready():
                self.set_expr("heart", 2)
                return
            if self.busy:
                self.cancel = True              # 正在等接话：放弃，改成摸头说话
                time.sleep(0.05)
                if self.busy:
                    return
            self.recording = True
            self.voice.start()
            self.set_expr("scan", 60)
        elif not touched and self.recording:
            self.recording = False
            wav = self.voice.stop()
            self._run(self._converse, wav, self.who(now))

    def tick(self, now):
        if now - self.t_tick < 0.5:
            return
        self.t_tick = now
        night = self.night(now)
        self.mood.tick(now, self.state.get("battery"), night)
        if now > self.state.get("expr_until", 0):
            self.state["expr"] = self.mood.idle_expr(now, night)
        s = self.session
        if s and not self.busy and now - s["last"] > SESSION_GAP:
            self.end()
        day = time.strftime("%Y-%m-%d", time.localtime(now))
        if day != self.day:
            self.day = day
            self.mem.prune(now)
        # 主动问候
        seen = set(self.vision.people(now)) if self.vision else set()
        home = {}
        if self.presence:
            home = {p: self.presence.home_since(p) for p in self.mem.people if self.presence.home(p, now)}
        busy = self.busy or self.recording or self.state.get("dock") not in (None, dock.IDLE, dock.DOCKED)
        for cue in self.greeter.step(now, seen, home, has_cam=bool(self.vision), busy=busy):
            if cue.kind == "arrive":
                self.mood.event("arrive", cue.pid)
            if cue.speak and self.ready():
                self._run(self._greet, cue)
            else:
                self._wave(cue)

    def _wave(self, cue):
        """不出声的迎接：表情、耳朵、灯光、转向对方。"""
        self.set_expr("heart" if cue.kind == "arrive" else "happy", 4)
        if self.cfg["proactive"].get("move") and cue.kind == "arrive":
            cx = (self.vision.people().get(cue.pid, (0, 0.0, 0))[1]) if self.vision else 0.0
            self.state["greet_t0"], self.state["greet_cx"] = time.time(), cx

    def _greet(self, cue):
        now = time.time()
        self._wave(cue)
        pid = cue.pid
        call = self.mem.person(pid)["call"]
        sys_ = self.system(pid, now, away=cue.away_h if cue.kind == "arrive" else None)
        try:
            line = self.backend().once(sys_, greet.instruction(cue, call))
            m = EMO.search(line)
            line = EMO.sub("", line).strip()
            emo = m.group(1) if m else "happy"
        except Exception as e:
            print("[写开场白出错]", e)
            line, emo = greet.fallback(cue, call), "happy"
        print(f"[主动] {cue.kind} → {call}")
        self.set_expr(emo)
        self.speak(line)
        listen_s = self.cfg["proactive"].get("listen_s", 0)
        if not listen_s:
            return
        self.set_expr("scan", listen_s + 1)
        wav = self.voice.listen(listen_s, stop_flag=lambda: self.cancel)
        if not wav:
            self.greeter.was_ignored(pid)              # 没人接话就安静收住，不追问
            self.mood.event("ignored", pid)
            self.set_expr("normal", 1)
            return
        self.greeter.replied(pid)
        self.mood.event("greet_back", pid)
        if self.session and self.session["pid"] != pid:
            self.end()
        self.begin(pid, time.time(), extra=f"你刚才主动对TA说了：“{line}”，TA现在接话了。")
        self.session["dialog"].append(("我", line))
        self._converse(wav, pid)
