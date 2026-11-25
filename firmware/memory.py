"""长期记忆：按人分开存，主人能在后台查看、修改、删除，也能对它说“把这件事忘了”。

存在 firmware/memory/people.json（不进公开仓库）。每个家庭成员一条：
  {"id": "p1", "name": "小明", "call": "爸爸", "phone": "192.168.1.23",
   "faces": [[128 维人脸特征], ...], "last_seen": 时间戳, "facts": [...]}
每条记忆（fact）：
  {"id": "f12", "text": "妈妈在吃降压药", "kind": "长期" | "近期", "t": 记下的时间, "due": "2026-12-01" 或 ""}
  - 长期：反复提到的、关于这个人的事（喜好、家人、习惯），一直留着
  - 近期：一件具体的事（下周去成都、明天考试），默认 14 天后自动淡忘；有 due 的到那天会提起，过了 3 天淡忘
怎么记：一段对话结束后，把这段对话交给大模型提炼出几条“增 / 改 / 删”，见 extract()。
怎么用：每段对话开始时，把这个人的记忆整理成几行字放进系统提示词，见 context()。一个家庭的记忆量不大，不用向量库。
"""
import datetime as dt
import json
import os
import re
import threading
import time

DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memory")
RECENT_DAYS = 14          # 近期记忆的保鲜期
AFTER_DUE_DAYS = 3        # 有日期的事，过了那天几天后淡忘
MAX_FACTS = 120           # 每个人最多记这么多条，超出时先删最旧的近期记忆
OWNER = "p0"              # 默认的人：认不出是谁时，就当是主人（creator.json 里的那位）在说话

EXTRACT_PROMPT = """你是家庭陪伴机器人的记忆整理员。下面是机器人和{who}刚才的一段对话，以及机器人已经记得的关于{who}的事。
请找出值得长期记住的新信息，输出 JSON，不要输出别的：
{{"add": [{{"text": "一句话，以{who}为主语", "kind": "长期或近期", "due": "YYYY-MM-DD 或空"}}],
  "update": [{{"id": "已有记忆的 id", "text": "改正后的说法"}}],
  "forget": ["要删掉的已有记忆 id"]}}
规则：
- 只记关于人的事实：喜好、家人、健康、工作学习、计划、约定、重要日子、情绪上的大事。寒暄、闲聊内容、机器人自己说的话不记。
- “长期”是会一直成立的事；“近期”是一件具体的、会过去的事。提到了日期或“明天 / 下周”就换算成日期填进 due（今天是 {today}）。
- 和已有记忆重复的不要再加；说法变了（比如搬家、换工作）就 update；{who}说了“忘掉 / 别记 / 删了”某件事，就 forget。
- 没有值得记的就输出 {{"add": [], "update": [], "forget": []}}。

已经记得的：
{known}

刚才的对话：
{dialog}"""


def today(now=None):
    return dt.date.fromtimestamp(now or time.time())


class Memory:
    def __init__(self, path=None, creator=None):
        self.path = path or os.path.join(DIR, "people.json")
        self.lock = threading.RLock()
        self.people = {}
        try:
            with open(self.path, encoding="utf-8") as f:
                self.people = json.load(f)
        except (OSError, ValueError):
            pass
        if OWNER not in self.people:
            c = creator or {}
            self.people[OWNER] = {"id": OWNER, "name": c.get("name", "主人"), "call": c.get("call", "主人"),
                                  "phone": "", "faces": [], "last_seen": 0, "facts": []}
            self.save()

    # ---------- 存取 ----------
    def save(self):
        with self.lock:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.people, f, ensure_ascii=False, indent=1)
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.path)

    def _next_id(self, prefix):
        n = 0
        for p in self.people.values():
            for x in [p["id"]] + [f["id"] for f in p["facts"]]:
                m = re.fullmatch(prefix + r"(\d+)", x)
                if m:
                    n = max(n, int(m.group(1)))
        return f"{prefix}{n + 1}"

    def person(self, pid):
        return self.people.get(pid) or self.people[OWNER]

    def add_person(self, name, call=""):
        with self.lock:
            pid = self._next_id("p")
            self.people[pid] = {"id": pid, "name": name, "call": call or name, "phone": "", "faces": [], "last_seen": 0, "facts": []}
            self.save()
            return pid

    def edit_person(self, pid, **kw):
        with self.lock:
            p = self.people[pid]
            for k in ("name", "call", "phone"):
                if k in kw:
                    p[k] = str(kw[k]).strip()
            self.save()

    def remove_person(self, pid):
        if pid == OWNER:
            raise ValueError("主人这一条不能删，可以清空他的记忆")
        with self.lock:
            self.people.pop(pid, None)
            self.save()

    def find(self, name):
        """按名字或称呼找人。"""
        for p in self.people.values():
            if name and name in (p["name"], p["call"]):
                return p["id"]
        return None

    # ---------- 记忆条目 ----------
    def add(self, pid, text, kind="长期", due="", now=None):
        text = text.strip()
        if not text:
            return None
        with self.lock:
            p = self.person(pid)
            if any(f["text"] == text for f in p["facts"]):
                return None
            f = {"id": self._next_id("f"), "text": text, "kind": "近期" if kind == "近期" else "长期",
                 "t": now or time.time(), "due": due if re.fullmatch(r"\d{4}-\d{2}-\d{2}", due or "") else ""}
            p["facts"].append(f)
            while len(p["facts"]) > MAX_FACTS:
                old = [x for x in p["facts"] if x["kind"] == "近期"] or p["facts"]
                p["facts"].remove(min(old, key=lambda x: x["t"]))
            self.save()
            return f["id"]

    def edit(self, fid, text):
        with self.lock:
            for p in self.people.values():
                for f in p["facts"]:
                    if f["id"] == fid:
                        f["text"] = text.strip()
                        self.save()
                        return True
        return False

    def forget(self, fid):
        with self.lock:
            for p in self.people.values():
                n = len(p["facts"])
                p["facts"] = [f for f in p["facts"] if f["id"] != fid]
                if len(p["facts"]) != n:
                    self.save()
                    return True
        return False

    def forget_matching(self, pid, words):
        """语音说“把降压药那件事忘了”：删掉含有这个词的记忆，返回删了几条。"""
        words = words.strip()
        if not words:
            return 0
        with self.lock:
            p = self.person(pid)
            n = len(p["facts"])
            p["facts"] = [f for f in p["facts"] if words not in f["text"]]
            if len(p["facts"]) != n:
                self.save()
            return n - len(p["facts"])

    def prune(self, now=None):
        """近期记忆过了保鲜期就淡忘。每天跑一次就够。"""
        now = now or time.time()
        d = today(now)
        with self.lock:
            changed = False
            for p in self.people.values():
                keep = []
                for f in p["facts"]:
                    if f["kind"] == "近期":
                        if f["due"]:
                            if (d - dt.date.fromisoformat(f["due"])).days > AFTER_DUE_DAYS:
                                continue
                        elif now - f["t"] > RECENT_DAYS * 86400:
                            continue
                    keep.append(f)
                changed |= len(keep) != len(p["facts"])
                p["facts"] = keep
            if changed:
                self.save()

    def due_today(self, pid, now=None):
        """今天或明天要发生的事，主动打招呼时可以提一句。"""
        d = today(now)
        out = []
        for f in self.person(pid)["facts"]:
            if f["due"]:
                k = (dt.date.fromisoformat(f["due"]) - d).days
                if 0 <= k <= 1:
                    out.append(("今天" if k == 0 else "明天") + "：" + f["text"])
        return out

    def context(self, pid, now=None):
        """放进系统提示词的几行字。"""
        p = self.person(pid)
        lines = [f"现在和你说话的是{p['name']}（你叫TA“{p['call']}”）。" if pid != OWNER or p["name"] != "主人" else ""]
        facts = p["facts"]
        if facts:
            longf = [f["text"] for f in facts if f["kind"] == "长期"]
            recent = [f["text"] + (f"（{f['due']}）" if f["due"] else "") for f in facts if f["kind"] == "近期"]
            lines.append("你记得关于TA的这些事，自然地用上，不要一条条背出来：")
            lines += ["- " + t for t in longf[-60:]]
            if recent:
                lines.append("最近的事：")
                lines += ["- " + t for t in recent[-20:]]
        for x in self.due_today(pid, now):
            lines.append("要提醒的：" + x)
        others = [q["call"] for q in self.people.values() if q["id"] != p["id"]]
        if others:
            lines.append("家里其他人：" + "、".join(others) + "。别人的事不要随便说出去。")
        return "\n".join(x for x in lines if x)

    # ---------- 从对话里提炼 ----------
    def extract(self, ask, pid, dialog, now=None):
        """dialog：[(说话的人, 内容), ...]；ask(system, text) -> 文本，是一次不带历史的大模型调用。返回改动条数。"""
        if not dialog:
            return 0
        p = self.person(pid)
        known = "\n".join(f"{f['id']}：{f['text']}" for f in p["facts"]) or "（还没有）"
        text = "\n".join(f"{who}：{say}" for who, say in dialog)
        raw = ask("只输出 JSON。", EXTRACT_PROMPT.format(who=p["call"], today=today(now).isoformat(), known=known, dialog=text))
        m = re.search(r"\{.*\}", raw or "", re.S)
        if not m:
            return 0
        try:
            ops = json.loads(m.group(0))
        except ValueError:
            return 0
        ids = {f["id"] for f in p["facts"]}
        n = 0
        for a in ops.get("add") or []:
            if isinstance(a, dict) and self.add(pid, str(a.get("text", "")), a.get("kind", "长期"), str(a.get("due") or ""), now):
                n += 1
        for u in ops.get("update") or []:
            if isinstance(u, dict) and u.get("id") in ids and self.edit(u["id"], str(u.get("text", ""))):
                n += 1
        for fid in ops.get("forget") or []:
            if fid in ids and self.forget(fid):
                n += 1
        return n

    # ---------- 人脸 ----------
    def faces(self):
        return [(p["id"], fe) for p in self.people.values() for fe in p["faces"]]

    def add_face(self, pid, feature, keep=8):
        with self.lock:
            p = self.person(pid)
            p["faces"] = (p["faces"] + [list(map(float, feature))])[-keep:]
            self.save()

    def clear_faces(self, pid):
        with self.lock:
            self.person(pid)["faces"] = []
            self.save()

    def seen(self, pid, now=None):
        self.person(pid)["last_seen"] = now or time.time()     # 不每次都写盘，退出前和每段对话后会存

    def public(self):
        """给后台网页看：不带人脸特征，只说录了几张。"""
        return [{**{k: v for k, v in p.items() if k != "faces"}, "faces": len(p["faces"])} for p in self.people.values()]
