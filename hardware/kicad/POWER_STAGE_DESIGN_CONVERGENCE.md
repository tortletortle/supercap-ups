# 电源级收敛评审（工程候选，非原理图放行）

基线仓库：`tortletortle/supercap-ups`  
基线分支：`power-stage-integration`  
基线提交：`d2da3e66406901a1970123faa9b69342a0f76ba8`  
对照分支：`main`，提交 `4d1c83e9ca00c750bcbef4eb7fb76134a87d64da`。该基线快照当时领先 main 2 个提交；本轮工程资料提交在该快照后追加。

本文件把现有 KiCad 页、模型和器件资料收敛成可执行的工程候选。它**不代表原理图已完成**，也不把宏模型或静态计算当作台架验收。

## 1. 不可更改的系统边界

- 4S 超级电容组的最大允许端电压：**9.400 V**。不得为保持时间而提高。
- 负载：12 V、1 A、12 W。
- EOL 保持时间：至少 1.200 s。
- 储能候选：4 × Eaton HVH1230-2R7206-R，20 F、2.7 V、±20%；样机容量分选目标 (C_{max}/C_{min} \le 1.08)。
- EOL 压力模型：每颗 (C=20\times0.8\times0.7=11.2\,F)，每颗 DC ESR 取 (2\times53=106\,m\Omega)。**106 mΩ 是压力假设，不是厂家给出的 EOL DC ESR 保证值**：Eaton 规格中的寿命 ESR 项是 AC ESR，最终必须以实际样品在任务电流、温度下测得的 DC 压降复核。
- 组端 UVLO 采用已加载外部接收端的静态最早动作角点 7.110123 V；Boost 只对已验证输入范围 7.0 V 及以上给保持时间信用。

Eaton 2025/2026 版 ELX1538 数据表列出 20 F 单体最大 DC ESR 53 mΩ（25 °C）、容量 ±20%、寿命 1500 h @70 °C/2.7 V 后容量不低于额定值 70%、AC ESR 不超过初始最大值 200%。因此本模型用 11.2 F（低容差再乘 70%）是比“额定容量 70%”更保守的组合；106 mΩ 仍需样品测量确认。数据表：https://www.eaton.com/content/dam/eaton/products/electronic-components/resources/data-sheet/eaton-hvh-supercapacitors-cylindrical-cells-high-density-data-sheet-elx1538-en.pdf

## 2. 当前候选架构

### 2.1 储能与均压

- C1–C4：Eaton HVH1230-2R7206-R，20 F / 2.7 V，径向 12.5 mm × 30 mm，5 mm 引脚间距。
- R301–R304：2.2 kΩ / 1%，分别跨接每颗单体。2.25 V 时每支路约 1.02 mA、2.30 mW；2.7 V 时约 1.23 mA、3.31 mW。四支路在 2.7 V/颗时总耗散约 13.2 mW。
- 2.2 kΩ 是慢速漏电均压，不是 0.5 A 快充时的动态均衡器。继续采用容量分选；若批次比值超过 1.08，必须重新跑充电失配模型，不允许仅靠这四只泄放电阻放行。

### 2.2 充电级

- 主 Buck：TPS54302；R101=30 mΩ，INA180A1 增益 20 V/V；0.300 V 电流设定对应 (I_{CC}=0.300/(20\times0.030)=0.500\,A)。
- 本地 Buck 分压：R104=162 kΩ、R105=10 kΩ，约 10.25 V 标称，仅作为精密外环失效时的上限兜底；不能把该分压当作 9.4 V 充电终点。
- 精密 CV：REF5025 + OPA333；R601/R602=52.60 kΩ/20.00 kΩ，2.500 V 基准，名义组端 CV 9.075 V。现有静态角点为 **9.0580–9.0921 V**。
- 独立总压 OVP：独立 REF5025 + TLV9031；R605/R606=54.20 kΩ/20.00 kΩ，名义 9.275 V，静态角点 **9.2451–9.3049 V**。最迟静态 OVP 到 9.400 V 上限仅有 **95.1 mV**，必须用实际充电电流、关断延迟、输出电容和线路寄生测最大过冲。
- 四路单体 OVP：OPA4197 差分采样 + LM339B 开集输出，静态动作范围 **2.449–2.551 V/单体**。对 2.7 V 额定值的最小静态余量为 149 mV。CHG_OVP_OD 直接拉低 Buck EN；总压 OVP 另行切断 Q601 串联充电开关。
- CV 最大角到最早总压 OVP 角的静态分离为 153.0 mV。CV 最低角比 9.0 V 最低静置组压目标高 58 mV；现有 60 s 静置模型最低约 9.0343 V，比 9.0 V 高 34.3 mV。
- 充电器许可链仍未完成：CHG_SAFE_IN 是台架接口；参考就绪、采样完整、抽头开路、故障锁存及手动重新武装尚未形成自动硬件闭环。不能把 MCU 单独作为 OVP 最终关断元件。
- 0.5 A 快充只适用于容量比受控样机。现有 measured-terminal CC/CV 模型在容量比 1.08、每颗 DC ESR=106 mΩ、CV=9.058–9.0921 V、静置 60 s 时，峰值单体约 2.397–2.4065 V，静置组压约 9.0355–9.0696 V，保持时间约 1.515–1.573 s；这是理想环路模型，不是硬件证据。该结果表明自然 CV 降流可能足够，暂不冻结额外的 50 mA 硬切换级。仍须实测 CC→CV 交接、单体 OVP 最低角 2.449 V 和动态过冲。2.2 kΩ 泄放不能在 0.5 A 下钳住失配单体。

### 2.3 组端欠压与单体欠压

- 现有 TPS3700 组端 UVLO 加入实际开关接收负载后，下降动作角点约 **6.840–7.110 V**，上升恢复约 **7.285–7.499 V**。组端 UVLO 不能替代单体 UV。
- 当前硬件候选中没有已落图的四路单体欠压保护。行为模型已有弱单体反例：初始单体 1.45/2.65/2.65/2.65 V 时，弱单体约在 1.033 s 到达 1.0 V，而组端仍约 8.024 V。
- 单体 UV 优先验证候选：TI BQ76905。器件支持 2S–5S，BAT 供电范围 3–27.5 V，可由 PACK_4S 供电；CUV 阈值寄存器范围 0–5.5 V、1 mV 步进，支持开线检测、ALERT 和自主保护。TI 资料：https://www.ti.com/lit/ds/symlink/bq76905.pdf ；技术参考手册：https://www.ti.com/lit/ug/sluuci8a/sluuci8a.pdf
- 初始配置候选：4S 输入，CUV=1.050 V 标称，最终实测动作窗口暂定 1.00–1.10 V/单体，CUV delay=1 个 ADSCAN，恢复设为不自动恢复；ALERT 进入硬件放电许可锁存。该阈值窗口仍须结合 Eaton 单体最低端电压和 BQ76905 在 1.0 V 附近的全温误差确认。BQ76905 的 COV 可作为诊断/第二道保护，但现有独立模拟 OVP 继续保留，直到 BQ 的 2.7 V 超级电容应用、ADC 低端误差、配置保持和动作延迟全部通过验证。
- 采用 100 Ω 串联输入电阻和 100 nF 滤波电容作为首轮输入网络起点（均在数据表推荐的 cell input RC 范围内），最终按 TI 参考设计、采样扫描时间和开线测试复核。
- 重要限制：BQ76905 是电池监测/保护器件，不是已验证的超级电容保护方案；TI 的典型应用示例把最小单体工作电压设为 2.5 V，但 CUV 寄存器允许设到 1.0 V。必须实测 1.0 V 附近的精度与延迟。上电时若配置未完成、REGOUT/参考无效、I²C 配置校验失败或器件复位，CELL_PROTECT_VALID 必须为低并阻止 DISCHARGE_ARM。不得让“MCU 尚未配置好”变成允许放电。
- BQ76905 的内部均衡最大 50 mA，且由主机命令控制，不足以替代 0.5 A 快充均衡；只能在 50 mA 末段或更低电流下评估。

### 2.4 放电隔离与 Boost

- 物理隔离候选：Q501/Q502 两只 Si7149DP 背靠背 P-MOS，Q503/Q504 为低侧栅极下拉许可；PACK_UV_OK 与 DISCHARGE_ARM 必须同时有效。任何控制掉电、保护无效或 ARM 释放时，R501 应使 P-MOS 的 VGS 回到约 0 V。
- Si7149DP 25 °C 最大 RDS(on) 9.4 mΩ/只，双管静态上限 18.8 mΩ；热态工程估计约 28–30 mΩ，仍需测量。**全放电输入路径目标暂定不超过 100 mΩ（热态）**，该预算包括双 P-MOS、保险/保护元件、连接器、铜箔和焊点；不允许只报 MOSFET 数据表电阻。
- Boost：TPS61088；当前宏模型研究候选为 L=3.3 µH、RFSW=324 kΩ、RILIM=100 kΩ、CIN 有效值约 35 µF、COUT 有效值约 47 µF、ESR 约 3 mΩ、补偿 21.5 kΩ + 13 nF + 100 pF、反馈 1.076 MΩ/120 kΩ。宏模型报告中的短时开关纹波/启动窗口可用于功率级趋势分析，**不能用约 99% 宏模型窗口效率代替实物效率**。
- TPS61088 数据表工作输入范围 2.7–12 V，100 kΩ RILIM 的峰值限流随 PFM/FPWM 条件和公差变化；当前 3.3 µH 电感的 9.5 A Isat 是典型值，不是保证最小值。应满足 (I_{LIM,max} \le 0.8\times I_{SAT,min})，或选用具有保证 Isat 下限的电感。不能只凭正常 1 A 负载仿真峰值 2.85 A 就忽略启动/短路时的限流角点。
- 4 颗 22 µF/25 V/X7R/1210 输出 MLCC 不能按 88 µF 标称值记账。必须按 12 V DC bias、温度和批次确认有效 COUT≥47 µF；CIN≥35 µF 也要按实际电压偏置复核。
- BOOST_EN 目前只有测试点；DISCHARGE_ARM 尚无真实硬件许可发生器。Boost 高边体二极管会造成 EN 关闭时的预偏置/反向路径，必须同时保留物理隔离。

### 2.5 主备切换候选

- 候选拓扑：VIN_MAIN → TPS2121 IN1；TPS61088 BOOST_12V → TPS25947 eFuse → BOOST_READY_12V → TPS2121 IN2；TPS2121 OUT → LOAD_12V。充电输入继续独立取 VIN_MAIN。
- TPS2121：外部 CP2 参考、PR1 主源优先判定；当前 35.7 kΩ/10.0 kΩ 与 2.5 V 参考的名义主源比较点约 11.425 V，仅为候选起点。44.2 kΩ ILIM 候选对应约 2–3 A 范围，需按负载和浪涌实测。
- TPS25947：备源 eFuse，82.5 kΩ/10 kΩ UVLO 分压和 1.65 kΩ ILM 为已有候选值；OVLO、dV/dt、ITIMER 和 PG/READY 逻辑仍待冻结。
- 备源就绪不能只看 IN2 电压。eFuse 断开后 100 µF 输入电容可在 1 ms 后仍保持约 11.988 V，足以被 MUX 误判为有效备源。必须有独立 BACKUP_READY/OV2 否决：PACK_UV_OK、CELL_PROTECT_VALID、Boost 输出窗口、eFuse 状态全部成立才允许 IN2 参与选路；故障撤销后应维持否决，直到明确重新武装。
- 145 mΩ 输出路径模型由 MUX/eFuse 热态电阻预算组成，1 A 时约 145 mV 压降。当前 Boost 12.0 V 设定经此路径可能只有约 11.855 V 到达负载。**负载允许的最小/最大电压尚未给出，因此 12.0 V Boost 反馈值不能最终冻结**；先取得负载电压窗口，再决定输出设定和 OVLO。
- 备源应在主源存在时预启动并验证 READY。TPS61088 模型 EN→98% 约 11.23–11.28 ms；若等主源掉电后才冷启动，按 1 A、0.5 V 允许跌落估算需要约 22.56 mF 理想保持电容，故不作为无缝接管方案。

## 3. 12 W / 1.2 s / EOL 联合预算

采用 4×11.2 F、每颗 106 mΩ、初始开路组压 9.0 V、输出路径 145 mΩ、Boost 效率 85%、PACK UVLO 7.110123 V、Boost 输入证据下限 7.0 V。输出路径 1 A 损耗为 0.145 W，Boost 输入功率：

[
P_{in}=\frac{12+1^2\times0.145}{0.85}=14.2882\ W
]

四颗等值串联的等效电容为 2.8 F；储能单体总 ESR 为 0.424 Ω。输入串联路径 Rpath 计入 MOSFET、连接器、铜箔和其它新增串联损耗。加载初值由 (V_{OC}=V_{loaded}+R_{total}P/V_{loaded}) 求解；放电时间使用恒功率与串联 ESR 的解析积分。PACK UVLO 转换到 Boost 输入端后，与 7.0 V 证据下限取较大值。

| Boost 效率 | 新增输入路径 R | EOL 保持时间 | 相对 1.2 s 余量 |
|---:|---:|---:|---:|
| 85% | 50 mΩ | 1.526 s | +326 ms |
| 85% | 100 mΩ | 1.375 s | +175 ms |
| 85% | 150 mΩ | 1.216 s | +16 ms |
| 85% | 200 mΩ | 1.058 s | −142 ms |
| 90% | 100 mΩ | 1.555 s | +355 ms |
| 90% | 150 mΩ | 1.394 s | +194 ms |

同一模型下 85% 效率的理论 Rpath 临界约 155 mΩ；它没有动态、测量或批次裕量。故推荐设计目标定为 **Rpath≤100 mΩ 热态**，150 mΩ 只作为极限测试点。100 mΩ 时初始加载组压约 8.073 V；Boost 输入在 7.0 V 证据边界处电流约 2.041 A，输入路径压降约 204 mV、耗散约 0.417 W；每颗 106 mΩ 电容 ESR 瞬时耗散约 0.442 W。Eaton 20 F 单体数据表列连续电流 1.92 A（15 °C 温升）和脉冲电流 13 A（数据表定义的 1 s 条件），本项目约 2 A、1.2 s 需做真实温升/端压试验，不能直接外推额定值。

复跑：`python3 -B sim/design_convergence/power_stage_budget.py`。该模型是系统能量与串联损耗预算，不是芯片级连续开关仿真。

## 4. 目前禁止标记为“完成”的项目

1. 单体 UV 保护页、BQ76905 配置/失效默认状态和硬件关断链。
2. DISCHARGE_ARM 锁存/重新武装逻辑；不得把外部 ARM 直接硬接高。
3. TPS2121 + TPS25947 主备 MUX/eFuse 原理图，以及 IN2 残压抑制和 BACKUP_READY 硬件资格。
4. CHG_SAFE_IN 自动许可、参考就绪、抽头开路检测、故障锁存及手动复位。
5. TPS54302 内 CC、外 CV、限流注入三条环路的环路增益/相位裕度、启动和 CC→CV 过渡验证。
6. TPS61088 电感 Isat 最小保证、RILIM 最大限流角点、CIN/COUT 直流偏置、热态效率和连续 1.2 s 联合仿真。
7. MOSFET SOA/热、关断残流、预偏置、浪涌、反灌和 PCB 铜损验证。
8. 负载 12 V 允许窗口、主适配器容差、允许断供时间及连接器/保险规格。

## 5. 环路补偿验证方法（不预先冻结试值）

TPS54302 的外部 CV（OPA333）与 CC（TLV9001/INA180）均通过注入 FB 改变 Buck 调节。当前 R108/C107/R109 和 OPA333 47 kΩ/10 nF 只算首轮试值。禁止只凭时域“看起来不振荡”签收。

- 在最终 PCB 与实际电容/电感模型上分别测 Buck 电压环、CC 环、外部 CV 环的 Bode；对 FB/COMP 注入点使用隔离注入变压器或适当的小信号注入夹具，确认测量不破坏直流偏置。
- 测量 CC、CV 两个模式和 CC→CV 交接附近；扫 VIN=10.8/12/13.2 V（适配器范围仍需确认）、PACK=低/中/高、COUT 有效值最小/最大、温度和负载。
- 初始验收目标：相位裕度≥45°（目标≥60°）、增益裕度≥10 dB；交越频率需低于开关频率的 1/10，并满足 TPS54302 数据表推荐补偿/输出电容范围。若实测环路与宏模型不符，以实测/厂商设计工具结果为准。
- 同时记录启动过冲、预偏置启动、负载阶跃、限流恢复、充电器禁用后的残余电流。独立 OVP 必须在任何环路失控情形下切断串联 Q601，且实测 PACK 峰值≤9.400 V。

## 6. 下一轮 KiCad 源文件变更清单

以下为下一轮实现顺序，不在本次文档提交中直接修改未经校核的电气连线：

| 顺序 | 文件 | 变更 |
|---:|---|---|
| 1 | `hardware/kicad/supercap-ups-4s.kicad_sch` | 新增 Cell UV Monitor、Power MUX/Backup eFuse、System Interlock 三个层级页；保留现有 Boost/充电/OVP/UVLO 页。 |
| 2 | `hardware/kicad/cell-uv-monitor.kicad_sch`（新增） | BQ76905 4S 输入、VC0–VC4 滤波、未用通道处理、REGOUT/ALERT/通信、配置有效反馈和 TP。 |
| 3 | `hardware/kicad/system-interlock.kicad_sch`（新增） | PACK_UV_OK、CELL_UV_FAULT、CELL_PROTECT_VALID、BOOST_READY、手动 ARM、故障锁存和 DISCHARGE_ARM 输出；任何电源/参考/采样无效时默认禁止。 |
| 4 | `hardware/kicad/power-mux.kicad_sch`（新增） | TPS2121、TPS25947、IN2 残压否决、BACKUP_READY、LOAD_12V 和反灌测点。 |
| 5 | `hardware/kicad/pack-discharge-switch.kicad_sch` | DISCHARGE_ARM 改接锁存输出；CELL_UV_FAULT 与 PACK_UV_OK 硬件撤销许可；复核 P-MOS VGS、热态 RDS(on) 和单管短路故障。 |
| 6 | `hardware/kicad/supercap-ups-charger.kicad_sch` / `precision-cv-ovp.kicad_sch` | 只在完成环路和故障逻辑验证后更新补偿、CV/OVP 和 Q601 门控；保留单体 OVP 独立路径。 |
| 7 | `hardware/kicad/BOM_PRELIMINARY.csv`（本轮新增） | 记录当前 MPN/封装候选、额定值、替代料、验证状态和未关闭事项；完成样品/封装/热校核后再冻结正式 BOM。 |
| 8 | `sim/design_convergence/`（新增） | 保持时间解析预算、联合角点、系统验收矩阵和复跑说明；后续增加 BQ76905 CUV、MUX 残压和充电环路仿真。 |

### 推荐测试点

- 储能/功率：TP_PACK_KELVIN、TP_VIN_BOOST、TP_CELL1–TP_CELL4、TP_BOOST_SW、TP_BOOST_12V、TP_LOAD_12V。
- 保护/互锁：TP_PACK_UV_OK、TP_CELL_UV_ALERT、TP_CELL_PROTECT_VALID、TP_DISCHARGE_ARM、TP_BOOST_EN、TP_BACKUP_READY、TP_MUX_ST、TP_OV2_INHIBIT。
- 充电：TP_CHG_EN、TP_CHG_FB、TP_CHG_OVP_OD、TP_CHG_CURRENT、TP_CV_REF、TP_OVP_REF、TP_Q601_GS、TP_5V_CV、TP_5V_OVP。
- 高速功率节点的测试点应使用短回路/同轴或差分探头，不允许用长地线探头环路测 SW 节点。

## 7. 故障默认状态与关断顺序

| 事件 | 必须的硬件默认动作 |
|---|---|
| MCU 复位、未启动或 I²C 配置未确认 | CHG_ALLOW=0；CELL_PROTECT_VALID=0；DISCHARGE_ARM=0 |
| 任一单体 OVP | CHG_OVP_OD 拉低 Buck EN；Q601 串联关断许可撤销；故障锁存，不能因电压回落自行重启 |
| 任一单体 UV / BQ76905 掉电或诊断失败 | DISCHARGE_ARM 清除，BOOST_EN 拉低，背靠背放电开关断开；故障锁存 |
| PACK_UV_OK 拉低 | 同步撤销 BOOST_EN 和放电开关许可；负载移除后的组压回弹不得重新 ARM |
| 参考/采样电源无效、抽头开路 | 禁止充电；若影响单体 UV 监测有效性，同时禁止放电 |
| Boost 未达到有效输出窗口或 eFuse 未 PG | OV2 保持否决，TPS2121 不得把残压 IN2 当成可用备源 |
| 主源恢复 | 主源稳定后由 TPS2121 回到主源；备源可按策略退出，但不得形成两路反灌 |
| 故障解除 | 必须先观察 ARM 请求为低，再接受新的 ARM 上升沿；保护解除本身不等于自动重启 |

关断时序应通过实测证明：先撤销 BOOST_EN/充电 EN，再确认功率开关 VGS 回到关断区；放电硬隔离必须覆盖 Boost 高边体二极管路径。任何单一信号线开路、辅助电源掉电或 MCU 高阻均不得使充/放电默认导通。

## 8. 放行门槛

最终电气图至少通过：KiCad ERC/网表端点审查；BOM MPN 与封装复核；EOL 12 W/1.2 s 联合仿真；充电 CC/CV/OVP 联合仿真；单体 UV/OV 故障注入；主备 MUX 残压与反灌仿真；MOSFET 热/SOA 复核；以及限能台架测试。没有这些证据前，状态只能标为“工程候选/待验证”，不能标为“完成”。
