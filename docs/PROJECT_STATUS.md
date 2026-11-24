# SuperCap UPS V0.1 项目进度看板

更新于 **2026-11-24（北京时间）**

**当前阶段：竞赛导向 V0.1 加速收敛。** 目标不是继续扩展研究，而是并行完成比赛基本要求、整机仿真、关键器件采购和首板准备。

**当前执行计划：** [V0.1 竞赛导向加速研发计划](V0.1_COMPETITION_BASELINE_PLAN_ZH.md)  
**当前共同研发基线：** [power-stage-integration · 360508c](https://github.com/tortletortle/supercap-ups/tree/360508c08f23f63cdd74fba7e0c201b0907d3825)  
**计划评审 PR：** [#7](https://github.com/tortletortle/supercap-ups/pull/7)（Draft，尚未合并）

> 赛题原件带保密标记，公开仓库不存放原始文件和完整评分表。具体验收以队内获准持有的赛题原件为准。

## 1. 竞赛优先级

1. **P0 基本要求：** 充放电电路、满载备电与切换电压、输入/过充/短路保护。任何一项未通过都阻塞 V0.1。
2. **P1 发挥项：** 典型工况高效率、低纹波、简易 BMS、故障诊断和一项有实测支撑的创新。
3. **P1 报告与证据：** 设计报告、成本分析、完整测试数据和高质量图表从研发第一天同步准备。

内部目标与比赛要求分开：
- 官方满载备电门槛为 1 s；内部 1.2 s 是裕量目标。
- 5 ms 单体欠压隔离是内部安全目标，不冒充比赛评分阈值。
- 放电效率、端到端效率和 Boost 效率分别记录，不互相替代。

## 2. 当前关键状态

| 工作项 | 已有证据 | 当前判断 | 下一步 |
|---|---|---|---|
| 储能与能量预算 | 基准模型约 1.3749 s；已知劣化工况约 1.146 s；更差的弱单体联合工况约 0.977 s | 1.146 s 高于官方 1 s 但低于内部 1.2 s；0.977 s 工况低于官方门槛。均为模型，不是实测 | 用真实候选物料边界复跑，定位低于 1 s 的原因；架构成本比较限时至 11月25日中午 |
| Boost | 有 TPS61088 局部仿真与历史 RAW/LOG | RILIM、动态矩阵和电感保证最小 Isat 未完全闭环 | 复用现有 RAW，补关键输入角点、限流、启动、阶跃、短路、效率和热证据 |
| 充电 | 有 TPS54302 CC/CV 候选和行为模型 | 自动许可、过压动态、开线/复位默认停充仍需闭环 | 完成 CC/CV、输入 OVP、单体/组端 OVP 和故障锁存验证 |
| 单体保护/BMS | 有 BQ76905 配置和简化时间模型 | 简化模型不能证明最坏 5 ms；实物保护未验证 | 核对采样/滤波/ALERT/开关隔离完整链；并行完成简易电量估算与故障记录 |
| 主备切换 | 备源专项有 18 项测试记录 | 残压误判已有模型覆盖，但硬件带载资格和整机切换仍需验证 | 复核 U902 引脚和 BOM；验证 BACKUP_READY、预启动、接管和主源恢复 |
| 采购 | 已有采购与替代料审查 | 关键器件保证参数、库存、封装和成本仍有风险 | 关键料优先询价和锁定，比较满足比赛指标的最低成本方案 |
| EDA/PCB | 有 KiCad 分层工程和 Eagle 导入候选 | 嘉立创 GUI 导入、最终 ERC/DRC 和生产文件尚未全部验收 | 与模块仿真并行准备布局、封装、测试点和制造审查 |
| 报告/测试 | 仿真数据分散在各专项 | 缺统一测试协议和证据归档 | 建立效率、纹波、切换、满载、温升、保护测试模板并持续归档 |

## 3. 加速冲刺里程碑

| 日期 | 目标 | 退出条件 |
|---|---|---|
| 11月24日 | 七条工作线并行启动，统一接口、验收矩阵和证据格式 | 每组提交状态卡、负责人、文件边界和首个复跑命令 |
| 11月25日中午 | 架构与关键物料冻结 | 4S×20F 与既有低成本候选完成限时比较；决定保留或有证据地变更 |
| 11月26日 | P0 模块证据收敛 | Boost、充电、单体保护、主备切换各有复跑结果和波形 |
| 11月27日 | 整机接口集成 | 同一提交的网表和接口一致，正常主备路径可运行 |
| 11月28日 | 整机仿真和故障回归 | 官方硬指标有整机证据，失败项明确 |
| 11月29日 | PCB/采购放行审查 | ERC/DRC、BOM、封装、热设计和关键料采购路径通过 |
| 11月30日 | V0.1 仿真候选发布评审 | 可复跑仿真包、原理图/BOM、PCB候选文件、测试报告初稿和风险清单齐全 |

首板下单在设计与制造放行条件满足后立即执行；真实满载和故障测试在首板到货后完成。11月30日是仿真候选评审目标，不冒充实物验收完成。

## 4. 七条并行工作线

| 工作线 | 唯一职责 | 当前主要交付 |
|---|---|---|
| A 竞赛指标/整机能量 | 官方指标映射、架构选择、储能预算 | 最坏工况表、1 s/1.2 s分级、架构决策 |
| B Boost | TPS61088、RILIM、电感、动态和效率 | RAW/LOG、限流表、效率和热证据 |
| C 充电 | TPS54302、CC/CV、输入及单体/组端 OVP | 充电时序、过压/故障停充证据 |
| D 单体保护/BMS | BQ76905、CELL_PERMIT、简易电量估算 | 保护延迟、默认状态、SOC/任务可用时间和故障记录 |
| E 主备切换 | TPS2121、eFuse、BACKUP_READY | 残压故障、切换时序和主源恢复波形 |
| F 采购/EDA/PCB | MPN、报价库存、封装、制造检查 | 可采购 BOM、替代影响、ERC/DRC和PCB候选 |
| G 测试/报告 | 测量协议、自动化回归、图表和报告 | 测试记录、波形库、效率/纹波/温升报告 |

每个文件/模块只有一个直接修改负责人；总集成负责人维护接口、验收矩阵和看板。各工作线并行推进，不等待其他模块全部结束，但集成必须经过统一接口和证据审查。

## 5. 分支与 PR 快照

以下为 2026-11-24 检查到的入口；专项成果不等于已合入集成基线。

| 入口 | 用途 | 规则 |
|---|---|---|
| [main · 4d1c83e](https://github.com/tortletortle/supercap-ups/tree/4d1c83e9ca00c750bcbef4eb7fb76134a87d64da) | 历史主线 | 不作为当前 4S×20F 集成基线 |
| [power-stage-integration · 360508c](https://github.com/tortletortle/supercap-ups/tree/360508c08f23f63cdd74fba7e0c201b0907d3825) | 当前共同基线 | 由总集成负责人通过 PR 更新 |
| [energy-budget-4s20f-reconciliation](https://github.com/tortletortle/supercap-ups/tree/energy-budget-4s20f-reconciliation) | 能量预算专项，Draft PR #5 | 复核模型边界后提取成果 |
| [p0-charge-runtime-closure](https://github.com/tortletortle/supercap-ups/tree/p0-charge-runtime-closure) | 充电终点/保持时间专项，Draft PR #2 | 与能量预算交叉部分需先对齐 |
| [p0-efuse-qualification](https://github.com/tortletortle/supercap-ups/tree/p0-efuse-qualification) | eFuse 资格专项，Draft PR #4 | 核对实际引脚和集成网表 |
| [procurement-jlc-eda-audit](https://github.com/tortletortle/supercap-ups/tree/procurement-jlc-eda-audit) | 采购与嘉立创审查，Draft PR #6 | 先关闭关键 MPN 和封装问题 |
| [cell-permit-uv-protection](https://github.com/tortletortle/supercap-ups/tree/cell-permit-uv-protection) | 单体欠压保护专项 | 复核最坏延迟和实际隔离证据 |
| [agent/backup-ready-fail-safe-20261124](https://github.com/tortletortle/supercap-ups/tree/agent/backup-ready-fail-safe-20261124) | 备源资格专项 | 复核残压故障和硬件实现 |
| [specialist/tps61088-final-verification](https://github.com/tortletortle/supercap-ups/tree/specialist/tps61088-final-verification) | Boost 最终验证 | 不整体合并分叉成果 |
| [architecture-reconciliation-2s-vs-4s](https://github.com/tortletortle/supercap-ups/tree/architecture-reconciliation-2s-vs-4s) | 低成本架构比较 | 只用于 11月25日限时架构决策 |

## 6. 证据和放行规则

状态必须区分：设计完成、单元测试、行为仿真、SPICE、整机联合仿真、EDA检查、实物测试。MODEL_ONLY、NOT_TESTED、BLOCKED_SPEC 不能标成 PASS。

每个交付附完整 commit SHA、文件路径、命令、工具版本、参数、判定阈值、实际结果和 RAW/LOG/CSV/波形及 SHA256。失败结果保留。

- 不因截止日期自动放行 PCB。
- 不把 1.2 s 内部裕量当成比赛最低门槛。
- 不把 5 ms 内部安全目标当成比赛评分项，也不因赶工删除必要保护。
- 不把 Boost 效率当成放电效率或端到端效率。
- 不用典型值替代关键器件保证值。
- 不宣称未经实测的实物性能。

**项目原则：七条工作线并行、关键路径每日集成、基本要求优先、发挥项同步准备、报告从第一天开始；以最低成本满足比赛标准，但绝不以牺牲安全和真实性换速度。**
