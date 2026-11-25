"""用户在手机后台填的设置：对话模型和密钥、语音服务、主动问候的开关和免打扰时间。

存在 firmware/settings.json（不进公开仓库，只在树莓派上，权限 600）。没有这个文件时，从原来的环境变量取默认值，
所以老的启动方式（NOMI_API_BASE 等）照样能用。网页 /setup 改了之后立刻生效，不用重启。
"""
import copy
import json
import os
import threading

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")
E = os.environ.get

# 对话模型的几个预设：用户在后台选一个，填自己的 key 就行
PRESETS = {
    "deepseek": {"provider": "openai", "base": "https://api.deepseek.com/v1", "model": "deepseek-chat"},
    "openai": {"provider": "openai", "base": "https://api.openai.com/v1", "model": ""},     # 模型名让用户自己填
    "claude": {"provider": "claude", "base": "", "model": "claude-opus-5-5"},
    "custom": {"provider": "openai", "base": "", "model": ""},                              # 其他兼容 OpenAI 格式的服务
}

DEFAULT = {
    # 对话（大模型）。provider：openai = 所有兼容 OpenAI 格式的服务（DeepSeek、GPT、通义、Kimi……）；claude = Anthropic 官方接口
    "chat": {"preset": "custom", "provider": "openai", "base": E("NOMI_API_BASE", ""), "key": E("NOMI_API_KEY", ""),
             "model": E("NOMI_CHAT_MODEL", "")},
    # 语音：DeepSeek 和 Claude 都没有语音转文字 / 文字转语音，所以单独配。留空就和对话用同一家（只对 OpenAI 格式的服务有效）
    "voice": {"base": E("NOMI_VOICE_BASE", ""), "key": E("NOMI_VOICE_KEY", ""), "asr_model": E("NOMI_ASR_MODEL", ""),
              "tts_base": E("NOMI_TTS_BASE", ""), "tts_model": E("NOMI_TTS_MODEL", ""), "tts_voice": E("NOMI_TTS_VOICE", "")},
    # 主动开口
    "proactive": {
        "on": True,              # 总开关
        "quiet": ["22:30", "07:30"],   # 免打扰：这段时间只做表情、不出声
        "away_h": 3.0,           # 离开超过几小时，再见到就算“回家了”
        "cooldown_min": 30,      # 对同一个人两次主动开口至少隔多久
        "max_per_day": 6,        # 一天最多主动开口几次
        "listen_s": 6,           # 说完之后开着耳朵等几秒，对方接话就接着聊，不接就安静收住
        "move": True,            # 迎接时转身、往前挪一点（在桌上、在充电时不动）
    },
}


class Settings:
    def __init__(self, path=PATH):
        self.path = path
        self.lock = threading.Lock()
        self.data = copy.deepcopy(DEFAULT)
        try:
            with open(path, encoding="utf-8") as f:
                saved = json.load(f)
            for k, v in saved.items():
                if isinstance(v, dict) and isinstance(self.data.get(k), dict):
                    self.data[k].update(v)
                else:
                    self.data[k] = v
        except (OSError, ValueError):
            pass

    def __getitem__(self, k):
        return self.data[k]

    def update(self, patch):
        """patch 是网页传来的部分设置。key 传空字符串表示“不改”，传 null 表示清掉。"""
        with self.lock:
            for sec, vals in patch.items():
                if sec not in self.data or not isinstance(vals, dict):
                    continue
                vals = dict(vals)
                if sec == "chat" and vals.get("preset") in PRESETS and vals.get("preset") != self.data["chat"].get("preset"):
                    for k, v in PRESETS[vals["preset"]].items():
                        vals.setdefault(k, v)
                for k in ("key",):
                    if k in vals and vals[k] == "":
                        vals.pop(k)
                    elif k in vals and vals[k] is None:
                        vals[k] = ""
                self.data[sec].update(vals)
            self.save()

    def save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=1)
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.path)

    def public(self):
        """给网页看的版本：密钥只说填没填，不回传。"""
        d = copy.deepcopy(self.data)
        for sec in ("chat", "voice"):
            d[sec]["key"] = "已填写" if d[sec].get("key") else ""
        d["presets"] = PRESETS
        return d
