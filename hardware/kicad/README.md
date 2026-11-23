# 4S 超级电容 UPS 电源候选图

在 KiCad 9 中打开 [工程](supercap-ups-4s.kicad_pro)，进入 Schematic Editor。七页电路可集中查看 [原理图 PDF](supercap-ups-4s.pdf)。

| 图页 | 电路覆盖 | 验证边界 |
| --- | --- | --- |
| 储能与升压 | 4S × 20 F、抽头、四路 2.2 kΩ 无源均压、TPS61088 升压 | 均压用于抑制稳态漏电差引起的偏移。失配单体快速过压时，仍需独立停充 |
| CC/CV 充电候选 | TPS54302、外部电流检测与反馈、防回灌元件及关断接口 | 充电电流、环路稳定性、精准 CV 和单体过压联锁仍待验证 |
| 组端欠压 | TPS3700 组端检测、硬件迟滞、PACK_UV_OK 输出 | 组端许可已接入放电隔离，BOOST_EN 仍待接入系统控制 |
| 四串单体过压 | 四路差分采样、开漏过压停充 | CHG_OVP_OD 已接充电 EN。控制器充电许可、抽头断线和故障复位仍待验证 |
| 放电隔离 | Si7149DP 背靠背开关，由 PACK_UV_OK 与 DISCHARGE_ARM 控制 | DISCHARGE_ARM 仍待驱动。热态通路电阻、浪涌和欠压回跳仍待验证 |

KiCad 9.0.2 的七页整合图 ERC 为 0 错误、0 警告。导出网表确认 PACK_4S 与 GND 跨页互通，并确认 VIN_BOOST 与 PACK_4S 经独立开关网络隔离。已核对精密反馈和串联关断的跨页网表。

TPS61088 原功率级依据见 [V1.4 EOL 局部窗口网表](https://github.com/tortletortle/supercap-ups/blob/f3ed57162d2f10beb377a69f5ff68a8f5a07595e/sim/tps61088_v1_4/joint/eol_1p2s_130m_92pct.cir) 和 [TI 数据手册](https://www.ti.com/lit/ds/symlink/tps61088.pdf)。RILIM 仍是研究候选，输入和输出电容采用网表有效值。

[充电设计](CHARGER_DESIGN.md) · [欠压设计](pack-uvlo-design.md) · [接口约定](power-stage-interfaces.md) · [失效模式与验收](system-interface-and-fault-review.md) · [无源均压计算](../../sim/cell_balancing/README.md) · [充电终点与欠压联算](../../sim/protection_budget/README.md)

该版本用于原理图评审。整机主备切换、控制器许可链、单体放电保护及台架验证尚待完成。

## 第二轮评审

[单体过压设计](cell-ovp-design.md) · [放电隔离设计](pack-discharge-switch-design.md) · [精密恒压及独立总压截止候选](precision-cv-ovp/README.md) · [主备预启动与切换候选](backup-pre-ready-switching.md) · [充电、UVLO 与串联损耗联合计算](../../sim/charge_window/README.md) · [容量失配降流分流估算](../../sim/balance_recovery/README.md)

旧 10 F 基线下的 9.2825 V / 23.5 mΩ 结果已由 20 F 候选取代，不再作为当前设计门槛。当前 4×20 F EOL 联合预算采用每颗 11.2 F、106 mΩ DC ESR 压力假设、9.0 V 最低初始 OCV、85% Boost 效率及 145 mΩ 输出路径：新增输入串联路径 100 mΩ 时保持约 1.375 s，150 mΩ 时约 1.216 s。当前热态输入路径设计目标为 ≤100 mΩ；150 mΩ 仅作边界测试。详情见 [电源级收敛评审](POWER_STAGE_DESIGN_CONVERGENCE.md) 和 [可复跑预算](../../sim/design_convergence/README.md)。

## 20 F 储能候选

C1–C4 选用 Eaton HVH1230-2R7206-R（20 F、2.7 V），配 12.5 mm 径向电容封装、5 mm 引脚间距。9.0 V 是最低初始静置开路组压目标；每颗 EOL 有效容量按 11.2 F 建模。106 mΩ/颗是初始最大 DC ESR 的两倍压力假设，不是厂家保证的 EOL DC ESR，必须对样品测量。样机按容量比不超过 1.08 分选。[计算及选型边界](../../sim/charge_window/storage-candidates.md)

## 精密充电整合

第七页作为整机评审图，D101 阴极经 Q601 才到 PACK_4S。组端 CV 和总压截止均取隔离管后的组压，CHG_FB 接回 Buck。R104 调整为 162 kΩ，本地 Buck 反馈只作为 10.25 V 标称兜底。J601 的 1、2 脚为 5 V 监测点，电源已由第七页提供。CHG_SAFE_IN 仍是台架许可接口，自动许可和参考就绪电路待实现。单体过压继续拉低 Buck EN，第七页也读取该节点并撤销 Q601 的串联关断许可。动态环路、故障锁存、反灌与主备接管仍待验证。独立精密页保留供台架对照。

## 充电辅助电源

第七页从 VIN_MAIN 分别用 U701、U702（TPS70950DBVR）生成 5V_CV 和 5V_OVP，两路共输入和地，各自稳压。DBV 封装的 EN 引脚按手册允许悬空启用，12 V 不接 EN。输入 1 µF / 50 V，输出 4.7 µF / 16 V，实际物料需确认输出有效电容在直流偏压和温度下至少 2.2 µF。手册给出反向电流保护，输出低于 1.8 V 时仍可能出现反流。J601 的 1、2 脚仅用于监测，不接外部电源。两路电源同时上电也不构成 CHG_SAFE_IN 的许可条件。[TI TPS709 数据手册](https://www.ti.com/lit/ds/symlink/tps709.pdf)

十个现有引脚仅有两路 5 V 网络由页内变为跨页，其余引脚网名保持一致。两路稳压器尚未进行电源波形或热验证。应在带预充电容组及主电源掉电条件下观察 VIN_MAIN、两路 5 V、参考电压与串联开关栅源电压。

## 串联开关台架联锁

U703（SN74LVC1G17DBVR）用现有 3V3_CHG 供电，经施密特缓冲读取 CHG_OVP_OD。R705 为 100 kΩ，输入断线时下拉。R706 为 39 kΩ，在缓冲失电进入高阻时下拉 Q703。Q603 源极改接 CUT_SAFE_RETURN，Q703（AO3400A）位于该节点到地的低侧回路。Q602 总压许可、Q603 外部 CHG_SAFE_IN 和 Q703 的稳态 EN 许可须同时有效，Q601 才有栅极下拉通路。网表比对确认 361 个原有引脚端点仅 Q603.2 改网，增加 14 个端点。全图 ERC 0 错误、0 警告。[SN74LVC1G17 数据手册](https://www.ti.com/lit/ds/symlink/sn74lvc1g17.pdf) · [AO3400A 数据手册](https://aosmd.com/res/datasheets/AO3400A.pdf)

R705 与原 47 kΩ 下拉并联，3.3 V 推挽许可经原 4.7 kΩ 时，理想 EN 高电平约 2.88 V，尚未扣除输入漏电和驱动误差。SN74LVC1G17 在 3.0 V 的上行阈值为 1.48–1.92 V，下行为 0.89–1.20 V。施密特阈值与 TPS54302 的 EN 阈值不同，缓慢下坡时允许出现两个关断动作不同步。台架需验证实际灌流下的 EN 稳态高低电平和关断时差。本缓冲器的部分断电行为适用于 VCC 为 0 V 的规格条件，掉电中间电压仍需结合外部许可验证。

CHG_SAFE_IN 上电保持低，只有外部台架确认参考电平和各单体状态后才允许置高。若持续置高，过压解除后本电路可能自动恢复。自动锁存、上电参考就绪和故障后的重新武装逻辑待实现。三路门控仅覆盖相应稳态故障信号，MOS 短路和充电环失控时仍需独立台架验证。
