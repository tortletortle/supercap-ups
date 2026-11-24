# 4S 超级电容 UPS 进度看板

更新于 **2026-11-24（北京时间）**

**当前阶段：V0.1 竞赛基线收敛、模块验证与整机行为仿真。整板下单尚未放行。**

**当前唯一执行计划：** [V0.1 竞赛基线研发计划](V0.1_COMPETITION_BASELINE_PLAN_ZH.md)。此前以“所有内部目标都作为首版硬门槛、专项同时扩张”为特点的排期停止派发新任务；已有分支、数据和仿真成果保留，按新计划复核和归类。

**当前共同基线：** [power-stage-integration · 360508c](https://github.com/tortletortle/supercap-ups/tree/360508c08f23f63cdd74fba7e0c201b0907d3825)。此前文档引用的 `ad05db1` 是该分支的前一提交，不再是当前 HEAD。

## 1. 先统一指标口径

赛题原件带有保密提示。公开仓库不上传赛题 PDF、截图、完整评分表或未经授权的原文摘录。具体官方阈值由团队使用获准持有的赛题原件核对；本看板不代替原件。

| 指标类别 | 当前口径 | 处理方式 |
|---|---|---|
| 官方硬指标 | 输入/输出、满载持续时间、切换输出窗口、效率、纹波、输入过压、超级电容过充、短路保护、自动切换 | 按受控赛题原件逐项验收，建立测量边界和实测证据 |
| 内部保持时间裕量 | 12 W、1.2 s | 内部设计目标，不得冒充官方最低持续时间；先满足官方门槛，再评估裕量缺口 |
| 内部单体安全目标 | 欠压到实际放电电流隔离不超过 5 ms | 非赛题评分阈值，但仍是本项目安全约束；没有完整延迟证据不得宣称通过 |
| 模型假设 | 85% Boost 效率、EOL 容量、DC ESR、路径电阻等 | 必须标注假设/典型/保证/实测属性；Boost 效率不等于放电效率或端到端效率 |
| 当前方案选择 | 4S × 20 F | 是当前实现候选，不是赛题规定的唯一架构；本轮冻结，除非证明不可行或关键料不可采购 |
| 后续优化 | 高效率、低纹波、BMS、故障记录、小型化和成本优化 | 放到 V0.2，不阻塞 V0.1，除非关系到硬指标、安全或供应链 |

效率必须分开报告功率级效率、放电到负载端效率和赛题定义的端到端效率。保持时间、保护响应时间也必须分别记录起止事件。

## 2. 当前工作看板

| 优先级 | 工作项 | 已有证据与当前状态 | 下一步交付 |
|---|---|---|---|
| P0 | 负载规格与能量预算 | 当前行为模型基准工况约 1.3749 s；联合劣化工况约 1.146 s，低于内部 1.2 s 裕量。它们是模型结果，不是实物测试。 | 按实际候选料的最坏参数复跑；区分官方最低持续时间与内部 1.2 s 裕量；交付负载端波形和通过/失败表。 |
| P0 | Boost 功率级 | TPS61088 有局部器件级仿真和历史 RAW；完整 RILIM/动态矩阵、保证最小 Isat 和最坏角点尚未全部闭环。 | 复核已有 RAW；完成必要限流、输入范围、启动、阶跃、短路和效率验证；不批准无保证 Isat 的电感。 |
| P0 | 充电与过压 | 有 CC/CV 候选电路和行为模型；自动充电许可、参考上电、单体/组端 OVP 动态和故障锁存仍需闭环。 | 验证恒流、恒压、切换、过压瞬态、开线/复位默认停充和故障恢复。 |
| P0 | 四串单体保护 | 已有约 4.06 ms 的简化模型估算；其中包含逻辑/开关假设，不能当作完整硬件最坏保证。慢扫描配置约 29.7 ms，已被现有模型拒绝。 | 核对 BQ76905 配置和规格边界；逐段证明采样至实际电流隔离时间；覆盖监测失效、开线、复位和重新武装。 |
| P0 | 主备切换与 eFuse | 备源专项已有 18 项测试记录；残压不能单独代表备源可带载。现有模型中的带载检测结果/有效期仍需与硬件实现闭环。 | 落实 U902 完整 MPN、引脚和实际连接；验证 BACKUP_READY、预启动、切换、主源恢复和残压故障。 |
| P0 | 采购与 BOM | 已有采购/嘉立创审查 PR；仍有关键料库存、保证参数、封装和 BOM 映射问题。 | 先锁定超级电容、Boost 电感、eFuse、保护器件等关键物料；逐项给出来源日期、替代影响和采购状态。 |
| P1 | 原理图、嘉立创与 PCB | 有分层 KiCad 工程和 Eagle 导入候选包；嘉立创 GUI 导入、最新全图 ERC/网表、PCB DRC 和生产文件尚未全部验收。 | 以统一工程核对网名/引脚/封装，完成 ERC、DRC、热路径、测试点和生产文件审查。 |

## 3. 当前分支与 PR 快照

以下是 **2026-11-24** 检查到的状态，不代表各分支成果已进入集成基线。

| 入口 | 当前提交/PR | 用途与处理规则 |
|---|---|---|
| [main](https://github.com/tortletortle/supercap-ups/tree/main) | `4d1c83e` | 历史主线；旧 TPS61088 PR #1 以 main 为目标，不能直接并入 4S×20F 集成线 |
| [power-stage-integration](https://github.com/tortletortle/supercap-ups/tree/360508c08f23f63cdd74fba7e0c201b0907d3825) | `360508c` | 当前共同基线；只由总集成负责人通过 PR 更新 |
| [energy-budget-4s20f-reconciliation](https://github.com/tortletortle/supercap-ups/tree/energy-budget-4s20f-reconciliation) | `356f91e` · Draft PR #5 | 能量预算和保持时间模型 |
| [p0-charge-runtime-closure](https://github.com/tortletortle/supercap-ups/tree/p0-charge-runtime-closure) | `ebd239e` · Draft PR #2 | 充电终点、容量失配和保持时间联算；与能量模型有交叉，合并前明确文件边界 |
| [p0-efuse-qualification](https://github.com/tortletortle/supercap-ups/tree/p0-efuse-qualification) | `c06fccd` · Draft PR #4 | eFuse 器件资格与备源路径 |
| [procurement-jlc-eda-audit](https://github.com/tortletortle/supercap-ups/tree/procurement-jlc-eda-audit) | `2e1d809` · Draft PR #6 | 采购 BOM 与嘉立创交付审查 |
| [cell-permit-uv-protection](https://github.com/tortletortle/supercap-ups/tree/cell-permit-uv-protection) | `fd05068` | 单体欠压保护专项；成果尚需按新接口复核 |
| [agent/backup-ready-fail-safe-20261124](https://github.com/tortletortle/supercap-ups/tree/agent/backup-ready-fail-safe-20261124) | `0fe9807` | 备源资格/残压故障专项；成果尚需核对实际原理图 |
| [specialist/tps61088-final-verification](https://github.com/tortletortle/supercap-ups/tree/specialist/tps61088-final-verification) | `930a34e` | TPS61088 最终验证专项；与当前集成线分叉，不整体合并 |
| [architecture-reconciliation-2s-vs-4s](https://github.com/tortletortle/supercap-ups/tree/architecture-reconciliation-2s-vs-4s) | `678f43e` | 架构研究；仅作隔离研究，不改变 V0.1 冻结方案 |

当前开放 Draft PR：[#2](https://github.com/tortletortle/supercap-ups/pull/2)、[#4](https://github.com/tortletortle/supercap-ups/pull/4)、[#5](https://github.com/tortletortle/supercap-ups/pull/5)、[#6](https://github.com/tortletortle/supercap-ups/pull/6) 指向 `power-stage-integration`；[#1](https://github.com/tortletortle/supercap-ups/pull/1) 指向 `main`。本轮不自动合并任何 PR。

## 4. 版本与证据规则

- 设计完成、单元测试、行为仿真、SPICE、整机联合仿真、EDA 检查和实物测试必须分级标记。
- MODEL_ONLY、NOT_TESTED、BLOCKED_SPEC 不得标记为通过。
- 每项报告必须包含完整 commit SHA、文件、命令、工具版本、参数、验收条件、结果和原始证据。
- 分叉分支只提取经复核的必要提交，不整体合并。
- 本计划、总看板和总验收矩阵由总集成负责人维护；专项组通过 PR 或报告提交变更建议。
- 本计划对应的 PR 只修改项目文档，不修改电路、网表、仿真脚本和器件参数。

## 5. 近期交付目标

- **11 月 24 日：** 计划、基线、指标口径和模块边界冻结。
- **11 月 25–27 日：** 关闭保持时间、Boost、充电、单体保护和主备切换的 P0 缺口。
- **11 月 28 日：** 同一集成提交上的整机联合仿真。
- **11 月 29 日：** 故障回归、采购和 EDA 审查。
- **11 月 30 日：** V0.1 整机仿真评审候选。此日期不是实物放行或 PCB 下单承诺；未通过退出条件就如实延期。

## 6. 放行检查

- [ ] 官方赛题硬指标已映射到受控验收表，测量边界明确。
- [ ] 当前 4S×20F 候选在实际物料最坏参数下满足官方能量要求；内部 1.2 s 裕量单独报告。
- [ ] Boost 限流、电感保证最小饱和电流和动态工况有证据。
- [ ] 充电 CC/CV、独立 OVP 和异常默认停充闭环。
- [ ] CELL_PERMIT 和实际放电隔离时间有完整证据。
- [ ] BACKUP_READY 不依赖单独 PG 或残压判断。
- [ ] 关键器件可采购，替代料已评估。
- [ ] 同一提交的整机仿真、原理图和网表一致。
- [ ] ERC/DRC、封装和生产文件完成审查。
- [ ] 首板实测完成后，才发布实物通过结论。

**项目原则：先交付满足官方基本要求、可复现、可安全验证的 V0.1；加分优化进入 V0.2。**
