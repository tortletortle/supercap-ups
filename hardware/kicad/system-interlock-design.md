# 硬件放电互锁与 Boost 使能时序（V0.1 候选）

状态：`system-interlock.kicad_sch` 已落入顶层层级；KiCad ERC/网表结果待本轮 CI 确认。该页实现**故障清除型放电 ARM 锁存**和**延迟 BOOST_EN**，不等同于完整主备切换控制器。

## 1. 信号契约

| 信号 | 方向/有效电平 | 来源或用途 |
|---|---|---|
| `PACK_UV_OK` | 输入，高有效 | 现有 TPS3700 组端欠压监督；低表示 PACK 不允许放电 |
| `CELL_MON_PG` | 输入，高有效 | U914 TPS3839G33 监测 BQ76905 的 REGOUT；低表示监测电源未就绪 |
| `CELL_CONFIG_VALID` | 输入，高有效 | J910 pin 1；主控完成 4S 配置、寄存器读回、CRC/开线检查和 watchdog 配置后才置高 |
| `CELL_MON_ALERT_L` | 输入，低有效故障 | BQ76905 ALERT 开漏线；高表示当前无已配置告警 |
| `MANUAL_ARM_REQ` | 输入，上升沿有效 | J910 pin 2；必须有新的低到高边沿才允许 ARM |
| `ARM_PERMIT` | 内部，高有效 | `PACK_UV_OK AND CELL_MON_PG AND CELL_CONFIG_VALID AND CELL_MON_ALERT_L` |
| `DISCHARGE_ARM` | 输出，高有效 | U910 Q；控制现有背靠背放电开关 Q504 许可 |
| `BOOST_EN` | 输出，高有效 | U915 Schmitt buffer 输出；延迟后使能 TPS61088 |

J910 pin 3 接 GND。R914/R915 分别把 `CELL_CONFIG_VALID` 和 `MANUAL_ARM_REQ` 默认拉低，防止接口悬空。

## 2. ARM 锁存

U910 = SN74LVC1G74DCT：

- D 接 `CELL_3V3`，PRE_N 接 `CELL_3V3`。
- CLK 接 `MANUAL_ARM_REQ`。
- CLR_N 接 `ARM_PERMIT`。
- Q 输出 `DISCHARGE_ARM`；Q_N 不使用。
- 当任一许可输入失效，`ARM_PERMIT` 变低，异步清除 Q；R913 另将 `DISCHARGE_ARM` 下拉至 GND。

这是一只**上升沿触发**的 D 触发器，不是电平使能门。若故障期间 `MANUAL_ARM_REQ` 一直保持高，故障解除只会释放 CLR_N，不会产生新的 CLK 上升沿，因此不会自动重新闭合放电开关。必须先将 ARM 请求拉低，再发出新的上升沿。

U911/U912/U913 三只 SN74LVC1G08 形成两级安全条件 AND。BQ76905 的 `CELL_MON_ALERT_L` 已在监测页通过 10 kΩ 上拉到 REGOUT；`PACK_UV_OK` 使用现有组端 UVLO 输出。任何输入开路/掉电时，必须由其上游电路保持无效状态；该页不允许 MCU 直接旁路 ARM_PERMIT。

## 3. 监测电源有效

U914 = TPS3839G33DQNT，VDD 接 `CELL_3V3`（BQ76905 REGOUT），RESET 输出 `CELL_MON_PG`。

- 监控门限：3.08 V 标称。
- RESET 为低有效；REGOUT 上电并超过门限后，经过约 200 ms 标称复位释放延迟才输出高。
- 欠压时立即将 `CELL_MON_PG` 拉低，U910 异步清除。

`CELL_MON_PG` 只证明 REGOUT 电源达到监督门限，不证明 BQ76905 已完成 4S 寄存器配置；后者由独立 `CELL_CONFIG_VALID` 和 `CELL_MON_ALERT_L` 覆盖。U914 的门限误差、迟滞和全温释放时间仍须按数据表和实物测量确认。

## 4. BOOST_EN 延迟与快速关断

U910 的 Q 立即产生 `DISCHARGE_ARM`。R910=100 kΩ、C910=1 µF、R911=1 MΩ 形成延迟节点 `BOOST_EN_DELAY`；U915 SN74LVC1G17DBVR 将慢边沿整形成 `BOOST_EN`。

- RC 节点最终电压约为 REGOUT 的 10/11，足以跨过 Schmitt 输入阈值；实际延迟由阈值、R/C 容差和温度决定，**约 60 ms 仅为首轮估计**，不能作为保证时序。
- D910=1N4148W，阳极接 `BOOST_EN_DELAY`，阴极接 `DISCHARGE_ARM`。当 U910 Q 被清除时，D910 为 C910 提供快速放电通路，使 BOOST_EN 尽快拉低。
- R912 将 `BOOST_EN` 默认下拉；R913 将 `DISCHARGE_ARM` 默认下拉。

该延迟用于先接通 PACK_4S→VIN_BOOST 物理路径，再启动 Boost，避免两个开关同时动作。必须用示波器实测 Q504 栅极、`DISCHARGE_ARM`、`BOOST_EN` 和 VIN_BOOST 的先后关系。

## 5. 明确尚未实现的闭环

本页**尚未实现**以下功能，不能把它们视为完成：

1. `BOOST_READY` 反馈资格与启动超时：若 ARM 后 Boost 未在限定时间内进入有效输出窗口，目前还没有定时器自动清除 ARM。
2. TPS25947 eFuse PG 与 `BACKUP_READY` 资格。
3. TPS2121 OV2 残压否决、主备优先级和反灌控制。
4. 故障锁存的诊断记录与人工复位接口（当前通过新的 ARM 边沿实现重新武装，但没有独立故障码寄存器）。
5. `CELL_CONFIG_VALID` 的主控固件实现和 BQ76905 host watchdog 故障注入。

因此，主备 MUX 页完成前，不能宣称已经具备完整的自动备电接管和启动失败恢复能力。

## 6. 台架验收

| 测试 | 操作 | 通过条件 |
|---|---|---|
| ILK-001 | PACK_UV_OK 从高变低 | U910 Q 异步清零；DISCHARGE_ARM、BOOST_EN 均低 |
| ILK-002 | CELL_MON_PG 欠压/掉电 | U914 RESET 拉低并清除 ARM；REGOUT 恢复后需重新 ARM |
| ILK-003 | CELL_CONFIG_VALID 拉低 | ARM 清除；接口开路时 R914 保持低 |
| ILK-004 | CELL_MON_ALERT_L 拉低 | ARM 清除；故障解除不得自动重新 ARM |
| ILK-005 | 故障期间保持 MANUAL_ARM_REQ 高，随后恢复所有许可 | 不得自动 ARM；先低后新的上升沿才可置位 |
| ILK-006 | DISCHARGE_ARM 上升沿 | BOOST_EN 在实测 RC/Schmitt 延迟后上升，目标约 40–100 ms |
| ILK-007 | ARM_PERMIT 撤销 | BOOST_EN 通过 D910 快速下降；测量从 Q 清零到 EN 低的延迟，目标小于 1 ms |
| ILK-008 | REGOUT 冷启动和慢斜坡 | CELL_MON_PG 不得在门限和复位延迟前有效 |
| ILK-009 | 所有辅助电源掉电、接口拔除 | 放电开关默认关闭；无意外重启 |

最终放行还需把 `BOOST_READY` 启动超时和 `BACKUP_READY` MUX 资格接入，并完成跨页 ERC/netlist 与 12 W / 1.2 s 联合仿真。
