# JLCEDA 导入指南与验收状态

## 当前可用入口

- 候选 EAGLE 包：[`supercap-ups-4s-eagle.zip`](./supercap-ups-4s-eagle.zip)
- KiCad 原工程：[`hardware/kicad/`](../kicad/)
- Weave 预检分支：[`test/ltspice-weave-jlc-qualification`](https://github.com/tortletortle/supercap-ups/tree/test/ltspice-weave-jlc-qualification)

## 重要限制

1. 当前 KiCad 工程使用 KiCad 9。JLCEDA Pro 官方 KiCad 导入指南列出的兼容版本是 KiCad 5.1 / 5.9；KiCad 9 直导没有在本项目中验证。
2. 官方 EAGLE 导入指南支持 EAGLE 6+ 项目。当前仓库有 EAGLE ZIP 候选包，但本轮未能解包检查其内部文件，也没有实际 JLCEDA GUI 导入。
3. Weave 的 NET→ASC 输出是 LTspice `.asc`，不是 JLCEDA 原理图工程，不会生成封装或 PCB。
4. 当前仓库没有 `.kicad_pcb`，所以不存在可导入并验收的完整 PCB 布局；DRC 与生产文件均未完成。

## GUI 导入步骤（需在本机 JLCEDA Pro 执行）

1. 在 JLCEDA Pro 中选择 EAGLE 导入入口，导入 `supercap-ups-4s-eagle.zip`。
2. 如果导入器要求 EAGLE 工程同时包含原理图和 PCB，请先检查 ZIP 是否包含 `.sch` 与 `.brd`；若只有 `.sch`，只能验收原理图导入，不能声称 PCB 已导入。
3. 导入后核对层级页数量、元件数量、网络数量和引脚连接数量。历史静态预检记录：9 页、167 元件、116 nets、486 pin connections；这些是对照基准，不是 GUI 通过证据。
4. 逐个检查高风险器件：TPS61088 RHL、BQ76905 RGR、Si7149DP PowerPAK SO-8、TPS3839 DQN X2SON、TPS2121 RUX、TPS25947 RPW。
5. 对照 `JLCEDA_FOOTPRINT_AUDIT.csv` 核对 footprint、pad number、pin number、极性、thermal pad、丝印和阻焊开窗。
6. 检查 PACK_4S、VIN_BOOST、BOOST_12V、LOAD_12V、CELL1–CELL4、CHG_ALLOW、CHG_OVP_OD、DISCHARGE_ARM、BACKUP_READY 等网络名及电源符号。
7. 在元件库中核对真实制造商料号和封装，不得只凭同名符号/封装自动匹配。
8. 只有在完整原理图、BOM、封装映射和 PCB 都确认后，才执行 JLC DRC 并生成 Gerber、Drill、BOM、CPL。

## 当前验收状态

| 项目 | 状态 |
|---|---|
| EAGLE ZIP 存在 | 是 |
| ZIP 内部文件结构复核 | 未完成 |
| JLCEDA GUI 实际导入 | 未验证 |
| 原理图网络对照 | 只有历史静态计数，无 GUI 证据 |
| 关键器件 footprint/pad map | 未完成 |
| PCB 导入 | 无 PCB 文件 |
| JLC DRC | 未运行 |
| Gerber/Drill/BOM/CPL | 不存在 |

## Weave 结果边界

Weave 的 NET→ASC 用于 LTspice 测试网表转为 ASC 原理图。已存在的预检工程对 `eol_1p2s.cir` 进行转换与回读一致性检查，TPS61088 宏模型使用 synthetic 21-pin symbol。它不是 JLCEDA 导入流程，也不是 TPS61088 真实封装/焊盘验证。请勿把 NET↔ASC MATCH 标记为 JLCEDA GUI import PASS。
