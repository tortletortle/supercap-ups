# BQ76905 四串单体欠压监测接口设计（候选，未落图）

状态：器件候选和引脚接口已收敛到可画图的程度；**尚未完成原理图、固件配置和安全验证**。本文按 TI BQ76905 数据手册 SLUSE97 的 4S 输入表执行，不能把 VC 引脚按直觉顺序直接接成 VC0–VC4。

数据表：https://www.ti.com/lit/ds/symlink/bq76905.pdf  
技术参考手册：https://www.ti.com/lit/ug/sluuci8a/sluuci8a.pdf

## 1. 4S cell-tap 映射（按 TI Table 7-1）

器件是 20-pin RGR QFN，4S 必须使用以下四组实际电芯输入：

| 超级电容单体 | BQ76905 差分测量端 | IC 引脚 |
|---|---|---|
| CELL1（最底端） | VC1 − VC0 | VC1 pin 4、VC0 pin 5 |
| CELL2 | VC2 − VC1 | VC2 pin 3、VC1 pin 4 |
| CELL3 | VC4B − VC3A | VC4B pin 20、VC3A pin 1 |
| CELL4（最顶端） | VC5 − VC4A | VC5 pin 18、VC4A pin 19 |

4S 未用输入必须在 PCB 上短接，不能悬空：

- VC4A ↔ VC4B
- VC3A ↔ VC3B
- VC3B ↔ VC2

因此抽头节点等效为：

- PACK− / CELL1− → VC0
- CELL1+/CELL2− → VC1
- CELL2+/CELL3− → VC2、VC3B、VC3A
- CELL3+/CELL4− → VC4B、VC4A
- CELL4+ / PACK+ → VC5

实际连接以 TI 数据手册 Table 7-1 的 4S 行和 Figure 7-5 为准。数据存储器配置必须把实际使用的四节电芯启用、未使用电芯通道禁用；仅做铜箔短接但不配置 cell count 不构成有效保护。

## 2. 20-pin 引脚和网络建议

| Pin | 名称 | 建议网络/处理 | 备注 |
|---:|---|---|---|
| 1 | VC3A | CELL2+/CELL3− tap，经 cell-input RC | 与 VC3B、VC2 按 4S 表短接 |
| 2 | VC3B | CELL2+/CELL3− tap，经 cell-input RC | 与 VC3A、VC2 按 4S 表短接 |
| 3 | VC2 | CELL2+/CELL3− tap，经 cell-input RC | 与 VC3B、VC3A 按 4S 表短接 |
| 4 | VC1 | CELL1+/CELL2− tap，经 cell-input RC | 连接 CELL1、CELL2 相邻节点 |
| 5 | VC0 | PACK− / VSS，经 RC | TI 要求 VC0 通过板上电阻/电容接 VSS |
| 6 | SRP | VSS | 本设计不使用库仑计电流采样，按数据表接地 |
| 7 | SRN | VSS | 同上 |
| 8 | TS | 10 kΩ NTC 到 VSS，或未使用时接 VSS | 若启用温度保护，必须配置阈值和 NTC 曲线 |
| 9 | DSG | NC | 现有高侧背靠背 P-MOS 不由此低侧 NFET driver 直接驱动 |
| 10 | CHG | NC | 现有充电 Q601/模拟 OVP 继续独立控制 |
| 11 | VSS | PACK− Kelvin 地 | 作为器件和 cell-tap 参考点 |
| 12 | SCL | I2C_SCL，4.7 kΩ 上拉到 REGOUT | 100/400 kHz 按总线电容确认 |
| 13 | SDA | I2C_SDA，4.7 kΩ 上拉到 REGOUT | 推荐启用 I2C CRC |
| 14 | ALERT | CELL_UV_FAULT_L / 硬件故障锁存输入 | 开漏输出；需按所选配置确认中断极性 |
| 15 | REGOUT | 3V3_CELL_MON | 配置为 3.3 V，旁路电容至少 1 µF |
| 16 | REGSRC | PACK+ 经独立低漏电二极管/滤波 | REGOUT LDO 及 CHG/DSG 驱动电源输入；若与 BAT 相连，须核算 REGOUT 负载对 BAT 保持电容的影响 |
| 17 | BAT | PACK+ 经低漏电二极管、串联 R 和滤波 C | 正常工作范围 3–27.5 V；PACK_4S 在 7.0–9.4 V 范围内有充足供电余量 |
| 18 | VC5 | PACK+ / CELL4+ tap，经 cell-input RC | 4S 最顶端实际电芯输入 |
| 19 | VC4A | CELL3+/CELL4− tap，经 cell-input RC | 与 VC4B 短接 |
| 20 | VC4B | CELL3+/CELL4− tap，经 cell-input RC | 与 VC4A 短接 |

### 电源与滤波初值

- BAT：由 PACK+ 供电，经低漏电隔离二极管和 100 Ω 串联电阻；BAT 对 VSS 初始取 10 µF。数据表允许 BAT 外部供电滤波电阻 50–1000 Ω、电容 1–40 µF；实际二极管漏电、启动时间和短路保持时间需验证。
- REGSRC：优先从 PACK+ 经独立低漏电二极管供电，并在 REGSRC–VSS 放置至少 1 µF。若采用 BAT 与 REGSRC 共用滤波节点，需按 REGOUT 负载重新验证 BAT 电容保持时间。
- VC 输入：初始按每个有效差分 cell 输入对使用 100 Ω 级串联电阻和 100 nF 级滤波电容；单个输入 RC 时间常数约 10 µs。TI 要求 cell input R=10–1000 Ω、C=0.1–10 µF，且 R×C≤200 µs。最终连接拓扑必须照 TI Figure 8-2/8-3 的滤波方式，而不是简单把四只电容都接到 GND。
- REGOUT：设为 3.3 V，放置 1 µF 旁路，供 I²C/ALERT 上拉和低功耗逻辑使用；不得用 REGOUT 直接供大负载。
- ALERT：开漏上拉到 REGOUT（初值 10 kΩ），并送硬件故障锁存；REGOUT 掉电时 ALERT 会失去上拉，所以**不能只靠 ALERT 的高阻态代表“无故障”**。

## 3. 保护寄存器和状态机初值

| 参数 | 初始候选 | 验证要求 |
|---|---|---|
| Cell count | 4S，按 Table 7-1 | 读回 cell enable map；逐个抽头断线注入 |
| CUV threshold | 1.050 V nominal | 实测动作窗口目标 1.00–1.10 V/单体；确认 1.0 V 附近全温 ADC 误差 |
| CUV delay | 1 个 ADSCAN | 电压扫描循环 NORMAL 模式约 1.1–18 ms，选择最快合规设置并测量 ALERT→隔离总延迟 |
| CUV recovery | 禁止自主恢复 | 先撤销 ARM，再要求明确重新武装；若采用 100 mV 恢复滞回须重新安全分析 |
| COV | 可设为 2.45 V 作为第二道监视，待 ADC 误差验证 | 现有独立模拟 2.449–2.551 V OVP 继续作为主充电保护 |
| Host watchdog | 启用 | 超时必须使 CELL_PROTECT_VALID 清零、DISCHARGE_ARM 释放 |
| I²C CRC | 启用 | 配置写入后逐项读回；CRC/通信错误立即禁止放电 |
| Cell balancing | 禁止自动用于快充 | 内部均衡最大 50 mA，不能替代 0.5 A 快充均衡 |

BQ76905 电芯电压 ADC 是逐个差分测量，16-bit 输出单位为 1 mV，数据手册列出典型 cell voltage measurement accuracy 4 mV。正常模式 ADSCAN 不是固定 366 µs；它随配置约 1.1–18 ms。必须用最快电压扫描配置，并在最终寄存器组合下实测 CUV 阈值穿越至 ALERT 和 MOS 关断的总延迟。电流 ADC 的 366 µs 数值不能误用作 cell-voltage ADSCAN 时间。

## 4. 与现有放电开关的互锁接口

建议增加以下逻辑信号：

- `CELL_MON_PG`：REGOUT 有效且 BQ76905 BAT 电压在推荐范围。
- `CELL_CONFIG_VALID`：MCU 已写入 4S、CUV/COV、delay、recovery、watchdog 等寄存器，并逐项读回匹配。
- `CELL_UV_FAULT_L`：ALERT 报告 CUV/诊断/看门狗故障时的低有效故障线。
- `CELL_PROTECT_VALID`：硬件组合 `CELL_MON_PG AND CELL_CONFIG_VALID AND NOT CELL_UV_FAULT`，任何输入开路或掉电都必须默认低。
- `DISCHARGE_ARM_LATCHED`：只在手动 ARM 请求、PACK_UV_OK、CELL_PROTECT_VALID 和 BOOST_READY 条件同时满足时置位；任何 UV、monitor reset、watchdog、I²C 配置错误或电源失效均异步清除。

现有 Q503 继续由 PACK_UV_OK 控制；Q504 的控制端改由 DISCHARGE_ARM_LATCHED。BQ76905 ALERT 不直接驱动功率 P-MOS 栅极，也不允许 MCU GPIO 单独覆盖硬件故障。保护故障解除、PACK 电压回弹或主电源恢复均不得自动重新闭合放电开关。

BQ76905 的 CHG/DSG 引脚是低侧 N-MOSFET gate driver，不能直接替代当前高侧背靠背 P-MOS 控制链。若改为使用 BQ 的 DSG/CHG 输出驱动低侧 NFET，必须重新审查放电回路接地、反向电流、负载地漂移和故障短路模式。

## 5. 上电配置时序

1. PACK_4S 经 BAT/REGSRC 供电，REGOUT 建立；此时硬件默认 CELL_PROTECT_VALID=0、DISCHARGE_ARM_LATCHED=0。
2. MCU 检查 REGOUT、PACK_4S 和 I²C 通信，写入 4S cell map、CUV/COV、delay、recovery、watchdog、温度保护设置。
3. MCU 逐项读回并核对 CRC、cell voltage 合理性、VC5 与各单体求和一致性、open-wire 检查结果。
4. 只有当所有监测通道有效、无 CUV/COV/诊断故障、host watchdog 已启用后，才允许 CELL_CONFIG_VALID 置位。
5. 经过显式 ARM 低→高边沿后，才可置位 DISCHARGE_ARM_LATCHED；Boost 预启动并验证 READY 后，允许备源进入 MUX。
6. 任一保护触发时先清除 DISCHARGE_ARM_LATCHED 并拉低 BOOST_EN；随后确认 Q501/Q502 VGS 回到关断区。故障清除后必须重新执行 ARM 低→高序列。

如果 MCU 没有完成配置，BQ76905 默认 CUV=2.5 V、COV=4.2 V 的电池默认阈值不适合本项目；因此“BQ 芯片已上电”不等于“单体保护已就绪”。上电、复位、brownout、I²C NACK/CRC 错误、VC tap 开路、REGOUT 掉电均须保持放电关闭。

## 6. 台架验收

1. 以四路隔离可编程源模拟 4S 抽头，先按 TI 4S pin map 接线，再逐一核对 CELL1–CELL4 ADC 读数和 VC5−VC0 组压。
2. 每路单体独立从 1.2 V 慢扫至 0.9 V，记录 CUV 寄存器状态、ALERT、CELL_PROTECT_VALID、DISCHARGE_ARM_LATCHED、Q501/Q502 VGS 和电流。覆盖 1.00–1.10 V 动作窗口和温度两端。
3. 以最快 ADSCAN 设置测量阈值穿越至物理隔离时间；目标≤5 ms。若做不到，按真实最坏延迟重新计算单体电压最低值与 EOL 保持时间。
4. 分别断开 VC0–VC5 各抽头、短接相邻输入、断 BAT、断 REGSRC、拉低 REGOUT、复位 MCU、注入 I²C CRC 错误和 host watchdog timeout。每种情况 CELL_PROTECT_VALID 必须低，放电开关必须保持关断。
5. 在 12 W 放电时制造弱单体初始 1.45/2.65/2.65/2.65 V，确认 CELL UV 先于单体越过 1.0 V 保护边界动作；组端 UVLO 不得掩盖弱单体。
6. CUV 触发后卸载并观察 pack voltage rebound；不得因回弹自动恢复。必须先使 ARM 请求为低，再重新置高。
