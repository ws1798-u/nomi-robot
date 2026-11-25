"""谁在家：家庭成员的手机连上家里 Wi-Fi 就算在家。在后台给每个人填上手机的局域网 IP
（在路由器里给手机绑定固定 IP；iPhone / 安卓要把这个 Wi-Fi 的“私有地址 / 随机 MAC”关掉，IP 才不会变）。

手机锁屏后会间歇性断 Wi-Fi，所以 10 分钟内 ping 通过一次都算在家。
"""
import subprocess
import threading
import time

HOME_S = 600


class Presence:
    def __init__(self, memory, period=20):
        self.mem, self.period = memory, period
        self.last = {}            # pid -> 最近一次 ping 通的时间
        self.since = {}           # pid -> 这次在家是从什么时候开始的
        threading.Thread(target=self._run, daemon=True).start()

    def _ping(self, ip):
        try:
            return subprocess.run(["ping", "-c", "1", "-W", "1", ip], stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL, timeout=3).returncode == 0
        except Exception:
            return False

    def _run(self):
        while True:
            for p in list(self.mem.people.values()):
                ip = p.get("phone", "").strip()
                if ip and self._ping(ip):
                    now = time.time()
                    if not self.home(p["id"], now):
                        self.since[p["id"]] = now
                    self.last[p["id"]] = now
            time.sleep(self.period)

    def tracked(self, pid):
        return bool(self.mem.person(pid).get("phone"))

    def home(self, pid, now=None):
        return (now or time.time()) - self.last.get(pid, 0) < HOME_S

    def home_since(self, pid):
        return self.since.get(pid, 0)
