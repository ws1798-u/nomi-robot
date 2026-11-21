// 充电座的红外回充信标。板子：Digispark ATtiny85（Arduino IDE 装 Digistump 板卡包，选 "Digispark (Default - 16.5mhz)"）。
// 也能用 Arduino Nano / Pro Mini，把下面三个引脚换成 D2、D3、D4，PORTB 那几行换成 digitalWrite 就行（Nano 上 26 µs 的周期仍然够准）。
//
// 三颗 940 nm、5 mm 红外灯装在充电座后墙的信标块里：中间一颗在细孔后面（光束窄），左右两颗斜着往两边照。
// 每颗灯各接一个 S8050 三极管：基极经 1 kΩ 接下面的引脚，灯 + 33 Ω 电阻接 5 V，峰值约 100 mA。
//
// 一帧 = 3 ms 的 38 kHz 引导光 + 1 ms 空 + 一段编码光：0.8 ms = 左灯 L，1.3 ms = 中灯 C，1.8 ms = 右灯 R。
// 三颗灯轮流发，中间各隔 12 ms。机器人那边的解码在 firmware/beacon.py，两边的时长要一致。
// "左 / 右" 是面对充电座看：左灯（L）照向座子的左前方。

const uint8_t PIN_L = 1;   // PB1（板上的小灯也在这个脚上，发光时会跟着闪）
const uint8_t PIN_C = 0;   // PB0
const uint8_t PIN_R = 2;   // PB2

void burst(uint8_t mask, uint16_t us) {
  uint16_t n = us / 26;                // 38 kHz：一个周期约 26 µs
  noInterrupts();
  for (uint16_t i = 0; i < n; i++) {
    PORTB |= mask;
    delayMicroseconds(12);
    PORTB &= ~mask;
    delayMicroseconds(12);
  }
  interrupts();
}

void frame(uint8_t pin, uint16_t code_us) {
  uint8_t mask = 1 << pin;
  burst(mask, 3000);
  delayMicroseconds(1000);
  burst(mask, code_us);
}

void setup() {
  pinMode(PIN_L, OUTPUT);
  pinMode(PIN_C, OUTPUT);
  pinMode(PIN_R, OUTPUT);
}

void loop() {
  frame(PIN_L, 800);
  delay(12);
  frame(PIN_C, 1300);
  delay(12);
  frame(PIN_R, 1800);
  delay(12);
}
