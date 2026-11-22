# TPS61088 2S 低输入电压验证矩阵

状态：**仅完成测试输入准备；7 份 LTspice 网表均未运行。**

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
- RFSW = 324 kΩ；
- RILIM = 100 kΩ；这是用于观察低输入电压能力的高限流基线。不要直接沿用 4S 工况筛出的 174 kΩ 候选，因为 2S 输入电流更高，必须先确认限流裕量；
- MODE 接地（FPWM）；
- COMP = 21.5 kΩ / 13 nF / 100 pF；
- 反馈 = 1.076 MΩ / 120 kΩ；
- 负载启动后为 12 V / 1 A。

模型文件引用仓库 V1.3 已审计的 TPS61088 官方宏模型，不复制或修改模型文件。

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

- 当前仓库 V1.3 的器件级实测仿真范围是 7–9.4 V；本矩阵把范围扩展到 2.8–4.8 V，但生成网表不等于完成仿真。
- 这些是固定输入电压的短时 Boost 测试，不是 1.2 s 超级电容连续放电仿真。网表使用理想直流源加 2 mΩ 串联电阻，不包含 2S 电容组的动态电压和 EOL ESR；储能动态由前述行为模型单独计算，后续需要把两者结合。
- 宏模型功率比不是实物效率；没有 PCB 寄生、热态电感饱和、器件分布和真实超级电容端口动态。
- V1.4 已发现 RFSW 频率偏差仍未定位。本矩阵保持 RFSW=324 kΩ 是为了与现有 BOM 基线可比，不表示该频率设定已经放行。
- 七份网表目前均为 not_run。只有实际 LOG/RAW 和复核结果入库后，才能更新状态。

## 文件

- generate_low_vin_matrix.py：生成矩阵；
- netlists/：七份 LTspice 输入网表及 manifest.csv；
- run_low_vin_matrix.ps1：Windows 批处理运行和证据归档脚本；
- test_low_vin_matrix.py：生成器回归测试。
