# 4S 超级电容备电功率级原理图

在 KiCad 9 中打开 [supercap-ups-4s.kicad_pro](supercap-ups-4s.kicad_pro)，进入 Schematic Editor。亦可直接打开 [原理图源文件](supercap-ups-4s.kicad_sch)或查看 [PDF](supercap-ups-4s.pdf)。项目目录内的 `sym-lib-table` 和 `TPS61088RHL.kicad_sym` 用于编辑 U1 符号。

## 电路依据

- 4S × 10 F 储能串及 9.4 V 充电目标来自[主线设计基线](../../README.md)。
- 升压器外围取自 [V1.4 EOL 局部窗口网表](https://github.com/tortletortle/supercap-ups/blob/f3ed57162d2f10beb377a69f5ff68a8f5a07595e/sim/tps61088_v1_4/joint/eol_1p2s_130m_92pct.cir)。MODE 接地，RFSW 为 324 kΩ，RILIM 174 kΩ 仍是研究候选。输入输出电容按网表有效值表示，未落实为采购料号。
- 物理引脚按 [TI TPS61088 数据手册第 5 节](https://www.ti.com/lit/ds/symlink/tps61088.pdf)转录。宏模型的 NC 节点悬空，图中物理引脚 11 / 12 按手册接地，21 为 PGND 散热焊盘。

## 覆盖范围与验证

此图覆盖储能串、抽头及升压功率和设定网络。TPS54302 充电、均压与单体监测、保护与欠压检测、主备隔离切换、电容选型和 PCB 布局仍待设计或确认。PACK_4S、VIN_BOOST 和 BOOST_12V 分别代表不同接口。TP2 暴露 BOOST_EN 供调试，控制源尚未绘入。图中功率标志用于声明外部供电和地参考。

KiCad 9.0.2 导出并比对了 17 条网络，ERC 为 0 错误、0 警告。该检查范围是图中已有电路；整机切换、备电时长及台架表现仍待验证。
