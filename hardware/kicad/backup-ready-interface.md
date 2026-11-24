# BACKUP_READY / OV2 接口契约（专项候选）

状态：**逻辑接口与行为模型候选；不是已实现的主备 MUX 原理图，也不是硬件放行。**  
共同基线：tortletortle/supercap-ups @ 360508c08f23f63cdd74fba7e0c201b0907d3825  
专项分支：agent/backup-ready-fail-safe-20261124

## 1. 目标与边界

本模块只负责备源资格、故障锁存和 TPS2121 IN2 的默认否决接口。它消费单体保护模块输出的 CELL_PERMIT，不修改或重建 BQ76905 单体保护逻辑。

共同基线 BOM 记录 U901=TPS2121（封装/订货后缀待定）和 U902=TPS259470ARPW（candidate_not_schematic）。逐一检查基线全部 10 张 KiCad 原理图，没有发现 U901、U902、TPS25947、TPS2121、OV2 或 BACKUP_READY 的器件实例/实际连线。因此，本文件是接口契约，不代表电路已接通。

## 2. BACKUP_READY 逻辑定义

BACKUP_READY 为高有效、失效默认低的备源带载资格，不是单一电压比较器或 eFuse 状态脚。

BACKUP_READY =
    ARM_LATCHED
 && CELL_PERMIT
 && PACK_UV_OK
 && BOOST_EN
 && BOOST_INPUT_WINDOW_OK
 && BOOST_OUTPUT_WINDOW_OK
 && EFUSE_INPUT_VALID
 && EFUSE_LOGIC_VALID
 && EFUSE_STATUS_OK
 && PATH_PROOF_OK
 && PATH_PROOF_FRESH
 && !BACKUP_FAULT_LATCH
 && !STARTUP_TIMEOUT

| 输入 | 有效条件 | 责任边界 |
|---|---|---|
| ARM_LATCHED | 复位后采样到 ARM 低，再收到新的 ARM 上升沿；无锁存故障 | 本模块/系统互锁 |
| CELL_PERMIT | 单体保护模块明确许可；开线、复位、监测无效时为低 | 单体保护模块，本模块只消费 |
| PACK_UV_OK | 组端欠压许可有效 | 组端保护模块 |
| BOOST_EN | Boost 已被硬件允许启动 | 系统互锁/Boost 控制 |
| BOOST_INPUT_WINDOW_OK | Boost 输入位于已验证工作窗口 | Boost 监测 |
| BOOST_OUTPUT_WINDOW_OK | Boost 输出位于负载允许窗口 | Boost 监测 |
| EFUSE_INPUT_VALID | 直接监测 U902 IN 引脚供电有效，不只监测 Boost 上游节点 | eFuse 输入监测 |
| EFUSE_LOGIC_VALID | AUXOFF/FLT/PG 的外部上拉与接收逻辑电源有效 | 状态接口 |
| EFUSE_STATUS_OK | 按实际 U902 变体解释状态脚 | eFuse 状态接口 |
| PATH_PROOF_OK | 独立证明 U902 IN→OUT/IN2 通路能承担规定负载 | 证明负载/电压电流测量电路，当前未实现 |
| PATH_PROOF_FRESH | 最近一次通过的通路证明未超过系统设定有效期 | 监督定时器，当前未实现 |
| BACKUP_FAULT_LATCH | 任何备源故障已锁存 | 本模块/外部硬件锁存 |
| STARTUP_TIMEOUT | Boost/eFuse 未在规定时间内完成资格建立 | 启动监督逻辑，当前未实现 |

软件/行为模型接口采用 path_proof_age_s 和 path_proof_max_age_s 计算新鲜度：缺失、负数、非有限值、零/负最大有效期或超期一律判为不新鲜。**100ms 仅用于单元测试夹具，不是已批准的硬件有效期。** 实际最大有效期必须由系统故障检测时间预算决定；若证明未刷新，必须在超期时撤销 READY，而不能继续沿用旧的成功结果。

OV2_INHIBIT = !BACKUP_READY。只有所有资格成立时才允许把 OV2 驱动到 IN2 允许区。无控制电源、复位、信号开路或未 ARM 时，硬件必须被动保持 OV2 在禁止区；不能依赖 MCU 启动后再补救。

## 3. U902 真实订货号、封装和引脚

TI 当前数据手册为 TPS25947 SLVSFC9C，2026-05 修订。RPW 封装为 10-pin QFN，标称 2mm × 2mm，工作温度范围 −40°C 至 +125°C，输入工作范围 2.7V 至 23V。

| 候选完整 MPN | 类型 | 状态脚 | 当前项目关系 |
|---|---|---|---|
| TPS259470ARPW | Auto-Retry、可调 OVLO、主动限流 | Pin 3 AUXOFF、Pin 4 FLT | 基线 BOM 当前记录；尚未进入原理图 |
| TPS259474LRPW | Latch-Off、可调 OVLO、Circuit Breaker | Pin 3 PG、Pin 4 PGTH | 备选变体；尚未批准替换 |

RPW 顶视引脚映射（两个变体共用封装）：

| Pin | 470A 功能 | 474L 功能 |
|---:|---|---|
| 1 | EN/UVLO | EN/UVLO |
| 2 | OVLO | OVLO |
| 3 | AUXOFF | PG |
| 4 | FLT | PGTH |
| 5 | IN | IN |
| 6 | OUT | OUT |
| 7 | dVdt | dVdt |
| 8 | GND | GND |
| 9 | ILM | ILM |
| 10 | ITIMER | ITIMER |

这两种料不是只换一个状态脚：过流响应、故障恢复策略和外部网络均有差异。TPS259470ARPW 是自动重试变体；数据手册给出的 tRST=110ms 为典型值，没有给出保证最大值。TPS259474LRPW 是锁断变体，电路断路器和重启方式不同。更换必须重新审查 ILIM/ITIMER、热设计、启动和故障恢复，不能直接替换封装符号后放行。

### 3.1 状态脚不能单独证明带载能力

- TPS259470x 的 AUXOFF 为开漏高有效，表示输入供电处于有效范围且 inrush 已完成。TI 明确说明：AUXOFF 在此后只因输入供电无效而撤销，**负载侧事件/故障不会使 AUXOFF 撤销**。
- TPS259470x 的 FLT 为开漏低有效，但并非所有故障都拉低。TI 故障表明确列出：输出对地短路时 FLT=H；AUXOFF 表中短路时 AUXOFF 也为 H。因此 TPS259470ARPW 的两个状态脚都可能显示“正常”，而输出路径已经不能供电。
- TPS259472x/474x 的 PG 是开漏高有效，取决于器件状态和 PGTH 电压。输出短路时 PG 仍按 PGTH 阈值决定；只要残压使 PGTH 维持高于下降阈值，PG 就可能继续为高。
- AUXOFF/PG 在器件无输入供电时没有主动下拉。外部上拉电源仍存在时，状态节点可能出现非零电压。因此必须分别监测 U902 IN 供电和状态逻辑上拉电源，不能只看引脚电平。

TPS259474L 的 PGTH 下降阈值规格为 1.076V min / 1.09V typ / 1.116V max；上升阈值为 1.183V min / 1.20V typ / 1.223V max。PG 的 tPGA、tPGD 均为 12µs **典型值**，数据手册没有列出最大保证值。本分支 SPICE 只用阈值角构造静态行为反例，没有把 12µs 当成最大延迟。

## 4. TPS2121 OV2 的实际逻辑和门限

TPS2121 为 RUX 12-pin VQFN-HR，标称 2.5mm × 2.0mm。U901 的完整订货后缀仍未在基线 BOM 中冻结。

TPS2121 引脚映射：

| Pin | 功能 |
|---:|---|
| 1、8 | OUT |
| 2 | IN2 |
| 3 | CP2 |
| 4 | OV2 |
| 5 | OV1 |
| 6 | PR1 |
| 7 | IN1 |
| 9 | ST |
| 10 | ILM |
| 11 | SS |
| 12 | GND |

TI 将 OV2 定义为 **IN2 的 active-low enable supervisor**。在 TPS2121 功能表中，OV2 ≥ VREF 时 IN2 被判为无效/禁止；OV2 < VREF 才有资格被选中。因此本项目的默认否决方向应是 OV2 高电平禁止 IN2，只有 BACKUP_READY 全部成立时才把 OV2 拉低到允许区。

TPS2121 VREF 规格（−40°C 至 +125°C）：

| 比较器方向 | MIN | TYP | MAX |
|---|---:|---:|---:|
| 上升阈值 | 1.01V | 1.06V | 1.10V |
| 下降阈值 | 0.99V | 1.04V | 1.09V |

保守接口边界：
- 禁止 IN2：OV2 必须高于 1.10V 最大上升阈值，并留出分压误差、漏电、噪声和瞬态裕量。
- 允许 IN2：OV2 必须低于 0.99V 最小下降阈值，并留出同类裕量。
- 不允许把 OV2 设计在 0.99V–1.10V 之间作为稳定逻辑状态。

基线 check_ov2_bias.py 的静态角落结果：IN2 到示例 falling-UV 边界时，OV2 最小 1.368V；资格允许态 OV2 最大 0.132V。两者分别跨过 1.10V 禁止边界和 0.99V 允许边界。但该脚本仅为电阻/漏电静态角落计算，不包含钳位启动、NMOS 栅极传播、TPS2121 动态响应、控制电源掉电和主备切换竞态，不能作为硬件验收。

## 5. 故障锁存与重新武装

1. 上电复位后，必须先采样到 ARM_REQ=0；ARM 高电平若跨越复位保持，不得被当作新的 ARM 边沿。
2. 只有在 CELL_PERMIT、PACK_UV_OK 和故障输入满足重新武装安全条件时，新的 ARM 低→高边沿才置位 ARM_LATCHED。
3. 若 ARM 上升沿发生时安全许可无效，该边沿被消费；许可随后恢复而 ARM 仍保持高，不得自动置位。
4. CELL_PERMIT、PACK_UV_OK 失效、eFuse/外部故障或启动超时会清除 ARM 并置位故障锁存。
5. 已经 READY 后，任一资格项丢失（Boost 输入/输出窗口、eFuse 状态、通路证明或证明新鲜度）均撤销 READY 并锁存故障。
6. 故障锁存只能在 ARM 为低且上游硬安全条件恢复时清除；之后还必须出现新的 ARM 上升沿。电压回弹、PG 恢复或 eFuse 自动重试不能自行重新 READY。
7. Boost 窗口和 eFuse 状态允许在 ARM 后的启动阶段逐步建立；启动超时前未就绪时保持 READY=0，不因正常启动过程立即误锁存。

### 5.1 对既有 ARM 模型的审查发现

既有 p0-efuse-qualification 分支的 BackupReadyLatch 将 arm_low_seen 初值设为 True。复现序列：上电时 ARM 已为高且 PACK_UV_OK 为低，第一次更新不 READY；随后 PACK_UV_OK 恢复而 ARM 仍保持高，模型会置位 READY，中间没有新的低→高边沿。这是重新武装状态机缺陷。

本分支状态机将 arm_low_seen 复位初值设为 False；上电高电平被忽略，只有实际采样低后才接受新的上升沿。对应回归已加入 test_backup_ready_supervisor.py。

## 6. 残压反例与 PATH_PROOF

- 基线 check_residual_input.py 使用 12V、100µF、10kΩ 的示例空载 RC：eFuse 断开 1ms 后 IN2 仍约 11.988V，远高于示例 2.8V 输入欠压门槛。它证明电压残留问题，但不是实测板级放电曲线。
- 470A 的 AUXOFF/FLT 对某些输出故障仍可能同时为高；474L 的 PGTH 只观察 OUT 电压，充电的 COUT 可在上游 eFuse 通路断开后维持 PG 高。
- 因此需要独立 PATH_PROOF_OK。当前行为 SPICE 用 1A / 200µs 证明负载脉冲、100mV 路径压降限值和 11.8V 输出下限作为筛选假设；这些不是已批准硬件参数。
- 在 10kΩ 泄放、eFuse 断开约 1ms、1A / 200µs 证明脉冲和 100mV 压降门槛下，简化电容放电估算的 COUT 识别上限约 2.0mF。最终证明脉冲必须按实装 COUT 最大值、eFuse ILIM 最小值、Boost 动态和负载电压下限重新定值。
- PATH_PROOF 还必须周期刷新。若 U902 在上次通过检测后失效，BACKUP_READY 最多只能维持到证明有效期结束；该最大有效期必须由整机容许的故障检测延迟和测试脉冲占空比共同决定。目前没有系统级依据冻结该时间。

若最终 COUT 超过当前筛选边界，必须增加脉冲幅度/宽度、改进电流/压降测量方法或采用其他独立带载证明；不能沿用当前筛选参数。

## 7. 当前证据边界与阻塞

| 层级 | 状态 |
|---|---|
| 已有设计 | 有主备拓扑、残压反例、OV2 静态偏置候选 |
| 已实现代码 | 本分支新增离散状态机、proof age 判定与行为 SPICE 测试台 |
| 单元测试 | 原始 14 项 CI 已通过；proof age 和状态电源有效性扩展正在验证 |
| 行为仿真 | Python 状态机和 RC 解析筛选；不等同真实器件模型 |
| SPICE 仿真 | ngspice 行为级理想开关测试已通过 10 项；非芯片宏模型 |
| 实物测试 | 未进行；无主备 MUX/eFuse 原理图与台架波形 |

阻塞项：U902 变体冻结、U901 完整订货号冻结、负载电压窗口、COUT 最大值、通路证明电路及刷新周期、启动超时实现、OV2 被动默认偏置、TPS2121/eFuse 实际网表和故障传播台架测试。

不得据此冻结 BOM、宣称主备硬件完成或宣称整机无缝切换通过。

## 8. 官方器件资料

- TPS25947，SLVSFC9C（2026-05 修订）：https://www.ti.com/lit/ds/symlink/tps25947.pdf
- TPS2120/TPS2121，SLVSEA3F（2020-08 修订）：https://www.ti.com/lit/ds/symlink/tps2121.pdf
