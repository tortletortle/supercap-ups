# 4S×20F 真实采购与嘉立创 EDA 交付审查

- 仓库：`tortletortle/supercap-ups`
- 本轮共同基线：`360508c08f23f63cdd74fba7e0c201b0907d3825`
- 专项分支：`procurement-jlc-eda-audit`
- 审查日期：2026-11-24
- 范围：真实物料可采购性、替代料影响、KiCad→嘉立创交付、Weave NET→ASC 证据、生产放行条件。
- 本报告只增加审计文件，不修改 `main` 或 `power-stage-integration`，不合并其他分支。

## 结论

**当前设计不能下单生产板。** 关键功率器件中有一部分可以在中国大陆渠道找到，但采购 BOM、原理图、封装和 PCB 交付并未闭环。最严重的问题不是某一个器件缺货，而是当前 BOM 与层级原理图明显不一致，且 Boost 电感没有满足器件限流角点的证据。

### 关键统计（从基线文件静态解析）

| 项目 | 结果 |
|---|---:|
| 层级原理图页 | 9 页（含顶层） |
| 层级原理图唯一元件位号 | 167 |
| `BOM_PRELIMINARY.csv` 行数 | 45 |
| BOM 展开后的唯一位号 | 74 |
| 与原理图重合的位号 | 66 |
| 原理图中未进入 BOM 的位号 | **101** |
| BOM 中存在、但层级原理图不存在的位号 | **8** |
| 原理图 Footprint 属性为空 | **72 / 167** |
| `.kicad_pcb` 文件 | **不存在** |
| `fp-lib-table` / 自定义 `.pretty` 封装库 | **未发现** |

8 个 BOM-only 位号为 `CIN`、`COUT1–COUT4`、`U901–U903`。其中 U901/U902/U903 是 TPS2121、eFuse 和参考源候选，但当前层级原理图没有对应的 Power MUX/eFuse 页面。CIN/COUT 在 BOM 中有候选描述，但原理图以有效电容占位符表达，尚未落成真实电容阵列。

完整逐位号清单见：
- [采购 BOM 审计（原理图 167 位号 + BOM-only 8 项）](../hardware/kicad/PROCUREMENT_BOM_AUDIT.csv)
- [封装映射审计（167 位号）](../hardware/kicad/JLCEDA_FOOTPRINT_AUDIT.csv)
- [关键器件采购快照与替代料表](../hardware/kicad/KEY_PARTS_PURCHASE.csv)

## 一、真实器件采购

库存和价格是 2026-11-24 检索到的公开目录快照，不是供应商报价单，也不是已登录购物车的锁库存承诺。LCSC 页面价格以其页面显示币种记录；DigiKey 中国价格按 CNY 记录。采购前必须重新确认含税价格、交期、批次和可发货地区。

### 已找到可采购渠道的关键器件

| 器件 | 完整 MPN | 渠道快照 | 结论 |
|---|---|---|---|
| 超级电容 | Eaton `HVH1230-2R7206-R` | DigiKey 中国约 1,576 件，约 ¥15.71/件，MOQ 1 | 可采购；仍需确认批次、寿命和高温降额 |
| Boost IC | TI `TPS61088RHLR` | LCSC 约 893 件，约 US$1.1702，MOQ 1 | 可采购；KiCad 缺 footprint |
| 主备 MUX | TI `TPS2121RUXR` | DigiKey 中国约 16,644 件，约 ¥21.82/件，MOQ 1 | 可采购；但当前不在原理图中 |
| eFuse 当前候选 | TI `TPS259470ARPWR` | LCSC 约 1,293 件，约 US$1.412，MOQ 1 | 可采购；BOM 需补完整订货后缀 R |
| eFuse 候选 | TI `TPS259474LRPWR` | LCSC 约 1,754 件，约 US$1.3541，MOQ 1 | 可采购；与 470A 不是电气 pin-to-pin 替代 |
| 充电 Buck | TI `TPS54302DDCR` | LCSC 约 1,175 件，约 US$0.303，MOQ 5 | 可采购 |
| 单体隔离 MOSFET | Vishay `Si7149DP-T1-GE3` | DigiKey 中国约 9,877 件，约 ¥20.34/件 | 可采购；BOM 当前缺完整后缀 |
| 电流采样放大器 | TI `INA180A1IDBVR` | LCSC 约 79,355 件，约 US$0.287，MOQ 5 | 可采购 |
| CV/OVP 参考 | TI `REF5025IDR` | LCSC 约 3,597 件，约 US$3.7054 | 可采购 |
| 运放 | TI `OPA333AIDBVR` | LCSC 约 8,636 件，约 US$1.3184 | 可采购 |
| 快速比较器 | TI `TLV9031DBVR` | DigiKey 中国约 10,571 件，约 ¥11.09 | 可采购；100ns 为典型传播延迟，不能当最大保证值 |
| 5V LDO | TI `TPS70950DBVR` | LCSC 约 21,655 件，约 US$0.6332 | 可采购 |
| 低漏电二极管候选 | onsemi `BAV199LT1G` | DigiKey 中国约 161,424 件，约 ¥1.32 | 可采购；双串联二极管，需改符号/封装 |

### 采购风险与阻塞器件

1. **BQ76905RGRR：P0 缺货风险。** DigiKey 中国检索时库存为 0，页面给出的后续到货日期在 2027 年；LCSC 有产品条目但未找到可确认库存。它是 4S 单体监测方案的核心器件，没有样品就不能完成板级验证。
2. **OPA4197IPWR：供货极薄。** LCSC 索引快照仅 1 件，DigiKey 中国为 0。单台样机可能勉强采购，不能视为量产供货。
3. **LM339BIPWR：准确订货号与供应要重新确认。** 现 BOM 写 `LM339BPWR`，TI 可检索的 B 版完整订货号为 `LM339BIPWR`；TI 中国当前未显示库存。LCSC 的 `LM339PWR` 不带 B，不能直接替代。
4. **SN74LVC1G74DCTR：库存未确认。** BOM 写 `SN74LVC1G74DCT`，需要补订单包装后缀；DigiKey 中国检索时为 0，预计到货日期为 2026-11-24，须重新检查是否已入库。
5. **TPS3839G33DQNT：小卷库存有限。** DQNT 索引库存约 65；`TPS3839G33DQNR` 是同器件/同封装的另一卷带后缀，索引库存约 4,396。DQNR 可作为包装数量替代，不改变电路和 PCB。
6. **D101：SS34 不是完整 MPN。** SS34 是多家厂商使用的系列名称，反向漏电和热态表现差异明显。现有 BOM 没有制造商、完整料号和保证漏电数据。
7. **L101、R101、CIN：尚未冻结。** L101 没有完整 MPN/footprint；R101 没有完整 MPN；CIN 只有有效电容要求，没有物理电容 BOM。

## 二、关键替代料和重新仿真影响

### Boost 电感 L1：现选型不通过限流筛查

当前 BOM 的 CENKER `CKST0603-3.3uH/M` 公开参数为 3.3µH、Isat 9.5A Typ、Irms 6A Typ、DCR max 26mΩ。TPS61088 在 RILIM=100kΩ 时，数据手册最大峰值限流约为 11.4A（FPWM）或 13A（PFM）。按项目采用的 `I_LIM,max ≤ 0.8×I_SAT,min` 规则，所需保证最小 Isat 至少为：
- FPWM：11.4 / 0.8 = **14.25A**
- PFM：13.0 / 0.8 = **16.25A**

现有 9.5A 是典型值，低于最大限流，不能放行。

候选 Sunlord `MWSA1205S-3R3MT`：3.3µH、DCR max 7mΩ，数据表列 Isat Max 17.6A / Typ 22A、Irms Max 12A / Typ 14A，JLC PCBA 页面约 277 件、US$0.6753。它是更合适的仿真候选，但数据表没有把 17.6A 明确写成跨批次保证的 `Isat,min`；在拿到厂家书面定义/保证前，不能按 17.6A 最小值签核。封装从约 7.4×6.6mm 增至 13.45×12.6mm，必须重新布局并重跑启动、限流、短路、热和效率仿真。JLC 库存仅供 PCBA，不能当作散料采购库存。

### 充电电感 L101

候选 Sunlord `MWSA1204S-100MT`：10µH、DCR max 25mΩ，数据表列 Isat Max 8A / Typ 10A、Irms Max 7A / Typ 8A。DigiKey 全球页面约 311 件、US$1.47、标准交期约 16 周。它比当前未选型状态更具体，但同样没有明确的保证最小 Isat；封装约 13.5×12.8×4mm，远大于紧凑型候选。需要重新验证 Buck 电流纹波、CC/CV 环路、启动和热。

### D101 充电反灌隔离

- `STPS340U`：虽然 LCSC 有库存，但数据手册给出的 125°C 最大反向漏电可达 10mA，不适合作为未验证的低漏电长期隔离方案，暂不推荐。
- `S3A-E3/57T` / `ES3A-13-F`：硅整流候选，目录列出约 10µA@50V，但正向压降明显高于肖特基，且封装为 SMC；没有拿到实际工作温度、9.4V 反压下的最大漏电保证，不能直接冻结。
- 结论：**暂不批准 D101。** 需要取得热态反向漏电保证/实测，并用最低主输入电压重跑充电 CV 余量。若低漏电与低压降无法同时满足，应评估受控 MOSFET 反向阻断拓扑，而不是盲目替换 SS34。

### D801/D802 监测供电隔离

onsemi `BAV199LT1G` 的官方数据表给出低漏电特性（25°C 下 5nA@70V，150°C 条件下 80nA）。但它是 SOT-23-3 双串联二极管，不是现有 2-pin 单二极管符号的直接替换；需要更新符号、pin mapping、footprint，并分别为 BAT 与 REGSRC 保留隔离。LCSC 页面把漏电列为 5µA，与 onsemi 数据表相冲突；采购验收以制造商原始数据表为准。

### 其它替代

- `1N4148W` 与当前 SOD-323 footprint 不匹配；建议用 `1N4148WS-7-F`（SOD-323）或将 footprint 改为 SOD-123。
- `BAT54` 必须选定 BAT54/BAT54A/BAT54C/BAT54S 的具体结构；候选 `BAT54-7-F` 是 SOT-23-3，需正确处理 NC/公共端 pin。
- `2N7002` 建议使用完整料号 `2N7002,215`；仍需按实际 VGS 检查 RDS(on) 和关断能力。
- `TPS259470A` 与 `TPS259474L` 虽同为 2×2mm QFN-10，但 470A 的 pin3/pin4 为 AUXOFF/FLT，474L 为 PG/PGTH；前者主动限流/自动重试，后者 circuit-breaker/latch-off。替换需要改原理图、PGTH 阈值、故障锁存和重新武装逻辑，并重跑备源残压反例，不能只换 BOM。
- `TPS3839G33DQNR` 替换 DQNT 只改变包装卷带数量，不改变芯片/封装/引脚；可作为采购包装替代。

## 三、KiCad / 嘉立创 EDA 审查

### KiCad 工程静态检查

- 当前工程是 KiCad 9 系列，顶层层级包含 9 页。
- TPS61088 自定义符号的逻辑引脚编号为 1–20 加 PGND/EP 21；与 TI RHL 数据表 pin map 对齐。
- BQ76905 自定义符号为 20-pin；其 VC 输入 pin map 与 TI 4S 表格一致。注意：符号正确不等于封装/焊盘正确。
- U1 TPS61088、U801 BQ76905、U914 TPS3839 的 footprint 属性为空；关键 IC 尚未落到可生产封装。
- D910 的 `1N4148W` 值与 SOD-323 footprint 不一致。
- 连接器 J101/J601、测试点 TP1/TP2、L1/L101、D101/D801/D802 及大量无源件缺 footprint。
- 顶层注释明确仍有 startup timeout、power MUX 和 charger permission 未闭合；U901/U902/U903 目前只是 BOM 候选，不在层级原理图中。

### ERC / DRC

- 仓库文档中有 KiCad 9.0.2 某充电页 ERC 0 error / 0 warning 的历史记录；这不是整个 9 页工程的 ERC 结果。
- `power-stage-design-check.yml` 工作流存在，但本轮无法取得基线提交对应的完整 ERC 日志，因此不把它标成全工程通过。
- 当前执行环境没有 `kicad-cli`，本轮未能本地重跑 ERC。
- 仓库中没有 `.kicad_pcb` 文件，所以 **DRC 不可运行**；没有 Gerber、钻孔、坐标文件或可下单 PCB。

## 四、Weave NET→ASC 与嘉立创导入

### Weave 证据边界

`test/ltspice-weave-jlc-qualification` 分支（提交 `5b1009870894ce5638f723d7c6ec955975ffefb8`）有一个 LTspice/JLC 导入预检测试工程：
- 输入是 `eol_1p2s.cir` 一类 SPICE 测试网表，不是完整 UPS 生产原理图。
- 记录了 NET→ASC 转换及 ASC→NET 回读一致性检查。
- TPS61088 宏模型使用 21-pin synthetic symbol；它服务于模型引脚映射，不等于真实 TPS61088 封装或 JLCEDA footprint。
- 测试脚本覆盖 4 个 package/preflight 用例；该分支报告没有给出真实 JLCEDA GUI 导入结果。
- 分支工作流受本地 LTspice 标准符号库影响，生成的是预检产物，不等于已验收的完整生产导入包。

此前对话曾报告 `tps61088-jlc-qualification-kit.zip` 的 NET→ASC PASS / NET↔ASC MATCH，但该 ZIP 未在本轮共同基线树中找到可核验路径，因此本轮不能把它当作已复验交付物。Weave 解决的是 LTspice NET→ASC，不是 KiCad→JLCEDA，也不负责 PCB footprint/pad mapping。

### 嘉立创 EDA 导入方式

- JLCEDA Pro 官方 KiCad 导入指南列出的版本为 KiCad 5.1/5.9；当前工程是 KiCad 9，因此不能把直接导入视为受支持且已验证。
- 官方 EAGLE 导入流程支持 EAGLE 6+ 项目包；仓库已有候选文件 `hardware/easyeda/supercap-ups-4s-eagle.zip`。它可以作为 GUI 导入测试入口，但本轮无法读取 ZIP 内部二进制并且没有实际 JLCEDA GUI 控制能力，**没有执行真实 GUI 导入**。
- 过去静态预检记录过 EAGLE 包 9 页、167 元件、116 nets、486 pin connections；这些计数是静态对照，不是 JLCEDA 导入成功证据。
- Weave 的 `.asc` 不能替代 EAGLE/KiCad 原理图工程，也不能生成 PCB。

操作说明与验收清单见 [JLCEDA 导入指南](../hardware/easyeda/JLCEDA_IMPORT_GUIDE_ZH.md)。

## 五、生产准备结论

| 生产项目 | 状态 | 说明 |
|---|---|---|
| 关键 IC 完整 MPN | 部分完成 | 若干 BOM 后缀不完整；BQ76905/LM339B/74LVC1G74 供货风险 |
| 超级电容采购 | 可采购候选 | 但 85°C 电压降额与 EOL DC ESR 需纳入 |
| Boost 电感 | 不通过 | 当前 CKST0603 典型 Isat 低于 TPS61088 最大限流 |
| 充电电感 | 未完成 | L101 没有冻结 MPN/footprint |
| D101 | 未完成 | 无完整 MPN，热漏电和 CV 余量未验证 |
| BOM | 不通过 | 101 个原理图位号未进入初步 BOM，8 个 BOM 位号不在原理图 |
| Footprint | 不通过 | 72/167 为空，关键 IC 缺 footprint |
| 原理图 ERC | 部分历史证据 | 仅特定页 0/0；全工程未复验 |
| PCB DRC | 不可运行 | 没有 `.kicad_pcb` |
| 嘉立创 GUI 导入 | 未验证 | 有 EAGLE 候选包，无真实 GUI 验收 |
| 生产文件 | 不存在 | 无 Gerber/Drill/CPL/最终 BOM/装配图 |

### 打板前必须关闭

1. 将 TPS2121/eFuse/CP2 reference 真实加入层级原理图，冻结 U902 变体。
2. 解决 BQ76905RGRR 的真实样品采购，确认供应批次。
3. 更换 Boost 电感，取得可追溯的 Isat 最小保证或完成来料分档测试，并复跑 TPS61088 全限流矩阵。
4. 冻结 L101、D101、D801/D802、R101、CIN/COUT 的完整 MPN、封装和保证参数。
5. 把 167 位号全部纳入 BOM，补齐 72 个空 footprint，逐器件核对 pad number / pin number / polarity / exposed pad。
6. 建立真实 PCB，完成高电流回路、超级电容机械间距、热设计、测试点与连接器布局。
7. 在 KiCad 9 重新运行全工程 ERC；完成 PCB DRC；输出 Gerber、钻孔、BOM、CPL 和装配图。
8. 使用实际 JLCEDA GUI 导入 EAGLE 包，逐页、逐网络、逐封装比对；导入成功后再做 JLC DRC 和 BOM/CPL 对照。

**本轮没有购买器件、没有更改主线电路、没有运行真实板级仿真、没有通过 JLCEDA GUI 导入，也没有生成生产文件。**
