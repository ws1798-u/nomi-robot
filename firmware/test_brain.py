"""在电脑上测记忆、心情、主动问候、对话接口，不用接硬件、不花 API 额度（模型和声音都是假的）。

    pip install requests flask anthropic
    python3 test_brain.py
"""
import json
import os
import tempfile
import threading
import time
import types
from http.server import BaseHTTPRequestHandler, HTTPServer

import greet
import llm
from memory import Memory, OWNER
from mood import Mood, is_quiet
from settings import Settings

TMP = tempfile.mkdtemp()
T = lambda h, m=0, d=2: time.mktime((2026, 12, d, h, m, 0, 0, 0, -1))      # 2026-12-02 的某个钟点
ok = 0


def check(cond, what):
    global ok
    assert cond, what
    ok += 1
    print("  ✓", what)


def fresh():
    s = Settings(os.path.join(TMP, f"s{time.time_ns()}.json"))
    m = Memory(os.path.join(TMP, f"m{time.time_ns()}.json"), creator={"name": "小吴", "call": "爸爸"})
    return s, m


print("记忆")
s, m = fresh()
f1 = m.add(OWNER, "喜欢喝冰美式")
check(m.add(OWNER, "喜欢喝冰美式") is None, "重复的不再记")
m.add(OWNER, "下周三去成都出差", "近期", "2026-12-09", now=T(9))
m.add(OWNER, "明天要体检", "近期", "2026-12-03", now=T(9))
check(m.due_today(OWNER, T(9)) == ["明天：明天要体检"], "到日子的事能提前一天想起")
check("喜欢喝冰美式" in m.context(OWNER, T(9)), "记忆会写进系统提示词")
check(m.forget_matching(OWNER, "成都") == 1, "说“把成都那件事忘了”能删掉")
m.add(OWNER, "这周在装修", "近期", now=T(9))
m.prune(T(9, d=20))
check([f["text"] for f in m.person(OWNER)["facts"]] == ["喜欢喝冰美式"], "近期的事过了保鲜期自动淡忘，长期的留着")


def fake_ask(system, text):
    check("喜欢喝冰美式" in text and "今天是" in text, "整理记忆时把已有记忆和日期交给模型")
    return '好的 {"add":[{"text":"妈妈在吃降压药","kind":"长期","due":""},{"text":"周六带妈妈去复查","kind":"近期","due":"2026-12-05"}],' \
           f'"update":[{{"id":"{f1}","text":"喜欢喝热美式，冬天不喝冰的"}}],"forget":["f999"]}}'


n = m.extract(fake_ask, OWNER, [("爸爸", "我妈最近在吃降压药，周六带她去复查"), ("糯米", "好的")], now=T(10))
facts = [f["text"] for f in m.person(OWNER)["facts"]]
check(n == 3 and "妈妈在吃降压药" in facts and "喜欢喝热美式，冬天不喝冰的" in facts, "从对话里提炼：新增 2 条、改 1 条、不存在的 id 不乱删")
pid = m.add_person("小雨", "妈妈")
m.add(pid, "喜欢养花")
check("喜欢养花" not in m.context(OWNER) and "喜欢养花" in m.context(pid), "记忆按人分开，不串台")
check(all("faces" in p and isinstance(p["faces"], int) for p in m.public()), "后台只看得到录了几张脸，看不到人脸特征")

print("心情")
md = Mood(os.path.join(TMP, "mood.json"))
md.t = T(9)
md.event("touch", OWNER), md.event("talk", OWNER)
j = md.joy
md.tick(T(10))
check(abs(md.joy - j / 2) < 1, "心情一小时回落一半")
check("天没见到TA" in md.describe(OWNER, away_h=50), "好几天没见，提示词里会说很想念")
check(is_quiet(T(23), ["22:30", "07:30"]) and not is_quiet(T(12), ["22:30", "07:30"]), "免打扰时段可以跨午夜")

print("主动问候")
s, m = fresh()
g = greet.Greeter(s, m)
check(g.step(T(8), {OWNER})[0].kind == "morning", "早上第一次看到：道早安")
check(g.step(T(8, 5), {OWNER}) == [], "早安一天只说一次")
check(all(g.step(T(8 + i // 2, 30 * (i % 2)), {OWNER}) == [] for i in range(1, 9)), "一上午一直在眼前，不会没事找话")
c = g.step(T(18), {OWNER})                      # 12 点之后没再看到，18 点出现：离开了 6 小时
check(c and c[0].kind == "arrive" and abs(c[0].away_h - 6) < 0.01, "离开 6 小时再出现：迎接回家")
g2 = greet.Greeter(s, m)
g2.step(T(12), {OWNER})
check(g2.step(T(18), {OWNER}, home={OWNER: T(7)}) == [], "手机一直在家（只是在别的房间）：不算回家")
g3 = greet.Greeter(s, m)
g3.step(T(12), {OWNER})
check(g3.step(T(23, 30), {OWNER})[0].speak is False, "免打扰时段回家：只做表情不出声")
g4 = greet.Greeter(s, m)
g4.step(T(12), {OWNER})
g4.was_ignored(OWNER), g4.was_ignored(OWNER)
g4.spoken[OWNER] = T(16, 30)
check(g4.step(T(18), {OWNER}) == [], "连着被无视两次：间隔变成 4 倍（2 小时），1.5 小时前说过，这次忍住")
g4.replied(OWNER)
g4.last_seen[OWNER] = T(12)
check(g4.step(T(18), {OWNER})[0].kind == "arrive", "对方回应过一次：恢复正常")
g5 = greet.Greeter(s, m)
g5.step(T(12), {OWNER})
g5.mute(120, T(17))
check(g5.step(T(18), {OWNER}) == [], "说过“安静一会儿”：不开口")
g6 = greet.Greeter(s, m)
g6.last_seen[OWNER] = T(12)
check(g6.step(T(18), set(), home={OWNER: T(18)}, has_cam=False) == [], "没摄像头：手机刚连上 Wi-Fi，先等人进门")
check(g6.step(T(18, 2), set(), home={OWNER: T(18)}, has_cam=False)[0].kind == "arrive", "没摄像头：一分钟后打招呼")
check("出去了大约6个小时" in greet.instruction(c[0], "爸爸"), "让模型写开场白时说明离开了多久")
s2, m2 = fresh()
m2.add(OWNER, "明天要体检", "近期", "2026-12-03")
g7 = greet.Greeter(s2, m2)
c7 = g7.step(T(12), {OWNER})
check(c7 and c7[0].kind == "remind" and "体检" in c7[0].remind[0], "有明天要做的事：见到时提一句，一天一次")
check(g7.step(T(12, 30), {OWNER}) == [], "提醒过了不再重复")

print("对话接口：OpenAI 格式（DeepSeek / GPT）")
calls = []


class Stub(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        calls.append((self.headers.get("Authorization"), body))
        msgs = body["messages"]
        if self.headers.get("Authorization") != "Bearer good":
            self.send_response(401), self.end_headers()
            return
        if msgs[-1]["role"] == "user" and "tools" in body and "空调" in msgs[-1]["content"]:
            msg = {"role": "assistant", "content": None, "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "set_device", "arguments": '{"name":"空调开"}'}}]}
        else:
            msg = {"role": "assistant", "content": "开好啦\n[情绪:happy]"}
        out = json.dumps({"choices": [{"message": msg}]}).encode()
        self.send_response(200), self.send_header("Content-Type", "application/json"), self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


srv = HTTPServer(("127.0.0.1", 0), Stub)
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{srv.server_port}/v1"
oc = llm.make({"provider": "openai", "base": base, "key": "good", "model": "deepseek-chat"})
used = []
r = oc.turn("帮我开空调", "SYS", [{"type": "function", "function": {"name": "set_device", "description": "", "parameters": {}}}], lambda n, a: used.append((n, a)) or "已发送")
check(used == [("set_device", {"name": "空调开"})] and "开好啦" in r, "模型调用工具开空调，再把话说完")
check(calls[-1][1]["messages"][0] == {"role": "system", "content": "SYS"} and calls[-1][1]["model"] == "deepseek-chat", "系统提示词和模型名照传")
try:
    llm.make({"provider": "openai", "base": base, "key": "bad", "model": "x"}).once("s", "t")
    check(False, "")
except llm.LLMError as e:
    check(e.kind == "auth", "key 不对时报 auth，机器人会提醒去后台检查")

print("对话接口：Claude（假的客户端，不联网）")


class Blk(types.SimpleNamespace):
    pass


class FakeMessages:
    def __init__(self):
        self.kw = []

    def create(self, **kw):
        self.kw.append(kw)
        last = kw["messages"][-1]["content"]
        if last == "拒":
            return types.SimpleNamespace(stop_reason="refusal", content=[])
        if isinstance(last, str) and "空调" in last:
            return types.SimpleNamespace(stop_reason="tool_use", content=[Blk(type="thinking", thinking=""), Blk(type="tool_use", id="t1", name="set_device", input={"name": "空调开"})])
        return types.SimpleNamespace(stop_reason="end_turn", content=[Blk(type="text", text="开好啦")])


cc = llm.ClaudeChat("", "sk-ant-test", "")
fm = FakeMessages()
cc.client = types.SimpleNamespace(beta=types.SimpleNamespace(messages=fm))
used = []
r = cc.turn("帮我开空调", "SYS", [{"type": "function", "function": {"name": "set_device", "description": "d", "parameters": {"type": "object"}}}], lambda n, a: used.append(n) or "已发送")
k = fm.kw[0]
check(r == "开好啦" and used == ["set_device"], "Claude 调用工具后把话说完")
check(k["model"] == "claude-opus-5-5" and k["fallbacks"] == "default" and k["betas"] == ["server-side-fallback-2026-07-01"]
      and k["tools"][0]["input_schema"] == {"type": "object"}, "默认 claude-opus-5-5、开了拒答自动换模型、工具格式转成 Anthropic 的")
check(cc.messages[1]["content"][0].type == "thinking" and cc.messages[2]["content"][0]["tool_use_id"] == "t1", "思考块原样放回历史，工具结果对上 id")
try:
    cc.turn("拒", "SYS", [], lambda n, a: "")
    check(False, "")
except llm.LLMError as e:
    check(e.kind == "refusal" and cc.messages == [], "拒答：报 refusal，这段对话从头开始（历史只追加、不删改）")

print("大脑：摸头说话 → 带着记忆回答 → 对话结束整理记忆")
import brain as B


class FakeVoice:
    def __init__(self):
        self.said, self.heard = [], []

    def ready(self):
        return True

    def start(self):
        pass

    def stop(self):
        return "a.wav"

    def transcribe(self, wav):
        return self.heard.pop(0) if self.heard else ""

    def listen(self, seconds, stop_flag=None):
        return "b.wav" if self.heard else None

    def speak(self, t):
        self.said.append(t)


class FakeChat:
    def __init__(self):
        self.systems, self.reset_n = [], 0

    def reset(self):
        self.reset_n += 1

    def turn(self, text, system, tools, on_tool):
        self.systems.append(system)
        if "别主动" in text:
            on_tool("quiet", {"minutes": 60})
            return "好，我安静一会儿\n[情绪:sleep]"
        return "你好呀\n[情绪:happy]"

    def once(self, system, text):
        if "记忆整理员" in text:
            return '{"add":[{"text":"今天加班到很晚","kind":"近期"}]}'
        self.systems.append(system)
        return "爸爸你回来啦！今天累不累？\n[情绪:heart]"


s, m = fresh()
m.add(OWNER, "喜欢喝热美式")
state = {"battery": 80, "dock": "空闲", "expr_until": 0}
v = FakeVoice()
fc = FakeChat()
br = B.Brain(s, m, Mood(os.path.join(TMP, "mood2.json")), v, greet.Greeter(s, m), state, lambda n, a: "ok")
br.chat, br.chat_sig = fc, json.dumps(s["chat"], sort_keys=True)
v.heard = ["我今天加班到很晚", "嗯"]
br.touch(True, T(21))
br.touch(False, T(21))
for _ in range(50):
    if not br.busy:
        break
    time.sleep(0.02)
check(v.said == ["你好呀", "你好呀"] and state["expr"] in ("happy", "scan", "normal"), "回答后开着耳朵等接话，接着聊了第二轮；表情标签不会念出来")
check("喜欢喝热美式" in fc.systems[0] and "爸爸" in fc.systems[0], "系统提示词里有这个人的记忆")
br.end()
time.sleep(0.2)
check(any(f["text"] == "今天加班到很晚" for f in m.person(OWNER)["facts"]), "对话结束后自动整理出新记忆")
v.heard = ["你别主动说话了"]
br._converse("c.wav", OWNER, follow=False)
check(br.greeter.muted_until > time.time() + 3000, "说“别主动说话”：模型调用 quiet，主动问候暂停")
br.greeter.muted_until = 0
br.greeter.last_seen[OWNER] = time.time() - 5 * 3600
v.said.clear()
v.heard = []
br._greet(greet.Cue("arrive", OWNER, True, 5.0))
check(v.said == ["爸爸你回来啦！今天累不累？"] and "出去了5个多小时" in fc.systems[-1], "回家迎接：带着心情和记忆写一句开场白，说完没人接话就收住")
check(br.greeter.ignored.get(OWNER) == 1, "没人接话：记一次被无视，下次隔久一点")

print(f"\n全部通过：{ok} 项")
