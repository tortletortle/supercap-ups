# BACKUP_READY / OV2 残压否决接口契约

状态：**审计补丁 / 行为模型要求，不是已放行硬件实现**  
审计基线：`tortletortle/supercap-ups` / `power-stage-integration` @ `22ec42f2625f2a428c8406132731768ada83129d`  
本文件所在分支：`audit/backup-ready-residual-fault`

## 1. 先给结论：器件版本与实现状态

| 项目 | 仓库证据 | 判定 |
|---|---|---|
| U902 当前 BOM 记录 | `TPS259470ARPW`，状态 `candidate_not_schematic` | 当前文档记录的器件候选，不是已实现器件 |
| 另一份方案 | `TPS259474LRPW` | 替代候选；不是当前 BOM/原理图实现 |
| 实际 KiCad 实例 | 当前分支全部 10 张 `.kicad_sch` 均无 U902、TPS25947 或 TPS2121 实例 | 当前没有完整主备 eFuse/MUX 原理图 |
| Power MUX 页面 | `power-mux.kicad_sch` 不存在 | OV2 与状态脚连接尚未实现 |

因此，严格说**TPS259470A 是当前 BOM/设计说明中记录的候选，TPS259474L 是备选候选；两者都不是当前原理图实现**。不能把 BOM 中的候选料号写成已经接线的 U902。

### 1.1 状态脚不可混用

| 器件完整订货号 | Pin 3 | Pin 4 | 保护方式 | 故障恢复 |
|---|---|---|---|---|
| TPS259470ARPW | AUXOFF，开漏、有效高 | FLT，开漏、有效低 | Active Current Limit | Auto-Retry |
| TPS259474LRPW | PG，开漏、有效高 | PGTH，模拟阈值输入 | Circuit Breaker | Latch-Off |

- **TPS259470A 没有 PG/PGTH。** AUXOFF 只表示输入处于有效窗口且 inrush 已完成；TI 明确说明负载侧故障不会使 AUXOFF 撤销。表 7-4 中过流、短路、ILM 异常、反向电流和过温时 AUXOFF 仍为高。FLT 也不是全故障覆盖：TI 表 7-3 的输出短路行列为 FLT 高。
- **TPS259474L 没有 AUXOFF/FLT。** PG 由 PGTH 电压及器件状态共同决定。PGTH 上升门限 1.183–1.223 V，下降门限 1.076–1.116 V；PG 的 tPGA/tPGD 均只有 12 µs 典型值。TI 对 PG 的描述明确排除了“overcurrent”作为直接撤销条件；持续过流由 Circuit Breaker 关断，PG 是否以及何时拉低仍要结合 PGTH/OUT 的实际下降波形确认。
- 474L 的 Latch-Off 与系统“故障锁存、人工重新武装”更一致；若以故障恢复策略为首要条件，它比 BOM 中的 470A Auto-Retry 更适合作为**优先评估候选**。但 PG 不是负载能力测试，不能只换成 474L 就宣称残压误接管问题已解决。

## 2. 从故障到 TPS2121 撤销 IN2 资格：已实现部分与断点

### 2.1 当前原理图真实存在的前半段

现有 `system-interlock.kicad_sch` 包含 U910（SN74LVC1G74DCT）与 U915（SN74LVC1G17DBVR）：

1. 实际许可网为 `ARM_PERMIT = PACK_UV_OK AND CELL_MON_PG AND CELL_CONFIG_VALID AND CELL_MON_ALERT_L`。
2. 任一许可撤销时，U910 的异步 CLR_N 清除 `DISCHARGE_ARM`；故障解除本身不会产生新的 MANUAL_ARM_REQ 上升沿，因此不会自动重新 ARM。
3. U915 将 R910/C910 的延迟节点整形成 `BOOST_EN`；D910 为 C910 提供快速放电通路。设计说明中的约 60 ms 是启动延迟估计，ILK-007 的小于 1 ms 关断目标尚无实测证据。
4. 重要边界：当前跨页功率级尚未完成，`BOOST_EN` 目前只是互锁页输出/测试点；它到 TPS61088 EN 的真实连接尚未在完整顶层网表中得到证明。不能把逻辑页的 BOOST_EN 生成等同于 Boost 已被实际关断。

### 2.2 文档描述的后半段仍只是候选

文档候选功率路径为：

```text
VIN_MAIN -------------------------------> TPS2121 IN1
PACK_4S -> discharge isolation -> TPS61088 -> BOOST_12V
                                            |
                                            v
                                  U902 TPS25947 eFuse
                                            |
                                     BOOST_READY_12V
                                            |
                                      TPS2121 IN2
                                            |
                                      TPS2121 OUT
                                            |
                                         LOAD_12V
```

但 U902、TPS2121、OV2 否决器件和它们之间的网线尚未出现在 KiCad 原理图。因此，**当前无法从实际网表证明“故障信号最终到达 OV2”的闭环**。目前只能审计文档候选和行为模型。

预期故障链必须是：

1. PACK 欠压、单体欠压/监测无效或 ARM 故障使 `DISCHARGE_ARM` 撤销，`BOOST_EN` 下降。
2. TPS61088 停止开关，但 Boost 输出电容、eFuse OUT 电容或 IN2 侧电容仍可能保持电荷。
3. U902 可能因输入 UVLO/OVLO、过流或系统禁用而切断功率通路；但 eFuse OUT/IN2 电容不因此瞬间归零。
4. 若只按 TPS2121 IN2 电压判有效，残压仍高于示例 UV 门限时，主源跌落会让 TPS2121 误选 IN2。
5. 必须由独立的 `BACKUP_READY` 资格逻辑撤销，并使 `OV2` 进入 IN2 禁止区；不能等待 IN2 电压自然放电。

### 2.3 已有残压反例的数值

`sim/backup_transfer/check_residual_input.py` 使用明确的示例参数：

- 初始 IN2：12.0 V
- 等效电容：100 µF
- 等效泄放：10 kΩ
- 时间常数：1.0 s

[
V_{IN2}(1\text{ ms})=12e^{-0.001/(10k\cdot100\mu F)}
\approx 11.988\text{ V}
]

按该脚本的 2.8 V 示例门限，空载自然衰减约需 1.455 s 才降到门限。**1.455 s 是该 RC 假设的模型结果，不是 TPS2121 或板级保证值。**

已有 7 组场景中，“backup fault during main sag”和“backup fault before hard main loss”均显示：
- voltage-only route：仍选 BACKUP；
- 独立 backup qualification route：分别保留 MAIN 或进入 HI_Z。

这已经证明“电压还在”不等于“备源还能带载”。但旧脚本把 `backup_ready` 作为外部布尔输入，没有解释如何生成该信号；本分支新增的测试补上这一缺口。

## 3. BACKUP_READY 的整机模型定义

`BACKUP_READY` 是**高有效、失效默认低、带资格新鲜度的备源能力许可**。不是单一电压比较器输出，也不是 TPS25947 的单个状态脚。

```text
BACKUP_READY =
    DISCHARGE_ARM
 && PACK_UV_OK
 && CELL_MON_PG
 && CELL_CONFIG_VALID
 && CELL_MON_ALERT_L
 && DISCHARGE_ARM
 && BOOST_EN
 && BOOST_V_WINDOW_OK
 && U902_STATUS_OK
 && LOAD_TEST_PASS
 && LOAD_TEST_FRESH
 && !BACKUP_FAULT_LATCH
 && !STARTUP_TIMEOUT
```

信号语义：

| 条件 | 定义 |
|---|---|
| `PACK_UV_OK` | 组端欠压保护许可有效 |
| `CELL_MON_PG` + `CELL_CONFIG_VALID` | 单体监测器电源有效且配置/诊断校验完成；任一低或开线时均不得 READY。测试脚本中的 `cell_protect_valid` 是这两项的逻辑合取 |
| `CELL_MON_ALERT_L` | BQ76905 ALERT 低有效信号处于无告警状态，即逻辑高 |
| `DISCHARGE_ARM` | 硬件放电许可锁存已置位 |
| `BOOST_EN` | Boost 已被硬件允许启动 |
| `BOOST_V_WINDOW_OK` | **U902 输入侧** Boost 电压处于负载允许窗口；不能只看 eFuse OUT/IN2 残压 |
| `U902_STATUS_OK` | 按具体料号解释：470A 用 AUXOFF 与 FLT；474L 用 PG。仅作为状态辅助条件 |
| `LOAD_TEST_PASS` | 对 U902 输入到输出的实际导通能力完成受控证明负载测试 |
| `LOAD_TEST_FRESH` | 最近一次证明负载测试仍在允许有效期内；超时未刷新则 READY 清零 |
| `BACKUP_FAULT_LATCH` | 备源故障锁存；任一故障后置位，不能因电压回弹自行清除 |
| `STARTUP_TIMEOUT` | Boost/eFuse 未在限定启动窗口内完成资格建立 |

### 3.1 为什么必须有 LOAD_TEST_PASS

TPS259470A 的 AUXOFF 不反映负载侧故障；TPS259474L 的 PG 依赖 PGTH/OUT 电压。若 OUT 电容仍有残压，PGTH 仍可能高于门限。两者都不能单独证明 U902 的输入到输出功率通路在负载下仍然导通。

第一轮行为模型采用一个**待硬件定值的诊断负载脉冲**：
- 测试电流：1 A；
- 脉冲宽度：200 µs；
- 试算功率通路电阻：45 mΩ；
- 允许输入/输出压差：100 mV；
- 输出电压下限：11.8 V。

模型对照结果：
- 活通路：1 A × 45 mΩ = 45 mV 压降，测试通过；
- 100 µF 隔离残压电容：200 µs 脉冲导致约 2.0 V 电压下降，测试失败；
- 470 µF 隔离残压电容：下降约 0.426 V，仍超过 100 mV 压差预算，测试失败。

这些值只是让反例可复跑的初始参数，**不是已冻结的电路参数或 TI 保证值**。最终脉冲需按实装 COUT、eFuse ILIM、Boost 动态和允许负载电压重新计算。该测试证明瞬时功率通路，不替代 12 W / 1.2 s 储能保持时间验收。

### 3.2 OV2 默认否决关系

```text
OV2_INHIBIT = !BACKUP_READY
```

- 未上电、逻辑掉电、未 ARM、故障锁存、测试失败或测试过期：`BACKUP_READY=0`，`OV2_INHIBIT=1`，TPS2121 IN2 必须被否决。
- 只有所有条件有效且证明负载测试通过：`BACKUP_READY=1`，才允许把 OV2 拉入 IN2 允许区。
- 推荐硬件默认态：无 READY 驱动时，利用 IN2 残压偏置使 OV2 落在禁止区；只有 READY 有效时才主动把 OV2 拉低。控制电源掉电不能意外解除否决。

TPS2121 的 OV2 比较器参考门限规格为：上升 1.01–1.10 V、下降 0.99–1.09 V。已有候选偏置检查在所设角落下得到：
- 禁止状态 OV2 最低 1.368 V，高于 1.10 V 最坏上升门限；
- 允许状态 OV2 最高 0.132 V，低于 0.99 V 最坏下降门限；
- ATL431LI 钳位电流模型 0.864–0.942 mA。

这只是静态电阻/漏电角落检查，不包括故障传播、钳位启动、NMOS 栅极下降、OV2 动态响应或主备同时变化的竞态。

## 4. 时序：规格保证、典型值、待实测

| 环节 | 数据手册/模型数值 | 证据等级与边界 |
|---|---:|---|
| TPS25947 OVLO 响应 | 1.2 µs | **典型值**；没有 min/max 最大延迟保证 |
| TPS259474x Circuit-Breaker 响应 | 2 µs | **典型值**；条件是 IOUT > 1.2 × ILIM 且 ITIMER 已到期；不包含 ITIMER 等待时间 |
| TPS259470x Active Current Limit 响应 | 400 µs | **典型值**；同样在 ITIMER 到期后计时，不是从故障起点算的总延迟 |
| TPS25947 快速过流/短路响应 | 500 ns | **典型值**；分别对应数据手册 tSC/tFT 规定的触发条件 |
| TPS25947 PG 断言/撤销去抖 | 12 µs / 12 µs | **典型值**；PGTH 必须先跨过对应阈值；不是整机故障到 READY 下降的总延迟 |
| TPS25947 A 版本自动重试间隔 | 110 ms | **典型值**；仅 A 自动重试系列相关，不能当作 474L 行为 |
| TPS25947 OVLO 快速恢复 | 90 µs | **典型值**；只对应数据手册 tSWOV 测试条件 |
| TPS2121 快速切换 tFSW | 5 µs | **典型值**；要求 CP2 ≥ VREF 且 OUT < 目标 INx；不是 OV2 禁止响应时间 |
| TPS2121 普通切换 tSW | 100 µs | **最大规格值**，适用数据手册列出的普通切换条件；不能套用到未建模的 OV2 关断链 |
| TPS2121 OV2 比较门限 | 上升 1.01–1.10 V；下降 0.99–1.09 V | **有 min/max 规格保证的阈值范围**；不代表有同等精度的系统关断延迟保证 |
| TPS25947 PGTH 门限 | 上升 1.183–1.223 V；下降 1.076–1.116 V | **有 min/max 规格保证的阈值范围** |
| BOOST_EN 撤销到实际 Boost 停止 | 尚无测量 | **待实测**；需测 U910 Q、DISCHARGE_ARM、D910、U915、BOOST_EN 和 Boost 开关/输出 |
| eFuse 状态脚到 BACKUP_READY 撤销 | 尚无完整电路 | **待实测**；470A AUXOFF 对负载侧故障不撤销，474L PG 对残压 OUT 的行为必须按实装 COUT 验证 |
| BACKUP_READY 到 OV2 越过禁止阈值 | 尚无完整电路 | **待实测**；外部逻辑、上拉、钳位、NMOS 和 OV2 引脚均未接入原理图 |
| OV2 禁止到 TPS2121 IN2 真正失去资格 | 尚无完整电路 | **待实测**；不得把 tFSW 直接当作该延迟 |
| 故障到 LOAD_12V 结果 | 尚无整机波形 | **待实测**；需要同时记录 LOAD_12V、IN1/IN2 电流及输出电容 |

**禁止把 1.2 µs + 12 µs + 5 µs 简单相加，宣称总故障响应 18.2 µs。**这些参数属于不同器件、不同触发条件；过流路径还包含 ITIMER，残压路径还包含电容放电/证明负载、逻辑传播和 TPS2121 资格撤销。

## 5. 可复跑命令

在仓库根目录执行：

```bash
python3 -B sim/backup_transfer/check_residual_input.py
python3 -B sim/backup_transfer/check_ov2_bias.py
python3 -B sim/backup_transfer/test_backup_ready_fault.py
python3 -B sim/design_convergence/power_stage_budget.py
```

新回归用例覆盖：
- 默认状态 READY=0、OV2 默认否决；
- 11.988 V 残压不能单独获得 READY；
- 470A AUXOFF/FLT 状态组合不能代替负载能力证明；
- 474L PGTH 被残压抬高时，PG 状态不能代替负载能力证明；
- 活通路与隔离电容在证明负载脉冲下的区分；
- PACK_UV、单体监测失效、DISCHARGE_ARM 撤销、故障锁存、测试过期、启动超时和 Boost 电压越窗均撤销 READY。

CI 已将 `sim/backup_transfer/**` 纳入路径触发，并增加上述三个备源切换回归脚本。

## 6. 台架/整机仿真必须保存的波形

| 阶段 | 需要看到的行为 | 关键通道 |
|---|---|---|
| 故障前 | 主源优先，备源已经预启动并完成资格 | VIN_MAIN、BOOST_12V、U902 IN/OUT、BACKUP_READY、OV2、TPS2121 ST |
| t0 故障注入 | PACK/CELL/Boost 或 eFuse 故障出现；故障锁存置位 | PACK_UV_OK、CELL_PROTECT_VALID、CELL_MON_ALERT_L、DISCHARGE_ARM、BOOST_EN、U902 状态 |
| t0 后残压阶段 | IN2/OUT 仍可能高于输入 UV 范围，但源通路已失去带载能力 | U902 IN、U902 OUT/IN2、PG 或 AUXOFF/FLT、COUT |
| 证明负载脉冲 | 活通路压差小；隔离残压电容电压明显下跌 | LOAD_TEST_EN、I_TEST、U902 IN−OUT、U902 OUT |
| 资格撤销 | READY 下降，OV2 进入禁止区 | BACKUP_READY、BACKUP_FAULT_LATCH、OV2_INHIBIT、OV2 |
| 主源仍有效 | TPS2121 保留 IN1，不误选残压 IN2 | VIN_MAIN、IN1/IN2 电流、ST、LOAD_12V |
| 主源也失效 | IN2 已被否决时输出应按设计进入 Hi-Z，而不是把残压误当成可用备源 | VIN_MAIN、IN2、OV2、ST、LOAD_12V |

现有模型的示例波形/时序点：
- t = 0：备源功率通路故障，输出电容初值 12.0 V；
- t = 1 ms：IN2 残压约 11.988 V，仍高于脚本的 2.8 V 示例门限；
- 1 A / 200 µs 证明负载脉冲：100 µF 隔离电容从 11.988 V 降至约 9.988 V；活通路按 45 mΩ 模型仅约 45 mV 压降；
- 只有 `LOAD_TEST_PASS` 仍有效且其他保护条件全部成立时，才允许 BACKUP_READY 置高。

这些是行为模型结果，不是实物波形。实物验收必须测得从故障注入到 `OV2` 越过禁止门限、TPS2121 IN2 电流归零/转移以及 LOAD_12V 响应的完整时间。

## 7. 当前放行阻塞

1. 新增真正的 `power-mux.kicad_sch`，放入 U901/U902、OV2 偏置/钳位、状态脚上拉、证明负载和测点。
2. 冻结 U902 的完整 MPN。若用 TPS259470ARPW，必须按 AUXOFF/FLT 接线；若用 TPS259474LRPW，必须按 PG/PGTH 接线，不能复制另一变体的引脚网络。
3. 为 U902 OUT/IN2 残压定义有效放电/隔离路径，确认证明负载测试的电流、宽度、刷新周期和输出电容角落。
4. 将 `BACKUP_READY` 与 `OV2_INHIBIT` 接入真实跨页网表；逻辑电源丢失、控制线开路和 MCU 复位时必须默认否决。
5. 用最终器件模型进行 TPS61088 + U902 + TPS2121 联合瞬态仿真，注入 pack UV、cell UV、Boost 停振、eFuse UVLO/OVLO、持续过流、输出短路和主源缓降/骤断。
6. KiCad 9 ERC/netlist 通过后，再进行限能台架验证；保存完整故障时序和负载端电压/电流。

## 8. 依据

- TI TPS25947 Rev. C 数据手册（2026-05）：https://www.ti.com/lit/ds/symlink/tps25947.pdf
- TI TPS2121 数据手册：https://www.ti.com/lit/ds/symlink/tps2121.pdf
- 仓库 `hardware/kicad/backup-pre-ready-switching.md`
- 仓库 `hardware/kicad/system-interlock-design.md`
- 仓库 `hardware/kicad/POWER_STAGE_DESIGN_CONVERGENCE.md`
- 仓库 `sim/backup_transfer/check_residual_input.py`
- 仓库 `sim/backup_transfer/check_ov2_bias.py`
