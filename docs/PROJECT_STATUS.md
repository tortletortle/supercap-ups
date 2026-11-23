# 4S 超级电容 UPS 进度看板

更新于 **2026-11-24（北京时间）**

**当前阶段：原理图评审与整机行为仿真。整板下单仍有阻塞。** 当前以 4S × 20 F 候选和 [电源级集成分支 ad05db1](https://github.com/tortletortle/supercap-ups/tree/ad05db117233ea82153cdbf3a4b59dc652abcb00) 为评审基线。先确认负载规格和物料，再用采购候选的最坏参数重跑整机。

## 验收底线

- 成品在约定最坏工况下，须向实际负载提供 **12 W、至少 1.2 s**，切换期间也须符合负载允许的电压窗口和最大中断时间。这两项负载规格待确认。
- 弱单体欠压后，实际放电路径须在 **5 ms** 内隔离。监测无效时默认禁止备电，故障解除后检查重新武装行为。阈值与各工况见 [仓库验收矩阵](../sim/design_convergence/acceptance_matrix.csv)。
- 采购替代件必须满足相同验收条件。验证板设计评审使用最坏工况证据，成品放行依据台架结果。

## 工作看板

| 优先级 | 工作项 | 已有证据与当前状态 | 队友认领后交付 |
| --- | --- | --- | --- |
| P0 | 负载规格与能量预算 | 4 × 11.2 F 有效容量、106 mΩ/颗、85% 效率、100 mΩ 输入路径下，行为模型为 **1.3749 s**，终点为 Boost 输入降至 7.0 V。独立扫描中，10.8 F/颗、110 mΩ/颗、83%、120 mΩ 同时出现时只有 **1.146 s**。这些是模型参数工况，实际物料边界待确认。 | 确认负载允许电压和断供时间，按实选物料重跑角点，交付负载端波形与通过/失败表。 |
| P0 | BOM 与采购 | Eaton HVH1230-2R7206-R 为 20 F 候选。11.2 F 和 106 mΩ 是寿命末期压力假设。库存、替代件和冷/热、老化数据未核实。[初步 BOM](../hardware/kicad/BOM_PRELIMINARY.csv) | 核对完整料号、封装、可采购数量及证据日期，优先补超容有效容量、DC ESR、电感饱和电流和热态路径损耗。 |
| P0 | 主备切换与 eFuse | 备源专项 18 项复跑通过。加入带载检测有效期后，整机能拒绝残压误判。带载检测结果及其有效期目前由模型外部输入。集成 BOM 列 U902 为 TPS259470ARPW，专项分支审查 AUXOFF/FLT 与 TPS259474LRPW 的 PG/PGTH 候选。 | 在同一版原理图和 BOM 落实 U902 与 BACKUP_READY，实现带载证据及故障撤销链，交付残压反例、抢切时序和负载端波形。 |
| P0 | 四串单体保护 | 弱单体模型隔离 **4.06 ms**，其中 0.4 ms 为逻辑和开关假设；慢扫描配置约 29.7 ms，已被模型拒绝。实际失效状态和隔离时间待验证。 | 固化 BQ76905 配置与放电许可接口，覆盖上电、复位、开线、欠压和重新武装。测弱单体跨阈值至放电电流实际切断的时差。 |
| P0 | CC/CV 与过压 | 行为模型覆盖恒流恒压、单体/组端过压及无许可停充。候选图的 CHG_SAFE_IN 仍依赖台架许可，自动许可和故障锁存待补。 | 验证 CC→CV、参考上电、过压瞬态与停充，给出最低充电终点及充放电联合角点。 |
| P0 | Boost 功率级 | TPS61088 有局部器件级仿真。整机 85% 效率、限流和掉压边界仍需用实际物料验证。[器件级记录](../sim/tps61088_v1_3/) | 补 4S 实际输入范围内的效率、峰值电流、限流、电感温升和瞬态证据。 |
| P1 | 原理图、嘉立创与 PCB | 集成分支有分层 KiCad 工程，并提交了 Eagle 原理图导入包。嘉立创导入未验收，打板文件未放行。[KiCad 评审入口](../hardware/kicad/README.md) · [Eagle 包](../hardware/easyeda/supercap-ups-4s-eagle.zip) | 校对导入前后关键网名和引脚，以最终工程重跑 ERC、核对封装及布局，再检查 DRC 与生产文件。 |

## 分支和版本入口

| 入口 | 用途 |
| --- | --- |
| [main · 4d1c83e](https://github.com/tortletortle/supercap-ups/tree/4d1c83e9ca00c750bcbef4eb7fb76134a87d64da) | 历史仓库主线。它的局部 4S × 10 F 图用于对照。 |
| [power-stage-integration · ad05db1](https://github.com/tortletortle/supercap-ups/tree/ad05db117233ea82153cdbf3a4b59dc652abcb00) | 本看板采用的 4S × 20 F 评审基线，含嘉立创 Eagle 原理图包。 |
| [audit/backup-ready-residual-fault · f1f40d2](https://github.com/tortletortle/supercap-ups/tree/f1f40d26b6c8ea3873b7b673fd2cf92fee678649) | 备源资格与残压反例，含可复跑测试。 |
| [p0-efuse-qualification · c06fccd](https://github.com/tortletortle/supercap-ups/tree/c06fccd8f0a626de8412b40f27e2c61bc9508af6) · [p0-ov2-fault-closure · b3669fd](https://github.com/tortletortle/supercap-ups/tree/b3669fde6a1cd73222fe786869877b7ef9b4dd80) | eFuse 选型接线和 OV2 专项。两条分支均与集成分支有分叉，合入前核对接线和许可证据。 |
| [p0-charge-runtime-closure · ebd239e](https://github.com/tortletortle/supercap-ups/tree/ebd239e6a835b93b9e30484c8ae11211483e3085) | 充电终点、单体失配与备电时间联算。 |

本次复核使用的 4S 整机行为包通过 13 项测试，备源专项通过 18 项。18 项可在备源专项分支用 `python3 sim/backup_transfer/test_backup_ready_fault.py` 复跑。整机 13 项来自独立集成包，组内归档时需附对应脚本、波形和日志。11 月 30 日是 V0.1 集成仿真评审目标，打板日期待定。

## 认领与放行

- [ ] 确认负载规格并关闭实际采购角点下的 1.2 s 缺口。
- [ ] 锁定原理图与 BOM，关闭欠压隔离、充电保护和备源带载资格的关键验证项。
- [ ] 签核验证板的原理图、BOM、布局及生产文件。
- [ ] 首板实测负载供电、故障切换、保护时序及热态性能，再评审成品。

队友认领后在对应行补上负责人及 Issue/PR 链接。更新状态时附提交号、测试条件与波形或日志，保留失败工况。
