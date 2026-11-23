# 电源级收敛模型与验收矩阵

本目录承接 `hardware/kicad/POWER_STAGE_DESIGN_CONVERGENCE.md` 的工程候选。

## 复跑

```sh
python3 -B sim/design_convergence/power_stage_budget.py
```

`power_stage_budget.py` 仅使用 Python 标准库，计算 4S×20 F Eaton 候选在 EOL 容量、压力 DC ESR、12 W 恒功率负载、输出路径压降、Boost 效率和组端 UVLO/Boost 最低输入边界下的保持时间。脚本含回归断言，防止文档中的关键数值无意漂移。

## 关键输入

- 每颗 EOL 容量 11.2 F：20 F × 80% 初始容差下限 × 70% EOL 因子。
- 每颗 DC ESR 106 mΩ：53 mΩ 初始最大 DC ESR × 2 的压力假设；寿命表给出的是 AC ESR 变化，故必须对样品做 DC 脉冲测量。
- 初始静置组压 9.0 V，硬上限 9.4 V。
- 输出路径 145 mΩ，负载 12 V/1 A。
- Boost 效率扫描 85%/90%，不把宏模型近似无损效率作为实物保证。
- 输入路径目标 ≤100 mΩ 热态；150 mΩ 只作为接近失效的边界点。

## 文件

- `power_stage_budget.py`：解析保持时间与静态保护窗口预算。
- `acceptance_matrix.csv`：仿真、原理图、器件、台架和安全验收矩阵。状态为 MODEL_ONLY / NOT_TESTED / BLOCKED_SPEC 的项目不得视为已放行。

## 重要边界

该模型没有模拟 TPS61088 开关波形、效率曲线、环路、热瞬态、单体失配动态、MOSFET SOA、保护传播延迟或主备 MUX 瞬态。它是参数预算和设计门槛，不替代 LTspice/ngspice、KiCad ERC/netlist、Bode 测量和限能台架测试。
