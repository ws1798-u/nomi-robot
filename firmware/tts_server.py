"""Nomi 的声音：用开源模型 CosyVoice 2 合成，音色和语气固定成试听时选定的那一个
（模型自带的女声参考音 + “活泼可爱”语气）。网站上机器人说的每一句话都是用同样的设置合成的。

这个服务跑在一台有显卡的电脑或云主机上（树莓派 Zero 跑不动），机器人通过局域网或公网调用它。
它对外是 OpenAI 格式的 /v1/audio/speech 接口，所以 voice.py 不用改，只要把
NOMI_TTS_BASE 指到这台机器：  export NOMI_TTS_BASE=http://<这台机器的地址>:8090/v1

准备（Python 3.10）：
    git clone --recursive https://github.com/FunAudioLLM/CosyVoice.git
    按它的 README 安装依赖，并下载模型 CosyVoice2-0.5B 到 CosyVoice/pretrained_models/CosyVoice2-0.5B
    pip install flask
运行：
    COSYVOICE_DIR=/path/to/CosyVoice python tts_server.py
"""
import io
import os
import sys

ROOT = os.environ.get("COSYVOICE_DIR", "./CosyVoice")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "third_party/Matcha-TTS"))

import torch
import torchaudio
from flask import Flask, request, Response
from cosyvoice.cli.cosyvoice import CosyVoice2

MODEL = os.environ.get("COSYVOICE_MODEL", os.path.join(ROOT, "pretrained_models/CosyVoice2-0.5B"))
# 音色：参考音决定“是谁的声音”。这里用模型仓库自带的女声样本，和网站上的一致。
# 要卖产品时，请换成你有授权的配音演员录音（3–10 秒、干净、无背景音）。
VOICE_REF = os.environ.get("NOMI_VOICE_REF", os.path.join(ROOT, "asset/zero_shot_prompt.wav"))
# 语气：三款外观可以各用一句。简约款用下面这句；可爱款可改成“用撒娇的语气说这句话”，科幻款“用冷静的语气说这句话”。
VOICE_STYLE = os.environ.get("NOMI_VOICE_STYLE", "用活泼可爱的语气说这句话")

cv = CosyVoice2(MODEL, load_jit=False, load_trt=False, fp16=False)
app = Flask(__name__)


@app.post("/v1/audio/speech")
def speech():
    text = (request.get_json(force=True).get("input") or "").strip()
    if not text:
        return {"error": "input is empty"}, 400
    parts = [j["tts_speech"] for j in cv.inference_instruct2(text, VOICE_STYLE + "<|endofprompt|>", VOICE_REF, stream=False)]
    wav = torch.cat(parts, dim=1)
    wav = wav / wav.abs().max().clamp(min=1e-6) * 0.9
    buf = io.BytesIO()
    torchaudio.save(buf, wav, cv.sample_rate, format="wav", backend="soundfile")
    return Response(buf.getvalue(), mimetype="audio/wav")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8090)))
