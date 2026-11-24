# BACKUP_READY 专项验证

状态：BACKUP_READY 行为契约与残压反例验证；**不是完整 TPS25947/TPS2121 电路仿真，也不是硬件放行。**

## 文件

- **backup_ready_supervisor.py**：消费 CELL_PERMIT、PACK_UV_OK、Boost 输入/输出窗口、eFuse 变体状态、通路证明新鲜度和 ARM 请求的离散状态机。
- **test_backup_ready_supervisor.py**：14 项状态机回归，覆盖默认禁止、各资格项、470A/474L 状态脚边界、复位时 ARM 高电平、故障锁存和重新武装。
- **backup_ready_residual_fault.cir**：ngspice 行为级瞬态网表，比较 100 µF/470 µF 残压、PG 状态、独立通路证明，以及电压门槛 MUX 与 READY 门控 MUX。
- **backup_ready_spice_parameters.json**：筛选参数与模型限制。
- **check_spice_results.py**：检查 ngspice wrdata CSV 的 10 项断言。
- **run_backup_ready_spice.sh**：运行 ngspice，保存 RAW、LOG、CSV、网表、参数、摘要和 SHA256。

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
            && EFUSE_STATUS_OK
            && PATH_PROOF_OK
            && PATH_PROOF_FRESH
            && !BACKUP_FAULT_LATCH
            && !STARTUP_TIMEOUT

OV2_INHIBIT = !BACKUP_READY

EFUSE_STATUS_OK 对 TPS259470A 使用受监测电源下的 AUXOFF/FLT 状态，对 TPS259474L 使用受监测电源下的 PG 状态。无论哪个变体，状态脚都不能替代 PATH_PROOF_OK：残压 COUT 可能维持 OUT/PGTH 电压。

## 已有状态机问题

对既有 p0-efuse-qualification 分支的 BackupReadyLatch 做静态复核，发现 arm_low_seen 初值为 True。复现序列：ARM 在上电时保持高、PACK_UV_OK 初始为低，第一次更新不 READY；PACK_UV_OK 恢复而 ARM 仍保持高，模型却置位 READY。中间没有新的 ARM 低→高边沿。这不满足重新武装要求。

本分支将 arm_low_seen 复位初值设为 False，并增加回归：上电高电平不接受；若许可恢复但 ARM 仍高，不得自动置位；必须采样低后再出现新的高电平。

## SPICE 筛选假设

- Boost 输出：12 V；eFuse 断开：100 µs；IN2 泄放：10 kΩ。
- 输出电容：100 µF、470 µF；健康通路电阻：45 mΩ。
- 通路证明脉冲：1 A / 200 µs；筛选压降上限 100 mV；输出下限 11.8 V。
- PGTH 分压比：10.5%（仅为筛选值）；使用 TPS259474L PG 阈值角判断残压能否维持 PG。
- 主源在 1.5 ms 掉电；MUX 采用理想化逻辑开关；负载用 12 Ω 和 100 µF 表示。

在 10 kΩ 泄放、eFuse 断开约 1 ms、1 A / 200 µs 证明脉冲和 100 mV 压降门槛下，粗略可识别的 COUT 上限约 2.0 mF。该数值仅是此简化 RC 模型的筛选边界，不是硬件保证。

这些不是已批准的原理图参数。证明脉冲必须根据最终 COUT 最大值和 eFuse ILIM 最小值重新核算；当前没有 U902/TPS2121/OV2 的 KiCad 实际实例，也没有 vendor macro-model。

## 证据边界

Python 单元测试是离散行为模型；.cir 是理想开关/行为逻辑 SPICE，不是芯片级模型。ngspice 仿真成功也不能代替 KiCad ERC、真实器件宏模型、台架测试或整机 12 W / 1.2 s EOL 验收。
