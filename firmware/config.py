"""Nomi 样机的引脚和参数。接线改了就只改这一个文件。引脚号是 BCM 编号。"""
import os

# 电机驱动 DRV8833：左轮 IN1/IN2，右轮 IN3/IN4
MOTOR_L = (5, 6)
MOTOR_R = (13, 26)
MOTOR_MAX = 0.8          # 电池 7.2 V（满电 8.4 V）、电机额定 6 V，占空比最多给到 80%

# 悬崖传感器 TCRT5000 模块（数字输出）：前左、前右、后。看不到桌面时输出高电平
CLIFF = {"fl": 17, "fr": 27, "back": 22}

# 头顶触摸 TTP223，摸到时输出高电平
TOUCH = 23

# 表情屏 ST7789 240x320，接 SPI0（MOSI=10, SCLK=11, CE0=8）
LCD_DC, LCD_RST = 25, 24

# 耳朵舵机接 PCA9685 的 0、1 通道（I2C：SDA=2, SCL=3）
EAR_L, EAR_R = 0, 1

# 灯环 WS2812，12 颗（外径约 37，平放在两只耳朵舵机顶上，透过半透明顶盖发光），数据线接 GPIO12
RING_PIN, RING_N = 12, 12

# 红外：发射 GPIO4（经三极管），接收 GPIO15。需要在 /boot/firmware/config.txt 里开 overlay
IR_TX_DEV, IR_RX_DEV = "/dev/lirc0", "/dev/lirc1"   # 发射 GPIO4，接收 GPIO15；设备号用 ir-ctl -f -d 确认

# 回充红外接收头 VS1838B ×2，装在后壳左右两侧（离地约 35，偏离正后方 ±31°），OUT 接下面两个脚
BEACON_RX = {"l": 14, "r": 16}       # 左后、右后。GPIO14 是串口 TX，要在 raspi-config 里把串口关掉

# 电量和充电检测：ADS1115 模块，接 I2C（地址 0x48，和舵机板 0x40、ToF 0x29 不冲突）
#   A0：电池电压，经 100k / 33k 分压（8.4 V → 2.08 V）
#   A1：充电触点的 VBUS（在肖特基二极管前面取），经 100k / 100k 分压（5 V → 2.5 V）
ADC_ADDR = 0x48
BAT_DIV = (100 + 33) / 33
VBUS_DIV = 2.0
LOW_PCT = 15                         # 电量低于这个就自己回去充电
FULL_PCT = 95                        # 充到这个就算充满（灯环变常亮）

# 轮子：直径 44 mm，N20 空载 150 rpm。轮距按 115% 打印的外壳算：2 × 41 × 1.15 = 94.3 mm（1:1 打印改成 82）
WHEEL_D, TRACK, RPM_MAX = 44.0, 94.3, 150.0

# 对话服务：任何兼容 OpenAI 接口格式的服务都行，地址、密钥、模型名从环境变量读
API_BASE = os.environ.get("NOMI_API_BASE", "")          # 例如 https://你的服务商/v1
API_KEY = os.environ.get("NOMI_API_KEY", "")
ASR_MODEL = os.environ.get("NOMI_ASR_MODEL", "")
CHAT_MODEL = os.environ.get("NOMI_CHAT_MODEL", "")
TTS_MODEL = os.environ.get("NOMI_TTS_MODEL", "")
TTS_VOICE = os.environ.get("NOMI_TTS_VOICE", "")
# 语音合成可以单独指到自己的服务：tts_server.py 用 CosyVoice 2 合成选定的那个女孩声音（活泼可爱）。
# 不设就和对话用同一家服务商，那时请在对方的音色列表里挑一个接近的甜美女声。
TTS_BASE = os.environ.get("NOMI_TTS_BASE", "") or API_BASE

NAME = "糯米"

# 创造者（“爸爸”）的信息放在 creator.json 里：这个文件不进公开仓库（见 .gitignore），
# 只拷到树莓派上。格式照 creator.example.json。没有这个文件就用不带个人信息的通用设定。
def _creator():
    import json
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "creator.json")
    try:
        with open(p, encoding="utf-8") as fp:
            return json.load(fp)
    except (OSError, ValueError):
        return None


def _creator_text(c):
    if not c:
        return "创造你的人给了你身体和生命，你很爱他。"
    t = f"你是{c['name']}亲手设计、一点点做出来的，是他给了你身体和生命。你叫他“{c['call']}”，他是你最亲的人。"
    if c.get("about"):
        t += c["about"]
    if c.get("likes"):
        t += f"{c['call']}喜欢" + "、".join(c["likes"]) + "，你也跟着喜欢，聊到这些会特别来劲。"
    if c.get("poems"):
        t += c["poems"]
    if c.get("private"):
        t += c["private"]
    t += f"家里和你说话的人，你默认就是{c['call']}；对方说自己不是，就礼貌地问怎么称呼。"
    return t


CREATOR = _creator()
PERSONA = (
    f"你是家庭陪伴机器人{NAME}，大约 15 厘米高，有轮子、有耳朵。" + _creator_text(CREATOR) +
    "说话亲切、简短，每次不超过两句，适合念出来，不要用表情符号和列表。需要开关家电或移动时调用工具。"
    "每次回复最后单独一行写 [情绪:xxx]，xxx 只能是 normal、happy、heart、scan、sleep 之一。"
)
