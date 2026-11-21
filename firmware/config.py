"""Nomi 样机的引脚和参数。接线改了就只改这一个文件。引脚号是 BCM 编号。"""
import os

# 电机驱动 DRV8833：左轮 IN1/IN2，右轮 IN3/IN4
MOTOR_L = (5, 6)
MOTOR_R = (13, 26)
MOTOR_MAX = 0.8          # 电池 7.4 V、电机额定 6 V，占空比最多给到 80%

# 悬崖传感器 TCRT5000 模块（数字输出）：前左、前右、后。看不到桌面时输出高电平
CLIFF = {"fl": 17, "fr": 27, "back": 22}

# 头顶触摸 TTP223，摸到时输出高电平
TOUCH = 23

# 表情屏 ST7789 240x320，接 SPI0（MOSI=10, SCLK=11, CE0=8）
LCD_DC, LCD_RST = 25, 24

# 耳朵舵机接 PCA9685 的 0、1 通道（I2C：SDA=2, SCL=3）
EAR_L, EAR_R = 0, 1

# 灯环 WS2812，16 颗，数据线接 GPIO12
RING_PIN, RING_N = 12, 16

# 红外：发射 GPIO4（经三极管），接收 GPIO15。需要在 /boot/firmware/config.txt 里开 overlay
IR_TX_DEV, IR_RX_DEV = "/dev/lirc0", "/dev/lirc1"   # 发射 GPIO4，接收 GPIO15；设备号用 ir-ctl -f -d 确认

# 轮子：直径 44 mm，轮距 82 mm，N20 空载 150 rpm
WHEEL_D, TRACK, RPM_MAX = 44.0, 82.0, 150.0

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
PERSONA = (
    f"你是家庭陪伴机器人{NAME}，12.8 厘米高，有轮子、有耳朵。说话亲切、简短，每次不超过两句，"
    "适合念出来，不要用表情符号和列表。需要开关家电或移动时调用工具。"
    "每次回复最后单独一行写 [情绪:xxx]，xxx 只能是 normal、happy、heart、scan、sleep 之一。"
)
