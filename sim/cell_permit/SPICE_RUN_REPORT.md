# CELL_PERMIT 简化栅极 RC 的 ngspice 运行记录

## 运行信息

- GitHub Actions run：<https://github.com/tortletortle/supercap-ups/actions/runs/45306089301>
- Job：`138150166271`，`validate-cell-permit`
- 分支：`cell-permit-uv-protection`
- 提交：`628fef20740a9a120c68f2af4123ad9acf7b0713`
- 仿真器：ngspice 45.2
- 命令：`ngspice -b gate_turnoff_rc.cir`
- 结果：退出码 0；3011 个瞬态数据点；仿真到 3ms。

## 结果

| 指标 | ngspice | 解析 RC 估算 | 差值 |
|---|---:|---:|---:|
| |VGS| 降到 1.2V | 0.58396ms | 0.58345ms | 0.00051ms |
| |VGS| 降到 0.1V | 1.32196ms | 1.32132ms | 0.00064ms |

末端 3ms 时 `V(GATE)` 约为 -0.3506mV。ngspice 输出与解析一阶 RC 估算一致，验证了等效 RC 方程和数值实现。

## 原始证据

GitHub Actions artifact：`cell-permit-uv-evidence`，对应 run `45306089301`。包含原始 RAW、ASCII DAT、LOG、网表和 SHA256。

| 文件 | 大小 | SHA256 |
|---|---:|---|
| `gate_turnoff_rc.cir` | 503 bytes | `7d1a6e7bc0ed0e499dae65be62377958a45bdce987a105d9862586a5167443d2` |
| `gate_turnoff_rc.raw` | 158757 bytes | `6ac3e49f29b60e5f00f4348f52a362f4de07c0923882c7cda7c59f42e83856b8` |
| `gate_turnoff_rc.dat` | 99363 bytes | `84ca70c3bdbd4f3f16314febf91feb914e006ef937e4397c2bd06a3b8fbbc3a4` |
| `gate_turnoff_rc.log` | 377 bytes | `26e989cf7772cc61029521ea6ed6c47a07e4800d2e9ffcab7f5bb730530a4fed` |

## 证据边界

这次 SPICE 只模拟了一个简化等效 RC：两只 Si7149DP 共栅极，以 `2 × Qg(max)/10V = 29.4nF` 代替非线性 MOSFET 栅极电荷，R501 取 10.1kΩ。它**不是** Si7149DP 厂商瞬态模型，不包含 Miller 平台、VDS/ID 工作点、MOSFET 跨导、AO3400A 关断级、PCB 寄生、实际 PACK 负载电流，也没有模拟 BQ76905 ADC/ALERT。

因此，本次结果只证明简化 RC 的解析计算与 ngspice 数值解一致；不能证明真实 MOSFET 电流在 1.32196ms 内归零，更不能证明整条 CELL_PERMIT 链路满足 5ms。真实隔离时间仍需完整器件级模型和台架电流波形验收。
