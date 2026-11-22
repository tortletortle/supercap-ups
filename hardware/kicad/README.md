# 4S 超级电容 UPS 电源候选图

在 KiCad 9 中打开 [工程](supercap-ups-4s.kicad_pro)，进入 Schematic Editor。三页电路可集中查看 [原理图 PDF](supercap-ups-4s.pdf)。

| 图页 | 电路覆盖 | 验证边界 |
| --- | --- | --- |
| 储能与升压 | 4S × 10 F、抽头、四路 2.2 kΩ 无源均压、TPS61088 升压 | 均压用于抑制稳态漏电差引起的偏移。失配单体快速过压时，仍需独立停充 |
| CC/CV 充电候选 | TPS54302、外部电流检测与反馈、防回灌元件及关断接口 | 充电电流、环路稳定性、精准 CV 和单体过压联锁仍待验证 |
| 组端欠压 | TPS3700 组端检测、硬件迟滞、PACK_UV_OK 输出 | 许可输出尚待接入放电隔离和 BOOST_EN 控制。须验证带载跳闸、恢复、抖动和漏电 |

KiCad 9.0.2 的三页整合图 ERC 为 0 错误、0 警告。导出网表确认 PACK_4S 与 GND 跨页互通，并确认 VIN_BOOST 仍独立，等待放电隔离器件。

TPS61088 原功率级依据见 [V1.4 EOL 局部窗口网表](https://github.com/tortletortle/supercap-ups/blob/f3ed57162d2f10beb377a69f5ff68a8f5a07595e/sim/tps61088_v1_4/joint/eol_1p2s_130m_92pct.cir) 和 [TI 数据手册](https://www.ti.com/lit/ds/symlink/tps61088.pdf)。RILIM 仍是研究候选，输入和输出电容采用网表有效值。

[充电设计](CHARGER_DESIGN.md) · [欠压设计](pack-uvlo-design.md) · [接口约定](power-stage-interfaces.md) · [失效模式与验收](system-interface-and-fault-review.md) · [无源均压计算](../../sim/cell_balancing/README.md) · [充电终点与欠压联算](../../sim/protection_budget/README.md)

该版本用于原理图评审。整机主备切换、单体保护、放电物理隔离及台架验证尚待完成。
