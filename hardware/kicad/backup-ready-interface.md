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
 && EFUSE_STATUS_OK
 && PATH_PROOF_OK
 && PATH_PROOF_FRESH
 && !BACKUP_FAULT_LATCH
 && !STARTUP_TIMEOUT

| 输入 | 有效条件 | 责任边界 |
|---|---|---|
| ARM_LATCHED | 已观察到 ARM 低，再收到新的 ARM 上升沿；无锁存故障 | 本模块/系统互锁 |
| CELL_PERMIT | 单体保护模块明确许可；开线、复位、监测无效时为低 | 单体保护模块，本模块只消费 |
| PACK_UV_OK | 组端欠压许可有效 | 组端保护模块 |
| BOOST_EN | Boost 已被硬件允许启动 | 系统互锁/Boost 控制 |
| BOOST_INPUT_WINDOW_OK | Boost 输入位于已验证工作窗口 | Boost 监测 |
| BOOST_OUTPUT_WINDOW_OK | Boost 输出位于负载允许窗口 | Boost/负载监测 |
| EFUSE_STATUS_OK | 按实际 U902 变体解释状态脚，且监测电源有效 | eFuse 状态接口 |
| PATH_PROOF_OK | 独立证明 U902 输入到 OUT/IN2 的通路能承担规定负载 | 证明负载/电压电流测量电路，当前未实现 |
| PATH_PROOF_FRESH | 最近一次通路证明仍在有效期内 | 证明负载/监督逻辑，当前未实现 |
| BACKUP_FAULT_LATCH | 任何备源故障已锁存 | 本模块/外部硬件锁存 |
| STARTUP_TIMEOUT | Boost/eFuse 未在规定时间内完成资格建立 | 启动监督逻辑，当前未实现 |

OV2_INHIBIT = !BACKUP_READY。只有所有资格成立时才允许把 OV2 驱动到 IN2 允许区。无控制电源、复位、信号开路或未 ARM 时，硬件必须被动保持 OV2 在禁止区；不能依赖 MCU 启动后再补救。

## 3. U902 变体语义

| 完整订货号候选 | 状态脚 | EFUSE_STATUS_OK 的必要条件 | 不能证明的事项 |
|---|---|---|---|
| TPS259470ARPW | AUXOFF、FLT | 监测电源有效，AUXOFF 高，FLT 高（未被拉低） | AUXOFF 不是 OUT Power-Good；数据手册列出的输出短路情形可能仍保持 AUXOFF/FLT 高 |
| TPS259474LRPW | PG、PGTH | 监测电源有效，PG 高 | PG 受 OUT→PGTH 分压控制；COUT 残压可使 PG 在上游通路已经失效时继续为高 |

因此 EFUSE_STATUS_OK 只是必要条件，不是带载证明。开漏状态脚在器件掉电时不能被默认上拉误判为有效；接收端必须有掉电安全的默认低/隔离措施。

## 4. 故障锁存与重新武装

1. 上电复位后，必须先采样到 ARM_REQ=0；ARM 高电平若跨越复位保持，不得被当作新的 ARM 边沿。
2. 只有在 CELL_PERMIT、PACK_UV_OK 和故障输入满足重新武装安全条件时，新的 ARM 低→高边沿才置位 ARM_LATCHED。
3. 若 ARM 上升沿发生时安全许可无效，该边沿被消费；许可随后恢复而 ARM 仍保持高，不得自动置位。
4. CELL_PERMIT、PACK_UV_OK 失效、eFuse/外部故障或启动超时会清除 ARM 并置位故障锁存。
5. 已经 READY 后，任一资格项丢失（Boost 输入/输出窗口、eFuse 状态、通路证明或证明新鲜度）均撤销 READY 并锁存故障。
6. 故障锁存只能在 ARM 为低且上游硬安全条件恢复时清除；之后还必须出现新的 ARM 上升沿。电压回弹、PG 恢复或故障脚自动重试不能自行重新 READY。
7. Boost 窗口和 eFuse 状态允许在 ARM 后的启动阶段逐步建立；启动超时前未就绪时保持 READY=0，不因正常启动过程立即误锁存。

### 4.1 对既有 ARM 模型的审查发现

既有 p0-efuse-qualification 分支的 BackupReadyLatch 将 arm_low_seen 初值设为 True。复现序列：上电时 ARM 已为高且 PACK_UV_OK 为低，第一次更新不 READY；随后 PACK_UV_OK 恢复而 ARM 仍保持高，模型会置位 READY，中间没有新的低→高边沿。这是重新武装状态机缺陷。

本分支状态机将 arm_low_seen 初值设为 False；上电高电平被忽略，只有实际采样低后才接受新的上升沿。对应回归已加入 test_backup_ready_supervisor.py。

## 5. 为什么不能只看 PG / AUXOFF / IN2 电压

- 基线 check_residual_input.py 使用 12 V、100 µF、10 kΩ 的示例空载 RC：eFuse 断开 1 ms 后 IN2 仍约 11.988 V，远高于示例 2.8 V 输入欠压门槛。它证明电压残留问题，但不是实测板级放电曲线。
- 470A 的 AUXOFF/FLT 不覆盖所有负载侧故障；474L 的 PGTH 只观察 OUT 电压，充电的 COUT 可在上游 eFuse 通路断开后维持 PG 高。
- 因此需要独立 PATH_PROOF_OK。已有审计分支提出 1 A / 200 µs 证明负载脉冲、100 mV 路径压降限值和 11.8 V 输出下限；本分支仅将其作为可复跑的筛选假设，不冻结为硬件参数。

按 10 kΩ 泄放、eFuse 断开约 1 ms、1 A / 200 µs 证明脉冲和 100 mV 压降门槛估算，粗略可识别的 COUT 上限约 2.0 mF。若最终 COUT 超过此值，必须增加脉冲幅度/宽度、改进测量方法或采用其他独立带载证明；不能沿用当前筛选参数。

最终测试脉冲必须按实装 COUT 最大值、eFuse ILIM 最小值、Boost 动态和负载电压下限重新定值；不得直接照搬示例值。

## 6. OV2 电气实现仍未闭环

基线 check_ov2_bias.py 是静态电阻/漏电角落脚本，候选使用 IN2 分压、ATL431LI 钳位和 NMOS 拉低。它不包含钳位启动、MOS 栅极传播、TPS2121 OV2 动态响应、主备同时变化竞态或完整控制电源失效测试。

本模块逻辑要求：

- 默认/禁止态：OV2 必须高于 TPS2121 OV2 上升阈值最大角；
- 允许态：OV2 必须低于下降阈值最小角；
- 任何 READY 撤销、控制电源掉电或逻辑输出高阻，都必须回到禁止态；
- 必须用最终器件、容差、温度、寄生和实装网表复核，并实测故障到 OV2 越过禁止阈值的延迟。

## 7. 当前证据边界与阻塞

| 层级 | 状态 |
|---|---|
| 已有设计 | 有主备拓扑、残压反例、OV2 静态偏置候选 |
| 已实现代码 | 本分支新增离散状态机与行为 SPICE 测试台 |
| 单元测试 | 本地 14 项通过；CI 结果待本分支运行 |
| 行为仿真 | Python 状态机和 RC 解析筛选；不等同真实器件模型 |
| SPICE 仿真 | 本分支 netlist 为理想开关/行为逻辑；ngspice CI 运行后才可标记通过 |
| 实物测试 | 未进行；无主备 MUX/eFuse 原理图与台架波形 |

阻塞项：U902 变体冻结、负载电压窗口、COUT 最大值、通路证明电路、启动超时实现、OV2 被动默认偏置、TPS2121/eFuse 实际网表和故障传播台架测试。

不得据此冻结 BOM、宣称主备硬件完成或宣称整机无缝切换通过。
