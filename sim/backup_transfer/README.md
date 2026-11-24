# BACKUP_READY 专项验证

状态：BACKUP_READY 行为契约与残压反例验证；**不是完整 TPS25947/TPS2121 电路仿真，也不是硬件放行。**

## 文件

- **backup_ready_supervisor.py**：消费 CELL_PERMIT、PACK_UV_OK、Boost 输入/输出窗口、eFuse 输入/逻辑电源有效性、变体状态脚、通路证明年龄和 ARM 请求的离散状态机。
- **test_backup_ready_supervisor.py**：18 项状态机回归，覆盖默认禁止、资格项、470A/474L 状态脚、开漏上拉失效、复位时 ARM 高电平、故障锁存、重新武装和 proof age 超时。
- **backup_ready_residual_fault.cir**：ngspice 行为级瞬态网表，比较 100µF/470µF 残压、限流故障电流、PG 状态、锁存的通路证明，以及健康/故障两种备源的 MUX 接管。
- **backup_ready_spice_parameters.json**：筛选参数、TI 数据手册阈值和模型限制。
- **check_spice_results.py**：检查 ngspice wrdata CSV 的 14 项断言，包括两种残压电容的限流反例、健康备源成功接管和故障备源被否决。
- **run_backup_ready_spice.sh**：运行 ngspice，保存 RAW、LOG、CSV、网表、参数、摘要和 SHA256。
- **hardware/kicad/backup-ready-interface.md**：U902/U901 变体语义、引脚、OV2 极性与门限、状态机和接口契约。

## 本地复跑

- python3 -B sim/backup_transfer/check_residual_input.py
- python3 -B sim/backup_transfer/check_ov2_bias.py
- python3 -m unittest discover -s sim/backup_transfer -p 'test_*.py' -v
- bash sim/backup_transfer/run_backup_ready_spice.sh artifacts/backup-ready-spice

SPICE 需要安装 ngspice。脚本在缺少 ngspice 时会明确失败，不会生成或伪造 RAW/LOG。CI 工作流会安装 ngspice 并上传仿真证据。

## BACKUP_READY 条件

BACKUP_READY = ARM_LATCHED
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

OV2_INHIBIT = !BACKUP_READY

TPS259470ARPW 使用 AUXOFF/FLT；TPS259474LRPW 使用 PG/PGTH。两种状态接口均要求独立确认 U902 IN 供电和状态逻辑上拉电源有效。状态脚不能替代 PATH_PROOF_OK：残压 COUT 可能维持 AUXOFF/FLT 或 PG 的“正常”读数。

TPS2121 OV2 是 IN2 的 active-low enable supervisor：OV2 ≥ 1.10V（VREF rising max）保证进入禁止区；OV2 < 0.99V（VREF falling min）才进入允许区。实际设计必须在这两个门限外另留容差和噪声裕量。

## 状态机与 proof freshness

本分支修复既有 p0-efuse-qualification 分支中 arm_low_seen 初值为 True 的问题。上电时 ARM 高、随后安全许可恢复但 ARM 不发生低→高边沿，旧模型可能错误 READY。本分支复位默认 False，并要求先采样 ARM 低，再接受新的上升沿。

proof freshness 通过 path_proof_age_s <= path_proof_max_age_s 判断；缺失、负数、非有限值、无效最大期限和过期均 fail-closed。单元测试中的 100ms 仅是测试夹具，不是已批准的实际刷新周期。最大有效期必须根据整机允许的故障检测延迟和证明负载占空比确定。

## SPICE 筛选假设

- Boost 输出：12V；eFuse 断开：100µs；IN2 泄放：10kΩ。
- 输出电容：100µF、470µF；健康通路电阻：45mΩ。
- 通路证明脉冲：1A / 200µs；筛选压降上限 100mV；输出下限 11.8V。
- PGTH 分压比：10.5%（仅为筛选值）；PGTH 阈值采用 TI 规格角。
- 主源在 1.5ms 掉电；MUX 采用理想化逻辑开关；负载用 12Ω 和 100µF 表示。

在 10kΩ 泄放、eFuse 断开约 1ms、1A / 200µs 证明脉冲和 100mV 压降门槛下，简化 RC 估算的 COUT 识别上限约 2.0mF。该数值仅是筛选边界，不是硬件保证。证明脉冲必须根据最终 COUT 最大值和 eFuse ILIM 最小值重新核算。

## 证据边界

Python 单元测试是离散行为模型；.cir 是理想开关/行为逻辑 SPICE，不是芯片级模型。ngspice 仿真成功也不能代替 KiCad ERC、真实器件宏模型、台架测试或整机 12W / 1.2s EOL 验收。
