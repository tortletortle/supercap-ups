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

- JLCEDA Pro 官方格式转换助手当前明确列出 KiCad 的 .kicad_sch、.kicad_pcb、.kicad_sym、.kicad_mod 和 .pro.kicad_pro 等导入格式；因此“只支持 KiCad 5.1/5.9”的旧说法不成立。文件类型被列为支持不等于本工程 KiCad 9 的每个图元、层级、封装和网络都能无损转换；仍需实际 GUI 导入与逐项核对。
- 官方 EAGLE 导入流程支持 EAGLE 6+ 项目包；仓库已有候选文件 `hardware/easyeda/supercap-ups-4s-eagle.zip`。它可以作为 GUI 导入测试入口，但本轮无法读取 ZIP 内部二进制并且没有实际 JLCEDA GUI 控制能力，**没有执行真实 GUI 导入**。
- 过去静态预检记录过 EAGLE 包 9 页、167 元件、116 nets、486 pin connections；这些计数是静态对照，不是 JLCEDA 导入成功证据。
- Weave 的 `.asc` 不能替代 EAGLE/KiCad 完整工程，也不能生成 PCB。但嘉立创 EDA 专业版官方确实支持 LTspice ASCII `.asc` + 对应 `.asy` ZIP 导入，因此 Weave NET→ASC 可作为仿真 testbench 的导入路径；它不是 KiCad→JLCEDA 的转换器。

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

---

## 第二轮复核修订（2026-11-24，优先于上文旧快照）

本节根据制造商 2025/2026 版资料及重新检索的大陆供应商目录修订上文个别字段。库存均为网页索引快照，不是锁库存或正式报价；价格按页面币种记录，实际下单前必须刷新。

### A. Eaton 超级电容：大陆渠道已找到，但订货后缀需确认

- Eaton 数据手册中的基础制造商料号：HVH1230-2R7206-R。
- DigiKey 中国 HVH 系列页面显示目录料号 HVH1230-2R7206-RCAP，库存 1,576，页面价 ¥15.71/件，MOQ 1；页面索引约 3 周前。这里的 RCAP 与 Eaton 数据手册基础料号后缀 -R 不同，采购前必须让 DigiKey/Eaton 书面确认它是包装/目录扩展还是不同的 orderable MPN。
- 因此，修正前一条消息中“大陆价格未确认”的说法：DigiKey 中国目录确实列出大陆入口与库存快照；但该页面并非实时锁库，且完整订货后缀尚需核对。
- 官方规格：20F ±20%、2.7V；最大 DC ESR 53mΩ@25°C、最大 AC ESR 35mΩ@1kHz、最大漏电 55µA；连续电流 1.92A（温升 15°C），脉冲电流 13A 仅按数据手册 1s 条件定义。温度 -40..70°C；扩展至 85°C 时必须线性降额至 2.5V。
- 85°C 寿命试验条件为 1000h@2.5V：容量保持率 ≥70%，AC ESR ≤初始最大值的 300%。这不是 DC ESR 的寿命保证。模型里的 11.2F/cell 可解释为 20F×80% 初始容差下限×70%寿命保持率；模型里的 106mΩ DC/cell 仍是工程假设，不能声称 Eaton 保证了 EOL DC ESR=106mΩ。
- 9.4V/4=2.35V 的平均单体电压低于 85°C 的 2.5V 降额值，但容量失配/串联不均衡时不能仅靠组端 9.4V 保证每个单体低于 2.5V；单体 OVP 必须保留。

### B. 最新目录快照（网页索引数据，非实时承诺）

| 器件 | 可核对的目录信息 | 采购判断 |
|---|---|---|
| TPS61088RHLR | LCSC CN 页面显示 1,494 件、$1.1702、MOQ1；其他缓存页出现 893–1,571 件 | 有大陆目录入口；库存快照不一致，购买前刷新；封装按 TI RHL drawing |
| TPS2121RUXR | LCSC 页面显示 34,538 件、$1.0571、MOQ1 | 有大陆目录入口，但 U901 尚未进入当前层级原理图 |
| TPS259470ARPWR | LCSC 页面/分类页约 4,487–4,562 件、$1.3874、MOQ1 | 有大陆目录入口；库存缓存差异需刷新 |
| TPS259474LRPWR | LCSC 页面显示 1,754 件、$1.3541、MOQ1 | 有大陆目录入口；只是候选，未批准替换 |
| TPS54302DDCR | LCSC 页面显示 9,355–16,395 件、$0.3033、MOQ5 | 有大陆目录入口；不同缓存页库存差异较大 |
| BQ76905RGRR | DigiKey 中国库存 0，预计 2027-07-26 到货 3,000；LCSC 页面 0 件 | P0 采购阻塞未解除。LCSC $1.0106 仅为参考价，不能当成可下单价格 |
| MWSA1205S-3R3MT | JLCPCB C408513 显示 277 件、可下单 273 件、$0.6753；但注明只进入 PCBA 料库、不可单独发货。DigiKey US 页面另显示 450 件、$1.47 cut tape、16 周标准交期 | JLC 库存不能算散料采购；若不走 JLC PCBA，需海外采购或找 Sunlord 授权代理 |
| MWSA1204S-100MT | DigiKey US 页面显示 311 件、$1.47 cut tape、16 周标准交期；JLCPCB 有 PCBA 器件页 | 海外采购候选；未证明大陆散料现货 |

### C. TPS25947 变体：必须使用 2026 年 5 月 Rev C 数据手册

旧 Rev B（2022-03）比较表对部分 L 变体的显示存在缺项；TI 当前 Rev C（2026-05）明确列出：

| 订货型号 | 过压响应 | 过流响应 | 状态脚 | 故障恢复 |
|---|---|---|---|---|
| TPS259470ARPWR | 可调 OVLO | Active current limit | AUXOFF + FLT | Auto-retry |
| TPS259470LRPWR | 可调 OVLO | Active current limit | AUXOFF + FLT | Latch-off |
| TPS259474ARPWR | 可调 OVLO | Circuit breaker | PG + PGTH | Auto-retry |
| TPS259474LRPWR | 可调 OVLO | Circuit breaker | PG + PGTH | Latch-off |

TPS259474LRPWR 不是“无过流保护”型号。它与当前候选 TPS259470ARPWR 同为 RPW 10-pin 2×2mm QFN-HR，但 pin 3/4 从 AUXOFF/FLT 改为 PG/PGTH，过流策略从主动限流变为断路器，故障恢复从自动重试变为锁存。必须重审 PGTH 电阻、故障锁存/清除、重新武装与 BACKUP_READY；不能只改 BOM。

另一个可考虑的功能替代是 TPS259470LRPWR：保留 470A 的主动限流与 AUXOFF/FLT，只把自动重试改为锁存；同样需要重新验证复位/重新武装时序。

### D. Weave 与嘉立创导入边界修订

1. 嘉立创 EDA 专业版官方格式转换助手列出了 KiCad .kicad_sch、.kicad_pcb、.kicad_sym、.kicad_mod 等格式，也列出 EAGLE .zip/.lbr/.sch/.brd。因此之前“只支持 KiCad 5.1/5.9”的说法不应继续使用；但当前项目的 KiCad 9 实际 GUI 导入仍未验收。
2. 嘉立创 EDA 专业版官方 LTspice 导入说明明确要求将 ASCII .asc 和全部对应 .asy 符号打包成 ZIP 后导入。故 Weave NET→ASC 是有效的 testbench 原理图导入路径，不是 JLCEDA 原生工程转换。
3. test/ltspice-weave-jlc-qualification 的 README 记载：固定 Weave commit bc9b3d3299f3d96fae3f9a1e56de2c639e40c68a，输入 eol_1p2s.cir，使用 synthetic __block21.asy，网络回读为 MATCH；打包器需要从本机 LTspice 库取得 bi/cap/ind/res/voltage.asy，缺失或冲突时拒绝生成 ZIP。该 21-pin 合成符号不是 TPS61088 真实封装引脚/焊盘。
4. 本轮 GitHub API 未取得该分支 HEAD 对应的 workflow run/check 记录（返回空列表）；所以 README 中“Actions 已成功”的描述仍是仓库文档声明，本轮没有重新拿到原始 Actions 日志/Artifact 独立复核。不能把它升级为本轮已复跑证据。
5. 本轮没有 JLCEDA GUI 会话，无法进行实际导入。EAGLE ZIP 在基线树中存在（15,022 bytes），但二进制内容无法在当前审查环境解包检查；不能确认 ZIP 内部究竟有多少 .sch/.brd 文件。

### E. 本轮新增的硬性采购放行规则

- 所有库存与价格必须记录来源页面、币种、MOQ、页面索引时间；网页库存不等于锁库，报价不等于含税到货价。
- Eaton 的 -RCAP 与基础料号 -R 需书面确认。
- Boost/L101 电感不得把数据手册的 Isat Max 或 Typ 直接写成 Isat,min。对 TPS61088，RILIM=100kΩ 时 TI 最大峰值限流为 PFM 13A、FPWM 11.4A；实际 MODE 脚必须按原理图确认。项目采用的 0.8×Isat 裕量是项目筛选规则，不是 TI 或 Sunlord 的保证值。
- BQ76905RGRR 无大陆现货确认前，不安排保护板投产；若转用替代监测器件，需重新做 4S 采样、阈值、延迟、失效默认状态和 5ms 关断验证。
- 当前仍无 .kicad_pcb，因此 DRC/生产文件仍未完成。

官方/供应商来源：
- Eaton HVH 数据手册：https://www.eaton.com/content/dam/eaton/products/electronic-components/resources/data-sheet/eaton-hvh-supercapacitors-cylindrical-cells-high-density-data-sheet-elx1538-en.pdf
- DigiKey 中国 Eaton HVH 系列：https://www.digikey.cn/zh/products/featured/hvh-series-high-density-2-7-v-radial-leaded-supercapacitors/1582341389283022
- TI TPS61088 Rev D：https://www.ti.com/lit/ds/symlink/tps61088.pdf
- Sunlord MWSA-S 数据手册：https://www.sunlordinc.com/uploads/files/20230303/MWSA-S%C2%A0series%C2%A0of%C2%A0SMD%C2%A0Power%C2%A0Inductor.pdf
- TI TPS25947 Rev C：https://www.ti.com/lit/ds/symlink/tps25947.pdf
- DigiKey 中国 BQ76905RGRR：https://www.digikey.cn/zh/products/detail/texas-instruments/BQ76905RGRR/22119523
- LCSC TPS61088RHLR：https://www.lcsc.com/zh-CN/product-detail/DC-DC-Converters_Texas-Instruments-TPS61088RHLR_C87357.html
- LCSC TPS2121RUXR：https://www.lcsc.com/product-detail/Battery-Management-ICs_Texas-Instruments-TPS2121RUXR_C485916.html
- LCSC TPS259470ARPWR：https://www.lcsc.com/product-detail/C3662799.html
- LCSC TPS259474LRPWR：https://www.lcsc.com/product-detail/surge-protection-devices-spds_texas-instruments-tps259474lrpwr_C2864845.html
- LCSC TPS54302DDCR：https://www.lcsc.com/product-detail/C311983.html
- JLCPCB MWSA1205S-3R3MT（PCBA only）：https://jlcpcb.com/partdetail/Sunlord-MWSA1205S3R3MT/C408513
- JLCPCB LTspice 导入说明：https://prodocs.lceda.cn/cn/import-export/import-ltspice/
- JLCPCB KiCad/EAGLE 格式转换支持：https://prodocs.lceda.cn/cn/import-export/easyeda-pro-format-converter/