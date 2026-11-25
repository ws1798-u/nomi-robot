"""在电脑上打开后台网页看看（不接硬件，设置和记忆存在临时文件夹里，不会碰真机的数据）：

    pip install flask requests anthropic
    python3 sim_web.py          # 然后浏览器打开 http://localhost:8798/setup
"""
import os
import sys
import tempfile

import web
from brain import Brain
from greet import Greeter
from memory import OWNER, Memory
from mood import Mood
from settings import Settings
from voice import Voice

tmp = tempfile.mkdtemp()
cfg = Settings(os.path.join(tmp, "settings.json"))
mem = Memory(os.path.join(tmp, "people.json"), creator={"name": "主人", "call": "爸爸"})
mem.add(OWNER, "喜欢喝热美式")
mem.add(OWNER, "周六带妈妈去复查", "近期", "2026-12-05")
p = mem.add_person("小雨", "妈妈")
mem.add(p, "在吃降压药")
state = {"desk": False}
brain = Brain(cfg, mem, Mood(os.path.join(tmp, "mood.json")), Voice(cfg), Greeter(cfg, mem), state, lambda n, a: "ok")
print("临时数据在", tmp, "；后台：http://localhost:%d/setup" % int(sys.argv[1] if len(sys.argv) > 1 else 8798))
web.serve(state, port=int(sys.argv[1]) if len(sys.argv) > 1 else 8798, brain=brain)
