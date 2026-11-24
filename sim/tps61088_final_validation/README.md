# TPS61088 功率级最终验证包

状态：**验证执行框架已建立；最终 SPICE 矩阵尚未运行；不批准 RILIM 或 L1 电感。**

本目录从共同基线独立开发，只选择性提取旧审计分支中的频率分析器、原始日志元数据、测试网表和 EOL 预算程序。没有整体合并两个旧审计分支。

## 1. 版本与来源

- 仓库：tortletortle/supercap-ups
- 本分支：specialist/tps61088-final-verification
- 共同基线：power-stage-integration @ 360508c08f23f63cdd74fba7e0c201b0907d3825
- 选择性提取来源：
  - tps61088-final-device-audit @ ee46090e5c262a77625fac1f2ffc3ad4588bd8dd
  - v1.4-audit-frequency-ilim @ f3c25269ac1703a2c0d6d7acb59db0dfcdce9d5a
- 当前集成基线的 TPS61088_LT.LIB 与来源分支模型文本逐字节相同；SHA-256：418466fbd205f9e9ec487bee1d9c1ada48858ff49eef67767e84706966fa1795。
- 本分支不修改 main 或 power-stage-integration，不合并其他分支。

## 2. 现有 50 ns / 25 ns 证据

来源：旧审计分支已经存在的 LTspice 运行记录，不是本分支重新运行的结果。

环境记录：
- Windows 11
- LTspice 26.1.1.0
- Python 3.12.10
- Gear
- 仿真终止时间 26 ms
- 两次运行使用同一 TPS61088 宏模型和相同电气参数；最大步长分别为 50 ns、25 ns。

RAW 本体没有提交到 GitHub，只有本地清单、RAW header、LOG、环境记录和旧分析 JSON。清单中的 SHA-256 是本地登记值，本轮没有拿到 RAW 字节，因此尚不能独立复算哈希。

| 项目 | 50 ns | 25 ns |
|---|---:|---:|
| RAW 大小 | 555,189,092 B | 654,022,700 B |
| RAW SHA-256 | b817d10d13cfc83027764796eafcf4e3bb8b0b05fbb420c68879417f051bc719 | 2d5b2ddbb5a9c27a25322143a426741cfbe1e01623c9ceeb9b7940481ab7e552 |
| LTspice 退出码 | 0 | 0 |
| 日志频率 | 442.336492 kHz | 441.757819 kHz |
| 平均 VOUT | 11.9987437 V | 11.9987351 V |
| 稳态电感峰值 | 2.80766 A | 2.77228 A |
| 启动期间电感峰值 | 2.86497 A | 2.84920 A |
| 模型测得效率 | 98.882% | 98.871% |

旧分析器的周期完整性不合格：

| 旧分析器计数 | 50 ns | 25 ns |
|---|---:|---:|
| 候选周期 | 884 | 883 |
| 完整有效周期 | 347 | 748 |
| 右删失周期 | 1 | 1 |
| 无效周期 | 536 | 134 |

旧版比较 JSON 报告频率差约 -0.578673 kHz（约 -0.1308%）、周期中位数差 -6.561 ns、输入事件到 U5 TOFF 中位数差 +0.776 ns。由于旧周期统计包含大量无效周期，这些数字只能用于定位分析问题，不能作为最终收敛证据。此前提到的 3.598 ns 没有得到该比较 JSON 支持，不应继续引用。

## 3. pairing-v2 与 12.5 ns 门控

已选择性移入：
- scripts/ltspice_raw.py
- scripts/analyze_fsw_internal.py
- scripts/run_fsw_internal_pairing_v2.py
- 对应单元测试
- 原始文件本地清单

pairing-v2 runner 对当前两份已登记 RAW 使用固定哈希和周期完整性检查。预期 50 ns 为 883 个完整有效周期、1 个右删失、0 个无效；25 ns 为 882 个完整有效周期、1 个右删失、0 个无效。这是验收目标，不是已取得的 pairing-v2 实际结果。

gate_and_screen.py 使用以下规则：
1. pairing-v2 报告状态、全部检查和 50/25 电气参数一致性必须通过，否则停止。
2. 50/25 频率相对差大于 0.1%，或任一关键事件中位数漂移大于 1 ns，才要求运行 12.5 ns。
3. 如果不需要 12.5 ns，可进入功率级矩阵。
4. 如果需要 12.5 ns，必须先运行并分析；12.5 ns 与 25 ns 比较需满足：无无效周期、周期完整率至少 99.5%、事件完整性/唯一性/CSV 一致性通过、频率相对差小于 0.05%、全部关键事件中位数漂移小于 0.5 ns。
5. 12.5 ns 未通过时，禁止启动 RILIM 和动态矩阵；下一步应调查或考虑 6.25 ns。

12.5 ns 网表已保留在 diagnostics/，尚无对应 RAW、LOG 或 pairing-v2 分析结果。

## 4. 12 组 RILIM 矩阵

generate_rilim_matrix.py 生成 6 个 RILIM × 2 个输入端点，共 12 份网表：

- RILIM：100、160、174、180、200、220 kΩ
- VIN：7.0 V、9.4 V
- 最大步长：25 ns
- 总仿真时间：26 ms
- 1 A 正常负载基线；15–16 ms 插入 3 A、1 ms 有界过载脉冲，然后恢复 1 A。

保存并测量：
- I(L1) 峰值、稳态峰值和 RMS
- V(X1:CLIMT)：宏模型内部编程限流阈值
- V(X1:ISENSE_A)：宏模型内部电流检测等效信号
- 过载期间的开关电流检测值、限流阈值、限流余量
- VOUT 最小值、纹波、过载后恢复
- 输入/输出功率、模型效率、开关频率和启动时间

注意：CLIMT 是模型阈值；若 ISENSE_A 没有到达阈值，不能宣称发生了限流。宏模型中的限流路径是行为模型，不包含芯片全温工艺分布。12 份网表目前只是已生成规则的测试输入，没有 SPICE 结果。

## 5. 动态与输入扫描

generate_dynamic_cases.py 生成 24 份额外网表：

- 12 份 VIN 扫描：7.0、7.5、8.0、8.5、9.0、9.4 V × RILIM 160/174 kΩ，1 A 负载。
- 12 份动态应力：
  - VIN 7.0/9.4 V × RILIM 160/174 kΩ × 负载阶跃、3 A/1 ms 过载、0.1 Ω/1 ms 输出短路。
- 动态网表同样记录 CLIMT、ISENSE_A、电感峰值/RMS、输入电流和输出恢复。

这 24 份也尚未运行。0.1 Ω 输出短路包含输出电容放电，不能等同于真实电子负载短路台架。

## 6. RILIM 与电流预算筛查

FPWM 典型公式：

    I_LIM,typ = 1.19e6 / R_ILIM - 1.6

保守工程筛查暂按 RILIM ±1%，并从典型公式减去 1.3 A。电流需求筛查使用 VIN=7 V、VOUT=12.6 V、IOUT=1 A、效率 75%、Lmin=2.31 µH、FSW=350 kHz。得到峰值约 4.324 A、RMS 约 2.645 A。

| RILIM | 典型限流值 | 最低限流筛查值 | 峰值电流余量 | 结论 |
|---:|---:|---:|---:|---|
| 100 kΩ | 10.300 A | 8.882 A | +4.558 A | 限流偏高，存在电感饱和风险 |
| 160 kΩ | 5.838 A | 4.464 A | +0.140 A（3.2%） | 六个候选中最好，但余量太低，不批准 |
| 174 kΩ | 5.239 A | 3.871 A | -0.453 A | 不满足筛查 |
| 180 kΩ | 5.011 A | 3.646 A | -0.678 A | 不满足筛查 |
| 200 kΩ | 4.350 A | 2.991 A | -1.333 A | 不满足筛查 |
| 220 kΩ | 3.809 A | 2.456 A | -1.868 A | 不满足筛查 |

完整 6 行见 data/rilim_analytical_screen.csv。gate_and_screen.py 还会生成 5,184 行参数敏感性表，覆盖 VIN、效率假设、电感量、频率、温度和 RILIM。热态 DCR 使用铜电阻温度系数 0.393%/°C 的一阶估算；这不是磁芯损耗、热反馈或器件温度模型。

重要边界：TI 电气特性表中的限流 min/max 测试条件为 VIN 2.7–5.5 V，不能把该表格直接当作 7–9.4 V 下的保证限流窗口。上述 1.3 A 差值用于工程筛查，不构成全输入范围保证。

## 7. EOL 效率假设与电感判定

4S×20F EOL 能量预算使用 85% 恒定 Boost 效率假设。已有预算脚本/CSV 给出：
- 输入路径 100 mΩ：85% 时保持约 1.374803 s；达到 1.2 s 所需最低效率约 80.121%。
- 输入路径 150 mΩ：85% 时保持约 1.215724 s；最低效率约 84.559%，仅约 15.7 ms 裕量。

这只是恒定效率能量预算，不是器件级效率曲线，也不是连续 1.2 s 整机 SPICE 仿真。

旧 50/25 ns LTspice 日志的 98.9% 效率来自 TI 宏模型与固定 26 mΩ 电感 DCR。模型没有充分证明实际磁芯损耗、温升、PCB 损耗和热态效率，不能用它替代 85% EOL 假设或实测。

现有 L1 候选 CENKER CKST0603-3.3uH/M：
- 3.3 µH ±20%
- DCR 23 mΩ typ / 26 mΩ max
- Isat 9.5 A typ
- Irms 6.0 A typ

Isat 和 Irms 没有给出保证最小值，因此不能据此证明电感在限流最大角落不会饱和或过热。L1 当前不批准。160 kΩ 也只是最值得继续验证的候选，不是冻结值。需要供应商提供保证 Isat,min、Irms/温升条件和全温电感曲线，或更换有明确保证参数的电感后重新验证。

## 8. Windows 本机执行

安装依赖：

    py -3 -m pip install -r sim/tps61088_final_validation/requirements.txt

使用清单中登记的原始 RAW 路径运行（如文件位置改变，只需修改参数）：

    py -3 sim/tps61088_final_validation/scripts/run_gated_audit.py --raw-50 "C:\Users\tortl\Documents\Codex\2026-11-20\c-users-tortl-downloads-dc-v1\work\v14-internal-native\freq_vin7_rfsw324k_internal_probe_50ns\freq_vin7_rfsw324k_internal_probe_50ns.raw" --raw-25 "C:\Users\tortl\Documents\Codex\2026-11-20\c-users-tortl-downloads-dc-v1\work\v14-internal-native\freq_vin7_rfsw324k_internal_probe_25ns\freq_vin7_rfsw324k_internal_probe_25ns.raw" --ltspice "C:\Users\tortl\AppData\Local\Programs\ADI\LTspice\LTspice.exe"

只执行 pairing-v2 和 12.5 ns 决策：

    py -3 sim/tps61088_final_validation/scripts/run_gated_audit.py --raw-50 "<50ns.raw>" --raw-25 "<25ns.raw>" --stop-after-pairing

如果 12.5 ns 被要求，执行到频率收敛验收后停止：

    py -3 sim/tps61088_final_validation/scripts/run_gated_audit.py --raw-50 "<50ns.raw>" --raw-25 "<25ns.raw>" --stop-after-12p5

完整执行会在频率门控通过后运行 12 组 RILIM、12 组 VIN 扫描和 12 组动态应力。所有文件隔离保存到 results/final_device_audit/<timestamp>/，包含执行网表、模型副本、RAW、LOG、测量 CSV、会话 JSON 和 SHA256SUMS.txt。不会覆盖已有输入网表。

## 9. 证据等级与放行状态

| 项目 | 当前状态 |
|---|---|
| 50 ns / 25 ns LTspice | 旧分支已有运行日志和本地 RAW 清单；本轮未重新读取 RAW |
| pairing-v2 | 代码与测试已移入本分支；实际 RAW 重分析待本机运行 |
| 12.5 ns | 网表已准备；是否运行由 pairing-v2 门控决定；尚无 RAW/LOG |
| RILIM 12 组 | 网表生成器与解析字段已建立；尚未运行 |
| VIN / 动态 24 组 | 网表生成器与验收字段已建立；尚未运行 |
| EOL 效率预算 | 4S×20F 恒定效率模型已有结果；不是器件效率测量 |
| 单元测试 | 由本分支 GitHub Actions 验证 |
| SPICE 矩阵 | 未完成 |
| 真实器件效率 / 温升 | 未测试 |
| 电感批准 | 不批准 |
| 85% 效率假设 | 预算暂用，尚未由实测确认 |
| 连续 1.2 s 整机仿真 | 不在本地 26 ms 功率级测试范围内，尚不能宣称完成 |

本分支目标是交付可复跑的最终验证流程与证据门控，不把脚本、网表、宏模型或能量预算冒充最终硬件验收。


## 10. 本分支自动化检查

GitHub Actions：运行 #45303608253，结论 SUCCESS。

已通过：
- Python 脚本语法编译。
- pairing-v2 与分析器相关单元测试。
- 新增的门控、限流筛查、周期换算和网表结构测试。
- 12 份 RILIM 网表生成与数量检查。
- 24 份动态/VIN 扫描网表生成与数量检查。
- 5,184 行参数敏感性表生成。
- 4S×20F EOL 效率预算脚本执行。

这次 CI 不包含 LTspice，因此不能作为 12.5 ns、12 组 RILIM、24 组动态测试的 SPICE 通过证据。
