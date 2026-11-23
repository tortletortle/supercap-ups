# 主备备源资格与 eFuse 变体模型

状态：器件语义回归模型 + 现有 OV2 静态角点脚本；不是完整电路仿真、KiCad ERC 或台架验证。

## 器件评审

当前 BOM 的 U902 是 TPS259470ARPW。TI TPS25947 Rev C（2026-05）区分：
- TPS259470A：AUXOFF + FLT、主动限流、自动重试、无 PG/PGTH。
- TPS259470L：AUXOFF + FLT、主动限流、锁存关断、仍无 PG/PGTH。
- TPS259474L：PG + PGTH、Circuit Breaker、Latch-Off；下一轮优先候选，但不是 drop-in。

470x AUXOFF 只表示输入有效且 inrush 完成，不反映负载侧过流/短路。474x 的 PG 由 PGTH 与器件状态共同决定，PGTH 应从 eFuse OUT 分压。

## TPS259474L 边界

- PGTH 上升阈值 1.183–1.223 V；下降阈值 1.076–1.116 V。
- PG assertion/deassertion deglitch 为 12 µs typical，没有可用于系统最坏时序证明的最大值。
- 1.65 kΩ R_ILM 的电流范围为 1.800 / 2.028 / 2.200 A（min/typ/max）；需联合核算输出电容充电、Boost 启动和负载阶跃。
- 持续 Circuit-Breaker 过流和过温可锁存；输出硬短路为 fast-trip 后 current-limit，内部 fault-latched=N，外部系统锁存仍然必须保留。
- 清除内部锁存需 VIN 掉到 0 V 后重启，或 EN/UVLO 拉到 V_SD 以下；仅略低于 UVLO falling threshold 不够。
- PG 为开漏输出；器件未供电时没有主动下拉保证到 0 V，接收端必须有默认低和防反灌设计。

TI 数据手册：https://www.ti.com/lit/ds/slvsfc9c/slvsfc9c.pdf

## 模型边界与复现

efuse_variant_model.py 对 PG 阈值公差带做保守分类；落在公差带内返回不确定。它区分持续过流锁存与输出短路不内部锁存，并模拟 BACKUP_READY 故障锁存/重新武装。没有虚构 PG 最大传播延迟，也不把 12 µs typical 当成最坏保证。

复现：
- python3 -B sim/backup_transfer/check_ov2_bias.py
- python3 -B sim/backup_transfer/check_residual_input.py
- python3 -m unittest discover -s sim/backup_transfer -p 'test_*.py' -v
- python3 -m unittest discover -s sim/design_convergence -p 'test_*.py' -v
- python3 -B sim/design_convergence/power_stage_budget.py
- python3 -B sim/design_convergence/check_artifacts.py
