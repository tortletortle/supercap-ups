# 储能架构复核：4S10F HCC vs 2S30F HP vs 2S25F LR

日期：2026-11-22  
状态：独立研究分支；不合并主线、不冻结 BOM、不宣称完成硬件验证。

## 结论摘要

本轮把仓库现有 **4S×10F HCCCap** 与两个 2S 候选放到同一个恒功率 + DC ESR 模型中，并按各自厂商公布的寿命边界重算。

在 12 W 输出、1.2 s 任务、路径效率 99%、Boost 效率假设 92% 时：

| 方案 | EOL 等效容量 | EOL 包 DC ESR | 截止条件 | EOL 保持时间 | 1.2 s |
|---|---:|---:|---:|---:|---|
| 4S10F HCCCap | 1.575 F | 520 mΩ | 7.0 V | **1.327 s** | 通过，余量 0.127 s |
| 2S30F KAMCAP HP | 10.5 F | 352 mΩ | 2.7 V | **0.948 s** | 不通过，甚至未达到 1 s |
| 2S25F KAMCAP LR | 8.75 F | 200 mΩ | 2.7 V | **2.588 s** | 通过，余量 1.388 s |

**目前最有竞争力的储能候选是 2S25F LR，而不是此前默认的 2S30F。**  
**4S10F HCC 仍是已有工程主线中可保留的低成本基线。**  
2S30F 在新电容时的储能表现很好，但按 HP 系列寿命上限同时施加容量衰减和 ESR 增长后，余量不足。

这只是储能侧的模型结论。2S25F 还没有完成小批量报价、脉冲电流规格确认和低输入电压 Boost 实测，因此现在不能直接冻结为第一版 PCB。

## 1. 参数纠错与来源

### 4S10F HCCCap（仓库现有基线）

器件：HCCCap HCAP-C 2R7 106。

厂家规格书给出：
- 额定容量 10 F，容差 -10%～+30%；
- 额定电压 2.7 V；
- AC ESR 50 mΩ（1 kHz）；
- **DC ESR 65 mΩ（0.2 A）**；
- 最大 1 s 电流 9 A；
- 寿命条件下容量变化不超过 30%，ESR 小于初始值 2 倍；
- 串联使用时厂家要求控制单体电压，建议模块中每个单体低于 2.5 V。

规格书：[HCCCap HCAP-C 2R7 106 PDF](https://uploadcdn.oneyac.com/attachments/files/brand_pdf/hcccap/HCAP-C%202R7%20106.pdf)

仓库 V1.2 模型的初始条件是 4×10 F、每颗 2.35 V、包电压 9.4 V、7 V 截止。原 EOL 输入为 6.3 F/颗和 112.5 mΩ/颗。6.3 F 对应先取 -10% 容差再衰减 30%，但 112.5 mΩ 不是 HCC 规格书 65 mΩ DC ESR 的 2 倍上限。

本轮统一改为：
- EOL 单体容量：10 F × 0.90 × 0.70 = 6.3 F；
- EOL 单体 DC ESR：65 mΩ × 2 = 130 mΩ；
- 串联数：4；
- 初始单体电压：2.35 V；
- 包截止：7.0 V。

因此 EOL 等效包容量为 1.575 F，包 DC ESR 为 520 mΩ。

### 2S30F KAMCAP HP

器件：KAMCAP HP-2R7-J306VYJ23。

KAMCAP 厂家型号表区分 DC ESR 和 1 kHz AC ESR，该型号为：
- 30 F；
- **DC ESR 44 mΩ**；
- AC ESR 22 mΩ；
- 额定电压 2.7 V。

厂家 HP 系列寿命条件：常温 25℃、额定电压与半额定电压间循环 100 万次，容量衰减不超过 30%，ESR 变化不超过 4 倍；高温耐久条件也给出容量衰减不超过 30%、ESR 变化不超过 4 倍。

来源：
- [KAMCAP HP 系列规格表](https://www.kamcappower.com/products/winding-type-2.7-volt-super-capacitors/)
- [LCSC 型号页](https://www.lcsc.com/zh-CN/product-detail/C7436773.html)

**此前报告使用的 35 mΩ 应纠正为 44 mΩ DC ESR。** 不能拿该型号的 22 mΩ AC ESR 代替 DC ESR。

本轮 EOL 使用：
- 单体容量：30 F × 0.70 = 21 F；
- 单体 DC ESR：44 mΩ × 4 = 176 mΩ；
- 初始单体电压：2.4 V；
- TPS61088 输入设计截止：2.7 V。

因此 EOL 等效包容量 10.5 F、包 DC ESR 352 mΩ。

### 2S25F KAMCAP LR

器件：KAMCAP LR-2R7-J256UYJ21。

KAMCAP LR 厂家表列出：
- 25 F；
- **DC ESR 25 mΩ**；
- AC ESR 17 mΩ；
- 额定电压 2.7 V。

LR 系列寿命条件同样为容量衰减不超过 30%、ESR 变化不超过 4 倍。

来源：[KAMCAP LR 系列规格表](https://www.kamcappower.com/products/low-esr-winding-type-supercapacitors/)

本轮 EOL 使用：
- 单体容量：25 F × 0.70 = 17.5 F；
- 单体 DC ESR：25 mΩ × 4 = 100 mΩ；
- 初始单体电压：2.4 V；
- TPS61088 输入设计截止：2.7 V。

厂家公开产品表没有列出该 25 F 型号的容量容差，也没有给出该型号的 1 s 最大脉冲电流。本轮先按 25 F 名义容量计算，并额外做了 -10% 容量敏感性测试；必须向厂家确认后才能用于冻结设计。

## 2. 统一模型与验收边界

模型采用：
- 输出负载：12 W（12 V / 1 A）；
- 目标时长：1.2 s；
- 路径效率：99%（固定假设）；
- Boost 效率：90%、92%、94% 三档敏感性；
- 4S10F 初始单体电压 2.35 V，包截止 7.0 V；
- 两个 2S 候选初始单体电压 2.4 V，包截止 2.7 V；
- 时间步长：0.1 ms。

串联等效参数：

\[
C_{\rm eq}=\frac{C_{\rm cell}}{N},\qquad
R_{\rm pack}=N R_{\rm cell}
\]

电容侧恒功率：

\[
P_{\rm cap}=\frac{12}{\eta_{\rm boost}\times0.99}
\]

由电容开路电压 \(V_{\rm oc}\) 和包 DC ESR 求电流：

\[
P_{\rm cap}=I(V_{\rm oc}-IR_{\rm pack})
\]

取低电流物理解：

\[
I=\frac{2P_{\rm cap}}
{V_{\rm oc}+\sqrt{V_{\rm oc}^2-4R_{\rm pack}P_{\rm cap}}}
\]

端电压：

\[
V_{\rm terminal}=V_{\rm oc}-IR_{\rm pack}
\]

理想电容开路电压按：

\[
\frac{dV_{\rm oc}}{dt}=-\frac{I}{C_{\rm eq}}
\]

积分，直至包端电压触及对应截止条件或恒功率方程无实数解。

**注意：** 4S 和 2S 的截止值不是同一个数值。4S 保留仓库已有的 7 V 截止；2S 采用 TPS61088 2.7 V 输入范围下限作为本轮转换器可工作边界。2.7 V 不是电容单体安全阈值，也不意味着设计应长期运行到 UVLO。

## 3. 仿真结果

### EOL 保持时间

| 方案 | Boost 90% | Boost 92% | Boost 94% |
|---|---:|---:|---:|
| 4S10F HCC | 1.277 s | **1.327 s** | 1.377 s |
| 2S30F KAM HP | 0.828 s | **0.948 s** | 1.069 s |
| 2S25F KAM LR | 2.477 s | **2.588 s** | 2.699 s |

在本轮 EOL 参数下：
- 4S10F HCC 在三档效率假设下均超过 1.2 s，但 90% 情形只有约 76 ms 余量；
- 2S30F HP 在 90% 和 92% 时达不到 1 s；即使 94% 也只能达到约 1.069 s；
- 2S25F LR 在三档效率假设下均超过 1.2 s。

### 92% Boost 假设下的 1.2 s 状态

| 方案 | 1.2 s 包端电压 | 输入电流 | 判断 |
|---|---:|---:|---|
| 4S10F HCC EOL | 7.173 V | 1.837 A | 通过 |
| 2S30F KAM HP EOL | 已在 0.948 s 触及 2.7 V 截止 | — | 不通过 |
| 2S25F KAM LR EOL | 3.604 V | 3.655 A | 通过 |

2S25F 的电流明显高于 4S10F，因此它需要更严格地检查 Boost 电感峰值、开关限流、铜箔温升、输入电容 RMS 电流和超级电容脉冲电流规格。储能模型没有模拟这些开关级应力。

### 最低效率阈值

要在对应截止条件下完成目标时长，本模型求得的 Boost 固定效率下限约为：

| 方案 | 完成 1.0 s 所需效率 | 完成 1.2 s 所需效率 |
|---|---:|---:|
| 4S10F HCC EOL | 79.0% | **87.0%** |
| 2S30F KAM HP EOL | 92.9% | **96.1%** |
| 2S25F KAM LR EOL | 62.9% | **66.6%** |

这不是实际转换器效率测量，而是给定电容、ESR、截止条件下的模型阈值。

### 关键敏感性：30F 的 35 mΩ → 44 mΩ

在 2S30F、70% 容量、ESR×4、2.4 V/单体、92% Boost 假设下：
- 沿用旧 35 mΩ DC ESR：模型保持时间约 1.933 s；
- 改为厂家型号表的 44 mΩ DC ESR：模型保持时间约 **0.948 s**。

单是 DC ESR 参数纠正，就足以改变 1 s 任务的判断。此前“2S30F 是寿命末期稳妥基线”的结论不能继续沿用。

### 25F 容量容差敏感性

若 2S25F 的实际初始容量比 25 F 低 10%，其 EOL 容量由 17.5 F 降至 15.75 F/颗。在 92% Boost 假设下，模型保持时间仍约 **2.329 s**，仍通过 1.2 s。

这只能说明模型对 -10% 容量偏差有余量，不能替代厂家对容量容差的书面确认。

## 4. 工程判断

### 当前方案定位

1. **4S10F HCC：保留为现有工程基线。** 已有 V1.2 系统级保持时间模型、V1.3 TPS61088 器件级仿真和对应 BOM。按厂家 DC ESR 与寿命边界纠正后，EOL 仍能达到 1.2 s，但余量不宽。它的优势是较高 Boost 输入电压和较低输入电流；代价是四颗串联单体的 OVP、均压和测量复杂度。
2. **2S25F KAMCAP LR：升级为首要竞争候选。** 它在 EOL 恒功率模型中有明显储能侧余量，且只有两个单体。它的短板是 3.5～4.9 A 量级的输入电流、公开规格缺少容量容差和 1 s 脉冲电流、尚无可靠小批量报价，以及尚未完成低输入电压下的实际 Boost 验证。
3. **2S30F KAMCAP HP：降级为名义性能候选，不再默认作为 EOL 主线。** 新器件储能充足，但在厂家 HP 系列最大 ESR 变化边界下，EOL 余量不足。除非拿到更低 DC ESR 的确切料号、降低截止点且验证 Boost 可工作，或通过实测证明实际 ESR 增幅显著低于规格上限，否则不应把它当成稳妥的寿命末期方案。

### 不能据此冻结 BOM 的原因

- Boost 效率仍是固定敏感参数，不是对应输入电压下的实测曲线；
- 现有 V1.3 TPS61088 开关仿真覆盖 7～9.4 V 输入，尚未覆盖 2S 方案的 3.5～4.8 V 区间；
- 2S25F 的最大脉冲电流、容量容差、采购价格和交期尚未核实；
- 4S10F 的 1.2 s 连续器件级联合仿真、主备切换和整机测试仍未完成；
- 模型不含单体失配、温度、漏电、均压损耗、ORing、待机、充电效率、Boost 限流、开关纹波和电感饱和。

## 5. 下一步工作

按以下顺序推进：

1. **向 KAMCAP 询证 LR-2R7-J256UYJ21：** 容量容差、DC ESR 测量电流/方法、1 s 与 5 s 最大脉冲电流、漏电流、样品价格、批量价格和交期。
2. **新增 TPS61088 低输入电压仿真矩阵：** VIN=3.2/3.6/4.0/4.4/4.8 V，12 V/1 A，统一实际 RFSW、L1、RILIM、MODE 和输出滤波参数；记录稳态效率、纹波、输入平均/峰值电流、开关峰值和启动。TI 的 PMP9778 已证明 TPS61088 可在 3～4.2 V 输入范围提供 12 V/1.5 A 输出能力，但该参考设计不能替代本项目的效率和热验证。
3. **修正 4S10F EOL 器件级窗口：** 使用 6.3 F/颗、130 mΩ/颗、9.4 V 初始包电压，检查 7 V 截止附近的输出调节、限流和纹波。原 V1.4 的 eol_1p2s_130m_92pct.cir 是预偏置局部开关窗口，不是连续 1.2 s 仿真。
4. **用实测效率映射重跑三种架构：** 不再用同一个固定 92% 值替代 4～9 V 输入范围内的效率差异。
5. **最后才做第一版储能 BOM 决策。**

## 6. 可复现文件

- compare_storage_architectures.py：纯 Python 标准库恒功率 + ESR 模型；
- test_compare_storage_architectures.py：7 项回归测试；
- results.csv：18 组名义/EOL 与效率敏感性结果。

运行：

~~~bash
python compare_storage_architectures.py
python -m unittest -v
~~~

模型的时间步长收敛差异小于 0.1 ms，EOL 案例的电容能量守恒残差小于 0.0001 J。以上仅验证模型实现与数值积分，不代表 LTspice、硬件或竞赛指标通过。

## 参考资料

- [HCCCap HCAP-C 2R7 106 规格书](https://uploadcdn.oneyac.com/attachments/files/brand_pdf/hcccap/HCAP-C%202R7%20106.pdf)
- [KAMCAP HP 2.7 V 系列规格表](https://www.kamcappower.com/products/winding-type-2.7-volt-super-capacitors/)
- [KAMCAP LR 2.7 V 系列规格表](https://www.kamcappower.com/products/low-esr-winding-type-supercapacitors/)
- [TPS61088 数据手册 Rev. D](https://www.ti.com/lit/ds/symlink/tps61088.pdf)
- [TI PMP9778 低输入电压 TPS61088 参考设计](https://www.ti.com/lit/ug/tidubt9a/tidubt9a.pdf)
- 仓库 V1.2：sim/sweep.py、sim/hold_validation/dc_v1_2_hold_report.md
- 仓库 V1.3：sim/tps61088_v1_3/model/bom.csv、sim/tps61088_v1_3/joint/window_summary.md
