# 嘉立创 EDA 导入指南与验收状态（修订版）

## 1. 当前有三条不同导入路径

### A. KiCad 原工程直接转换

嘉立创 EDA 专业版官方格式转换助手列出的 KiCad 支持格式包括：
- .kicad_sch
- .kicad_pcb
- .kicad_sym
- .kicad_mod
- .pro.kicad_pro
- 以及 KiCad 旧版相关文件/库格式。

因此不再沿用“只支持 KiCad 5.1/5.9”的旧说法。官方列出文件扩展名并不等于承诺所有 KiCad 9 图元/层级/自定义符号都无损；当前工程必须实际转换后核对。官方文档也提示第三方格式转换可能存在差异，必须在目标 EDA 中检查。

官方入口文档：https://prodocs.lceda.cn/cn/import-export/easyeda-pro-format-converter/

### B. EAGLE 工程 ZIP 导入

官方格式转换助手列出 EAGLE .zip、.lbr、.sch、.brd。基线仓库中有候选文件：
hardware/easyeda/supercap-ups-4s-eagle.zip

该 ZIP 在本轮未能解包检查内部文件，不能确认它是否同时包含原理图和 PCB。文件存在不等于 GUI 导入成功。

### C. Weave NET → LTspice ASC → 嘉立创 LTspice 导入

嘉立创 EDA 专业版官方支持导入 LTspice ASCII 文件，但要求：
1. ASC 必须为 ASCII 格式；
2. ASC 所引用的每个符号 ASY 都必须提供；
3. 将 ASC 和对应 ASY 文件一起打包成 ZIP；
4. 通过“开始页 → 快速开始 → 导入其他 → 导入 LTspice”，或“文件 → 导入 → LTspice”导入。

官方说明：https://prodocs.lceda.cn/cn/import-export/import-ltspice/

项目已有隔离资格测试分支：https://github.com/tortletortle/supercap-ups/tree/test/ltspice-weave-jlc-qualification

其输入为 sim/tps61088_v1_3/joint/eol_1p2s.cir，不是整机生产原理图。Weave 生成的 __block21.asy 是宏模型 21-pin 合成符号，不是 TPS61088 真实芯片引脚图，也没有 PCB footprint。打包脚本还要求本机 LTspice 标准符号 bi/cap/ind/res/voltage.asy；缺失、冲突或 pin order 错误时拒绝生成 ZIP。

Weave round-trip MATCH 只证明网表与 ASC 的网络连接分区一致，不证明电气行为、视觉布局、真实器件 pin map 或 PCB 生产可行性。

## 2. 本机 GUI 验收流程

### KiCad 工程导入
1. 在嘉立创 EDA 专业版打开格式转换助手，选择 KiCad 工程文件。
2. 导入顶层 .kicad_sch，同时导入层级子页及自定义符号/封装库。
3. 对照原始 KiCad 页数、元件位号、网络名、pin number 和电源网络。
4. 特别检查 TPS61088 RHL、BQ76905 RGR、TPS2121 RUX、TPS25947 RPW、TPS3839 DQN、Si7149DP PowerPAK。
5. 检查所有 exposed pad、thermal pad、NC、极性和封装焊盘编号。
6. 核对 BOM 的 167 个原理图位号；不得把 101 个漏入初步 BOM 的位号忽略。
7. 只有转换后原理图、BOM、器件库、封装映射逐项一致，才继续 PCB。

### LTspice/Weave 导入
1. 运行隔离分支的 Weave NET→ASC 转换。
2. 对 ASC 执行 round-trip verifier，保存原始 NET、ASC、LOG、ASY、manifest 和 SHA256。
3. 从本机 LTspice 库补齐全部 ASY；运行 package_jlc_import.py，缺符号/冲突/pin order 不连续时必须失败关闭。
4. 将生成的 ZIP 导入嘉立创 LTspice。
5. 检查符号是否缺失、引脚是否错位、导线是否真正连接。
6. 只把该路径用于仿真 testbench 的可视化/检查，不得把 synthetic 21-pin macro symbol 当成生产器件符号。

## 3. 当前实际验收状态

| 项目 | 状态 |
|---|---|
| KiCad 文件格式被官方列为支持 | 是 |
| 当前 KiCad 9 层级工程 GUI 导入 | 未验证 |
| EAGLE ZIP 文件存在 | 是 |
| EAGLE ZIP 内部结构已复核 | 未验证 |
| EAGLE ZIP GUI 导入 | 未验证 |
| Weave NET→ASC 测试工程与脚本存在 | 是 |
| Weave round-trip MATCH | 分支 README 声明；本轮未取得对应 Actions run/log 独立复核 |
| Weave ASC+ASY ZIP 已完整生成 | 未确认；CI 预检缺本机 LTspice 标准 ASY |
| Weave LTspice ZIP GUI 导入 | 未验证 |
| TPS61088 synthetic 21-pin 符号为真实 IC footprint | 否 |
| PCB 文件 | 不存在 |
| DRC | 不可运行 |
| Gerber/Drill/BOM/CPL | 不存在 |

## 4. 打板前不可跳过

- 将 U901/U902/U903 的实际器件和外围网络加入正式层级原理图。
- 补齐全部 167 位号 BOM、制造商料号和封装。
- 补齐空 footprint；按数据手册封装图校验 pad number 和 exposed pad。
- 生成真实 .kicad_pcb 并完成布局。
- 在嘉立创 GUI 中完成导入检查；输出网络对照记录和差异清单。
- 运行 ERC/DRC；输出 Gerber、Drill、BOM、CPL、装配图。
