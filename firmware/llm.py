"""对话大模型：用户在后台选 DeepSeek / GPT / Claude（或其他兼容 OpenAI 格式的服务），填自己的 key。

两种接口：
  OpenAIChat  POST {base}/chat/completions，DeepSeek、GPT、通义、Kimi 等都兼容这个格式
  ClaudeChat  Anthropic 官方 Python SDK（pip install anthropic）

两个都提供：
  turn(text, system, tools, on_tool) -> 回复文字   一段对话里的一轮，自己保存历史，需要时先调用工具
  once(system, text) -> 文字                         不带历史的一次调用（整理记忆、写主动问候的开场白）
  reset()                                            一段对话结束，清空历史
历史只往后追加、不删改：一段对话结束（2 分钟没人说话或换了人）就整段清掉，下一段从头开始，记忆靠 memory.py 带过去。

工具（tools）统一用 OpenAI 的写法定义：{"type": "function", "function": {name, description, parameters}}，
ClaudeChat 内部转换成 Anthropic 的格式。
"""
import json
import requests


class LLMError(Exception):
    """kind：auth 密钥不对、rate 额度 / 频率超了、network 连不上、refusal 模型拒答、other"""
    def __init__(self, kind, msg):
        super().__init__(msg)
        self.kind = kind


class OpenAIChat:
    def __init__(self, base, key, model):
        if not (base and key and model):
            raise LLMError("auth", "对话服务的地址、密钥、模型名没填全")
        self.base, self.key, self.model = base.rstrip("/"), key, model
        self.history = []

    def reset(self):
        self.history = []

    def _post(self, body):
        try:
            r = requests.post(f"{self.base}/chat/completions", headers={"Authorization": f"Bearer {self.key}"},
                              json={"model": self.model, **body}, timeout=60)
        except requests.RequestException as e:
            raise LLMError("network", f"连不上对话服务：{e}")
        if r.status_code in (401, 403):
            raise LLMError("auth", "对话服务的密钥不对或没权限")
        if r.status_code in (402, 429):
            raise LLMError("rate", "对话服务额度用完了或请求太频繁")
        if r.status_code >= 400:
            raise LLMError("other", f"对话服务报错 {r.status_code}：{r.text[:200]}")
        return r.json()["choices"][0]["message"]

    def turn(self, text, system, tools, on_tool):
        self.history.append({"role": "user", "content": text})
        msg = {}
        for _ in range(4):
            msg = self._post({"messages": [{"role": "system", "content": system}] + self.history, **({"tools": tools} if tools else {})})
            msg = {k: v for k, v in msg.items() if v is not None}
            self.history.append(msg)
            calls = msg.get("tool_calls") or []
            if not calls:
                break
            for c in calls:
                try:
                    args = json.loads(c["function"].get("arguments") or "{}")
                except ValueError:
                    args = {}
                self.history.append({"role": "tool", "tool_call_id": c["id"], "content": str(on_tool(c["function"]["name"], args))})
        return msg.get("content") or ""

    def once(self, system, text):
        return self._post({"messages": [{"role": "system", "content": system}, {"role": "user", "content": text}]}).get("content") or ""


class ClaudeChat:
    FALLBACK_BETA = "server-side-fallback-2026-07-01"

    def __init__(self, base, key, model):
        import anthropic
        if not key:
            raise LLMError("auth", "Claude 的 API key 没填")
        self.anthropic = anthropic
        self.client = anthropic.Anthropic(api_key=key, **({"base_url": base} if base else {}))
        self.model = model or "claude-opus-5-5"
        self.messages = []

    def reset(self):
        self.messages = []

    @staticmethod
    def _tools(tools):
        return [{"name": t["function"]["name"], "description": t["function"]["description"],
                 "input_schema": t["function"]["parameters"]} for t in tools or []]

    def _create(self, **kw):
        a = self.anthropic
        try:
            # 对话要快：effort 用 low。模型因安全原因拒答时，服务端按类别自动换一个模型重答（fallbacks="default"）
            return self.client.beta.messages.create(
                model=self.model, max_tokens=16000, output_config={"effort": "low"},
                betas=[self.FALLBACK_BETA], fallbacks="default", **kw)
        except a.AuthenticationError:
            raise LLMError("auth", "Claude 的 API key 不对")
        except a.PermissionDeniedError:
            raise LLMError("auth", "这个 Claude key 没有权限用这个模型")
        except a.NotFoundError:
            raise LLMError("other", f"没有这个模型：{self.model}")
        except a.RateLimitError:
            raise LLMError("rate", "Claude 请求太频繁或额度用完了")
        except a.APIConnectionError as e:
            raise LLMError("network", f"连不上 Claude：{e}")
        except a.APIStatusError as e:
            raise LLMError("other", f"Claude 报错 {e.status_code}：{e.message}")

    @staticmethod
    def _text(resp):
        return "".join(b.text for b in resp.content if b.type == "text")

    def turn(self, text, system, tools, on_tool):
        self.messages.append({"role": "user", "content": text})
        for _ in range(6):
            resp = self._create(system=system, tools=self._tools(tools), messages=self.messages)
            if resp.stop_reason == "refusal":
                self.reset()                    # 历史只能往后加，拒答这一轮没法接上，这段对话就此重新开始
                raise LLMError("refusal", "模型拒绝回答")
            self.messages.append({"role": "assistant", "content": resp.content})   # 原样放回，思考块也要保留
            if resp.stop_reason == "pause_turn":
                continue
            calls = [b for b in resp.content if b.type == "tool_use"]
            if not calls:
                return self._text(resp)
            results = []
            for b in calls:
                try:
                    out, err = str(on_tool(b.name, dict(b.input or {}))), False
                except Exception as e:
                    out, err = f"出错了：{e}", True
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": out, **({"is_error": True} if err else {})})
            self.messages.append({"role": "user", "content": results})
        return self._text(resp)

    def once(self, system, text):
        resp = self._create(system=system, messages=[{"role": "user", "content": text}])
        if resp.stop_reason == "refusal":
            raise LLMError("refusal", "模型拒绝回答")
        return self._text(resp)


def make(chat_cfg):
    """按后台设置建一个对话后端。没填好时抛 LLMError。"""
    p = chat_cfg.get("provider", "openai")
    if p == "claude":
        return ClaudeChat(chat_cfg.get("base", ""), chat_cfg.get("key", ""), chat_cfg.get("model", ""))
    return OpenAIChat(chat_cfg.get("base", ""), chat_cfg.get("key", ""), chat_cfg.get("model", ""))
