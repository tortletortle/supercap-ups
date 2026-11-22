# TPS61088 2S 低输入电压验证矩阵

状态：**仅完成测试输入准备；7 份固定 VIN 网表和 2 份 EOL pack-coupled 网表均未运行。**

## 目的

验证 2S 超级电容候选在低输入电压区间能否由 TPS61088 稳定提供 12 V / 1 A。架构模型在 2S25F LR EOL、92% 固定 Boost 效率假设下，1.2 s 时包端电压约 3.604 V、输入电流约 3.655 A；2S30F HP J306VYJ22 EOL 在 1.2 s 时包端电压约 2.873 V、输入电流约 4.585 A。因此 2.8/3.0 V 是 30F 低 ESR 料号的临界测试点，3.6 V 是 25F LR 的关键对照点，4.8 V 对应初始充电状态。

TI 数据手册给出 TPS61088 的 2.7–12 V 输入范围。TI PMP9778 页面特性摘要列出 2.7–4.2 V 输入与 12 V / 1.5 A 输出，但同页参数表的 VIN 最小/最大值为 3.0/4.4 V，页面口径不完全一致。因此 2.8 V 是本项目接近器件输入下限的压力测试点，3.0 V 是参考设计参数表下限附近的对照点；该参考设计只说明低压 TPS61088 拓扑有先例，**不代表本项目的 3.3 µH 电感、补偿、RFSW、布局和效率已经验证**。

## 测试矩阵

| 顺序 | VIN 源电压 | 输出目标 | 用途 |
|---:|---:|---:|---|
| 1 | 2.8 V | 12 V / 1 A | J306VYJ22 EOL 端电压附近，接近输入下限 |
| 2 | 3.0 V | 12 V / 1 A | 低压临界点，对照 TI PMP9778 输入下限 |
| 3 | 3.2 V | 12 V / 1 A | 低输入边界压力点 |
| 4 | 3.6 V | 12 V / 1 A | 对照 2S25F LR EOL 1.2 s 模型点 |
| 5 | 4.0 V | 12 V / 1 A | 中间点 |
| 6 | 4.4 V | 12 V / 1 A | 2S 运行区间上段 |
| 7 | 4.8 V | 12 V / 1 A | 初始充电状态附近 |

所有网表保持同一功率级参数，避免把输入电压变化与器件变化混在一起：

- TPS61088 官方 PSpice transient macro-model；
- L1 = 3.3 µH，DCR = 26 mΩ；
- CIN = 35 µF；
- COUT = 47 µF，ESR = 3 mΩ；
- RFSW = 324 kΩ；这是为保持与 V1.3 BOM 基线可比而暂时固定的值，不代表开关频率已经验收。V1.4 在 VIN=7 V、VOUT=12 V 下测得 442.336 kHz，而 TI 公式理论值为 496.137 kHz，偏差约 −10.84%；FSW 斜坡/延迟路径已有诊断证据，但唯一根因尚未闭环。低压各点必须以本轮实测 FSW 为准，不按电阻标称值推断频率，也不在本轮擅自换阻值；
- RILIM = 100 kΩ；这是用于观察低输入电压能力的高限流基线。不要直接沿用 4S 工况筛出的 174 kΩ 候选，因为 2S 输入电流更高，必须先确认限流裕量；
- MODE 接地（FPWM）；
- COMP = 21.5 kΩ / 13 nF / 100 pF；
- 反馈 = 1.076 MΩ / 120 kΩ；
- 负载启动后为 12 V / 1 A。

模型文件引用仓库 V1.3 已审计的 TPS61088 官方宏模型，不复制或修改模型文件。

## Continuous 1.2 s hold-up integration (macro-model calibrated)

The 40 ms EOL checkpoint decks above are local startup tests only. They do not establish that the converter can remain in regulation continuously for the complete 1.2 s backup interval.

To close that gap without pretending that a multi-million-cycle switching transient has already been run, the repository now includes a separate time-domain behavioral integration. It consumes the seven-point fixed-VIN LTspice result summary, uses the measured TPS61088 macro-model efficiency versus actual converter VIN, and integrates the EOL capacitor OCV under a 12 W constant output load.

The integration assumes the 12 W output load is already being served and the converter remains regulated; it models the storage-side DC trajectory, not output-bus switchover dynamics or a switching waveform. The integration includes:
- EOL equivalent capacitance and DC ESR for each 2S candidate;
- the same 2 mΩ series input-path resistance used in the fixed-VIN decks;
- midpoint integration of capacitor voltage and a numerical operating-point solve at each step;
- piecewise-linear efficiency interpolation only inside the measured VIN range;
- no efficiency extrapolation if the pack voltage falls outside the seven-point calibration;
- energy accounting for capacitor energy removed, converter input energy, pack ESR loss and path loss;
- an interpolated steady-state inductor peak-current estimate, clearly separated from startup/transient peak current.

It evaluates J306VYJ23 (44 mΩ), J306VYJ22 (40 mΩ), and J256UYJ21 (25 mΩ). A 1.2 s PASS means only that this macro-model-calibrated behavioral model can find a valid 12 W operating point through the endpoint. It is not a continuous switching-level run or hardware qualification. All seven fixed-VIN cases must be screen_pass with matching deck/log/raw/model hashes before the efficiency map is accepted; a failed or missing case blocks the integration rather than being silently interpolated.

After running and analyzing all seven fixed-VIN decks, run:

~~~powershell
py -3 .\simulate_calibrated_hold_up.py --analysis-csv .\results\<run_timestamp>\analysis_summary.csv
~~~

The script writes calibrated_hold_up_summary.csv and calibrated_hold_up_report.md beside the input analysis CSV. Preserve the source analysis CSV and its SHA-256 with the report. If the calibrated trajectory leaves the measured VIN range before 1.2 s, the result is NOT VERIFIED; do not extrapolate efficiency or call it a physical cutoff prediction.

## Prebiased 12 V output-bus transfer matrix

The system architecture gives the main supply priority and uses the supercapacitor Boost stage as backup. During a real switchover, the 12 V output bus is already energized and the load does not disappear while the backup converter starts. A cold-start deck with COUT=0 and a load gated by EN does not represent that event.

A separate nine-case transfer matrix now models this boundary:
- three 2S candidates: J306VYJ23 (44 mΩ), J306VYJ22 (40 mΩ), and J256UYJ21 (25 mΩ);
- EOL capacitance and EOL DC ESR, but the pack starts fully charged at 4.8 V;
- output capacitor COUT=47 µF prebiased to 12 V;
- 1 A constant-current load remains connected throughout the transfer;
- backup EN delay sensitivity points of 20, 50, and 100 µs, followed by a 1 µs EN ramp;
- 2 mΩ input path, same TPS61088 macro-model and switching BOM baseline.

The three enable delays are sensitivity points, not claims about the actual controller response. The decks record output voltage immediately before enable, the average output voltage during the final 1 µs before enable, the minimum during the first 5 ms, and the global minimum over 40 ms. They also record steady-state regulation, ripple, input current, inductor current and observed FSW.

No minimum output-voltage acceptance limit has been invented. The analyzer therefore labels a complete transfer run as transfer_review_required, not screen_pass, even if the later steady-state window regulates correctly. The minimum-output trace must be compared with the system's actual load brownout/reset tolerance before the transfer can be accepted.

Generate, run and analyze:

~~~powershell
py -3 .\generate_prebiased_transfer_decks.py
powershell -ExecutionPolicy Bypass -File .\run_low_vin_matrix.ps1 -LtspiceExe "C:\Program Files\ADI\LTspice\LTspice.exe" -NetlistSubdir transfer
py -3 .\analyze_low_vin_results.py --run-dir .\results\<run_timestamp>
~~~

This 40 ms test covers initial switchover and recovery only. It does not replace the continuous 1.2 s storage-side integration or the separate EOL local operating-point check.

## EOL pack-coupled checkpoint decks

七点固定 VIN 矩阵把输入端视为理想电压源，适合隔离 Boost 在不同 VIN 下的启动和稳态表现，但不包含超级电容组的 ESR 压降。为补上这一缺口，新增两个 1.2 s EOL 局部启动窗口：

| 候选 | EOL 等效电容 | EOL 包 DC ESR | 行为模型预期 OCV | 预期带载端电压 | 预期输入电流 |
|---|---:|---:|---:|---:|---:|
| 2S30F HP J306VYJ22（40 mΩ） | 10.5 F | 320 mΩ | 4.341 V | 2.873 V | 4.585 A |
| 2S25F LR J256UYJ21（25 mΩ） | 8.75 F | 200 mΩ | 4.335 V | 3.604 V | 3.655 A |

这些 OCV、带载端电压和电流来自同一份恒功率 + ESR 行为模型：12 W 输出、92% 固定 Boost 效率、99% 路径效率。它们是生成 LTspice 初始条件的模型预测，不是器件级仿真结果。

每份网表显式包含 EOL 等效电容、包 DC ESR、2 mΩ 输入路径电阻和输入电容；输入电容按 checkpoint OCV 预充电，避免人为制造上电浪涌。当前这两份网表的 COUT 未预偏置，且 BLOAD 由 EN 控制，因此它们是“EOL 状态下冷启动”的压力测试，不是主电源优先系统的预偏置输出切换测试。仿真覆盖 40 ms 局部启动窗口，观察在“已经放电 1.2 s”的储能状态下，实际宏模型输入电流会造成多大 ESR 压降，以及输出能否重新建立。真正的主备切换还需另行验证：输出母线应预偏置到 12 V、负载在切换期间保持连接，并显式扫描实际备电使能延迟。

**重要边界：这不是从满电开始连续运行 1.2 s 的开关级仿真。** 它只验证行为模型给出的 1.2 s EOL 状态附近的局部启动。实际宏模型效率和输入电流可能不同于 92% 行为模型，因此应比较实测 pack terminal、VIN、IIN 与预期值的偏差，不应强行要求数值完全相等。注意：预期 OCV/端电压/电流是 t=1.2 s 的状态；分析窗口在局部仿真 35–37 ms，期间电容会继续放电。分析器同时输出 pack OCV 的窗口均值及其相对初始 checkpoint 的变化量；pack terminal 与 t=1.2 s 参考值的差值包含这段额外放电，不能直接解释为模型误差。

生成与运行：

~~~powershell
py -3 .\generate_eol_checkpoint_decks.py
powershell -ExecutionPolicy Bypass -File .\run_low_vin_matrix.ps1 -LtspiceExe "C:\Program Files\ADI\LTspice\LTspice.exe" -NetlistSubdir checkpoints
~~~

同样使用 analyze_low_vin_results.py 分析该次 results/run_timestamp。运行脚本会从 checkpoints/manifest.csv 读取架构、checkpoint 时间和预期 pack 状态，并写入 run_manifest.csv；分析器会额外要求 pack_ocv_avg、pack_terminal_avg、pack_input_avg、ppack、pack_esr_loss_w、path_loss_w 和 eff_pack 等测量项，并输出实际值与行为模型预测的差异。

## 运行方式

使用 Windows LTspice 26.1.1。推荐通过 PowerShell 批处理脚本运行，脚本会按 manifest.csv 顺序逐个调用 LTspice、归档每份输入网表与 LOG/RAW，并记录退出码及 SHA-256：

~~~powershell
powershell -ExecutionPolicy Bypass -File .\run_low_vin_matrix.ps1 -LtspiceExe "C:\Program Files\ADI\LTspice\LTspice.exe"
~~~

如果 LTspice 安装在用户目录，请把 -LtspiceExe 改为实际的 LTspice.exe 路径。也可以只运行一个测试点，例如：

~~~powershell
powershell -ExecutionPolicy Bypass -File .\run_low_vin_matrix.ps1 -LtspiceExe "C:\Program Files\ADI\LTspice\LTspice.exe" -Case tps61088_vin_3p6v
~~~

脚本使用 LTspice 的 -b batch 模式。官方命令行说明见 [Analog Devices LTspice Quick Reference](https://www.analog.com/media/en/news-marketing-collateral/solutions-bulletins-brochures/ltspice-keyboard-shortcuts.pdf)。每次运行会创建独立的 results/run_timestamp 目录，不覆盖旧结果；脚本状态只表示进程与文件收集情况，不代表电气验收通过。大型 RAW 文件默认由本目录 .gitignore 排除，避免意外提交超大二进制文件。

每份运行都应保留原始 LOG/RAW、退出状态、模型哈希、网表哈希和 LTspice 版本；不要覆盖先前结果。

运行结束后，用分析器自动读取 manifest、LOG/RAW 与输入文件哈希：

~~~powershell
py -3 .\analyze_low_vin_results.py --run-dir .\results\<run_timestamp>
~~~

分析器会生成 analysis_summary.csv 和 analysis_report.md，逐点区分仿真未完成、测量失败、证据哈希不匹配、有限电气筛查通过/失败。它不会把进程退出码 0 当成电气通过，也不会给 FSW 设未经批准的目标值。只有全部文件哈希匹配、求解完成、必需 .meas 齐全、时序正确且输出电压/电流/纹波满足筛查范围，才标记 screen_pass；这仍然只是宏模型筛查，不是硬件资格或 BOM 放行。

仿真时长 40 ms，最大步长 50 ns；稳态统计窗口为 35–37 ms。网表还请求测量 t98、6001/6101 次 SW=10 V 上升沿及两者计算的开关频率。若某个 .meas 返回 FAIL，保留原始失败，不得通过改边沿序号或阈值把它改写成通过。

## 最小验收

每个输入点分别记录：

1. 求解器是否完整运行至 40 ms；区分 fatal error、time-step-too-small、二极管警告和单项测量失败。
2. t98、sw_t6001、sw_t6101 是否满足 t98 < sw_t6001 < sw_t6101 < 40 ms。
3. 35–37 ms 的平均 VOUT、VOUT 最小/最大值、峰峰纹波、平均输出电流。
4. 平均输入电流、输入功率、输出功率和宏模型窗口功率比。
5. 电感峰值电流及启动峰值；对照 CENKER CKST0603-3.3uH/M 的 Isat 9.5 A typical、Irms 6 A typical 时，必须注明这些是数据手册典型值，不能当作保证值，也不能用线性电感模型证明未饱和。
6. 记录是否出现输出塌陷、明显限流、启动失败或稳态振荡。

暂定筛查目标：稳态平均输出电压 11.9–12.1 V、平均输出电流 0.98–1.02 A、纹波不超过 100 mVpp。任何单项不满足都应保留原始波形并分析原因，不要只看效率数值。

## 证据边界

- 当前仓库 V1.3 的器件级实测仿真范围是 7–9.4 V；固定 VIN 矩阵把范围扩展到 2.8–4.8 V，但生成网表不等于完成仿真。
- 固定 VIN 网表仍使用理想直流源加 2 mΩ 串联电阻；两份 EOL checkpoint 网表才显式加入 2S 等效电容与 EOL DC ESR。
- 两份 checkpoint 只覆盖 1.2 s EOL 状态附近的 40 ms 冷启动窗口，不是从满电开始的 1.2 s 连续开关级放电仿真，也不是预偏置输出的主备切换仿真。
- 连续 1.2 s 积分器仅模拟储能侧 DC 动态，并假设转换器持续维持 12 W 输出；实际输出母线切换延迟、COUT 暂态和主电源优先路径仍需单独建模。
- 宏模型功率比不是实物效率；没有 PCB 寄生、热态电感饱和、器件分布和真实超级电容端口动态。
- V1.4 已发现 RFSW 频率偏差仍未定位。本矩阵保持 RFSW=324 kΩ 是为了与现有 BOM 基线可比，不表示该频率设定已经放行。
- 七份固定 VIN 网表和两份 EOL checkpoint 网表目前均为 not_run。只有实际 LOG/RAW 和复核结果入库后，才能更新状态。

## 文件

- generate_low_vin_matrix.py：生成矩阵；
- netlists/：七份固定 VIN LTspice 输入网表及 manifest.csv；
- checkpoints/：两份 2S EOL pack-coupled 局部启动网表及 manifest.csv；
- generate_eol_checkpoint_decks.py：从储能行为模型生成 EOL checkpoint 网表；
- generate_prebiased_transfer_decks.py：生成 3 种 2S 料号 × 3 种备电使能延迟的预偏置 12 V 输出切换矩阵；
- transfer/：9 份预偏置输出切换 LTspice 网表及 manifest.csv；
- run_low_vin_matrix.ps1：Windows 批处理运行和证据归档脚本，支持 -NetlistSubdir；
- analyze_low_vin_results.py：LOG/RAW/哈希与电气筛查分析器；
- simulate_calibrated_hold_up.py：基于七点 LTspice 宏模型效率映射的连续 1.2 s 储能行为积分器；
- test_low_vin_matrix.py、test_analyze_low_vin_results.py、test_generate_eol_checkpoint_decks.py、test_generate_prebiased_transfer_decks.py、test_simulate_calibrated_hold_up.py：网表、证据分析、输出切换矩阵和连续保持时间模型回归测试。
