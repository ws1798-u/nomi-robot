"""红外：先用 learn 录下自家遥控器的按键，之后用 send 发出去。底层是系统自带的 ir-ctl。"""
import os
import subprocess
import config as C

DIR = os.path.join(os.path.dirname(__file__), "ir_codes")


def learn(name, seconds=5):
    """对着机器人头顶按一下遥控器。录到的原始波形存成 ir_codes/<name>.txt。"""
    os.makedirs(DIR, exist_ok=True)
    path = os.path.join(DIR, f"{name}.txt")
    try:
        subprocess.run(["ir-ctl", "-d", C.IR_RX_DEV, "-r" + path, "--one-shot"], timeout=seconds)
    except subprocess.TimeoutExpired:
        return None
    return path if os.path.exists(path) and os.path.getsize(path) else None


def send(name):
    path = os.path.join(DIR, f"{name}.txt")
    if not os.path.exists(path):
        return False
    return subprocess.run(["ir-ctl", "-d", C.IR_TX_DEV, "--send=" + path]).returncode == 0
