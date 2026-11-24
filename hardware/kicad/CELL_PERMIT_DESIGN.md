# CELL_PERMIT：4S BQ76905 单体欠压保护专项审计

- 仓库：`tortletortle/supercap-ups`
- 本分支基线：`360508c08f23f63cdd74fba7e0c201b0907d3825`
- 本分支：`cell-permit-uv-protection`
- 设计对象：4S × 20F 超级电容；U801 `BQ76905RGRR`
- 结论等级：**设计/寄存器建议/行为模型完成；硬件 5ms 保证未通过**

## 1. 执行结论

当前设计**不能宣称已经可靠满足 5ms 最坏隔离时间**。原因不是 Python 模型不够快，而是硬件链路中仍存在未被数据手册给出最大值、未实现或未实测的环节：

1. BQ76905 的 ADC slot time 在数据手册中是典型值；LFO 的温漂项有 characterization 数据，但没有可直接组合成全温、全批次生产保证的绝对 ADSCAN 最大值。
2. CUV Alert 到 ALERT 引脚没有找到可用于本预算的最大传播延迟。
3. 原理图没有固化 BQ76905 的寄存器写入/读回证据；默认 `Enabled Protections A=0xA1` 中 CUV 关闭，默认 `Default Alarm Mask=0xC200` 中 SAA 未使能。
4. 现有背靠背 P-MOS 的关断依靠 R501=10kΩ 把栅极拉回源极。按 Si7149DP 最大 Qg 做的一阶等效 RC 估算，栅源电压接近 0V 约需 1.321ms；原模型的 0.4ms 不能代表实际电流隔离。
5. ALERT 开漏线没有接收端断线监督；`CELL_CONFIG_VALID` 是静态主控信号，没有外部心跳超时监督。
6. BQ76905 的 COW 开线检测是低占空比脉冲检测，不是 5ms 保护路径。按现有 220nF 输入电容和 55µA 典型 COW 电流估算，从 2.7V 放电到 1.05V 可能需要约 0.58s；该结果不是最大保证值。

**最快 BQ 路径的工程估算约 4.265ms，但仍是估算，不是可签核的最大值。** 如果将 ADC 设置留在 medium-fast，或把 LOOP_SLOW 设为半速，则使用“栅源接近 0V”判据时模型已经超过 5ms。

## 2. 基线事实与现有实现

### 2.1 本分支审计的基线文件

- `hardware/kicad/cell-uv-monitor.kicad_sch`
- `hardware/kicad/system-interlock.kicad_sch`
- `hardware/kicad/pack-discharge-switch.kicad_sch`
- `hardware/kicad/cell-uv-monitor-design.md`

基线中已经存在 BQ76905 监测原理图；原设计说明中“尚未落图”的状态文字已过期。本专项没有改动主原理图、主备切换原理图或其他模块。

### 2.2 原理图可观察事实

- U801：BQ76905RGRR。
- 4S 电压输入按 BQ76905 的 4S 模式映射：Cell1=VC1−VC0，Cell2=VC2−VC1，Cell3=VC4B−VC3A，Cell4=VC5−VC4A；未使用的 VC4A/VC4B、VC3A/VC3B、VC3B/VC2 连接按器件 4S 配置要求处理。配置写入后仍须用实际引脚电压和寄存器读回确认。
- 单体输入网络采用 10Ω 串联电阻和 220nF 电容；每个差分单体输入两端各经过一个 10Ω，名义差分 RC 时间常数约 `20Ω × 220nF = 4.4µs`。
- ALERT 为开漏、低有效，原理图有 10kΩ 上拉到 CELL_3V3。
- U914：TPS3839G33，监控 REGOUT 电源。
- `CELL_CONFIG_VALID`、`MANUAL_ARM_REQ` 有 100kΩ 下拉，主控复位/高阻时默认低。
- 放电开关 Q501/Q502 为 Si7149DP 背靠背 P-MOS；Q503/Q504 为 AO3400A 串联下拉控制。
- R501=10kΩ，为 P-MOS 栅源恢复电阻；R502=1kΩ，为使能下拉支路电阻。
- U910：SN74LVC1G74，利用异步清零锁存 DISCHARGE_ARM。
- BQ76905 的 DSG 引脚在当前图中未接入实际放电 MOS 栅极；不能把 BQ 内部 DSG 保护配置当作已经切断了当前 P-MOS 放电路径。

### 2.3 尚未发现的实现证据

在共同基线中没有找到以下可验收证据：

- BQ76905 固件寄存器配置源文件；
- 上电 CONFIG_UPDATE、寄存器写入和逐项读回日志；
- 4S Vcell Mode 的实测读回；
- `AlarmEnable()` 中 SAA 的读回；
- `ADSCAN` 新鲜度监控；
- `CELL_CONFIG_VALID` 与 BQ POR/复位状态之间的实测闭环；
- ALERT 断线/卡高测试；
- MOS 关断电流实测波形。

因此当前状态为“原理图已存在、配置建议已形成”，不是“寄存器已实现”。

## 3. BQ76905 配置审计

以下默认值与字段依据 TI BQ76905 数据手册及 Technical Reference Manual。写入建议必须在固件中按 CONFIG_UPDATE 流程实施，并在退出 CONFIG_UPDATE 后读回；不能只把 CSV 当作芯片已经配置。

### 3.1 默认配置风险

| 项目 | 默认值 | 风险 |
|---|---:|---|
| Power Config | `0x01` | SLEEP_EN 默认置位 |
| REGOUT Config | `0x08` | REG_EN=1，但 REGCTL=0；不能假定为 3.3V |
| DA Config | `0x0000` | CV/I/Shared ADC speed 默认慢速 |
| Vcell Mode | `0x00` | 不是明确的 4S 模式 |
| Enabled Protections A | `0xA1` | CUV bit6 默认关闭 |
| Default Alarm Mask | `0xC200` | SAA bit13 默认关闭 |
| CUV Threshold | 2500mV | 与超级电容候选阈值不匹配 |
| CUV Delay | 10 ADSCAN | 不是最短设置 |
| CUV Recovery | `0x02` | 100mV 自主恢复 |
| COW NORMAL Check Time | `0x00` | 开线检测默认关闭 |
| Enabled Protections B | `0x00` | Host Watchdog 默认关闭 |

**关键逻辑：** BQ76905 的 Safety Alert A 会在首次检测到 CUV 时产生；Safety Status A 的 CUV 故障状态受 CUV Delay 控制。若要用 ALERT 首次告警异步清除外部锁存，必须把 SAA 纳入 Alarm Enable。默认 `0xC200` 不包含 bit13，因此“ALERT 引脚已经连线”不等于“CUV 能拉低 ALERT”。

### 3.2 欠压阈值与迟滞

项目候选 CUV 阈值为 1050mV。BQ76905 数据手册全温 cell-voltage accuracy 项给出的误差范围为约 ±9.8mV；按该误差单独折算，实际单体电压触发点约落在 **1040.2–1059.8mV**。这不是包含外部电阻/电容误差、动态负载压降和采样噪声的完整阈值误差预算。

`CUV Recovery Hysteresis=0` 的意义是关闭自动恢复，不应解释成“0mV迟滞并自动恢复”。故障解除后仍需主控清故障并经过硬件 ARM 低→高重新武装。阈值是否足以保护 Eaton 4S×20F 最弱单体，还需与能量预算/放电截止阈值统一确认。

### 3.3 候选寄存器配置

| 数据存储器/命令 | 地址 | 候选值 | 说明 |
|---|---:|---:|---|
| Power Config | `0x9014` | `0x04` | LOOP_SPEED=0、CB_LOOP_SPEED=0；SLEEP_EN=0；LFOWD=1（需验证 LFO watchdog shutdown 时 REGOUT/PG 的实际默认态） |
| REGOUT Config | `0x9015` | `0x0E` | REG_EN=1、REGCTL=6，目标 3.3V |
| I2C Config | `0x9017` | `0x3401` | CRC=1；仅当 MCU CRC 实现已验证时使用 |
| DA Config | `0x9019` | `0x003F` | CVADCSPEED/IADCSPEED/SSADCSPEED 全部设为最快 |
| Vcell Mode | `0x901B` | `0x04` | 4S |
| Default Alarm Mask | `0x901C` | `0xE205` | SAA、SSB、SSA、SHUTV、INITCOMP、POR |
| Enabled Protections A | `0x9024` | `0xE1` | 保留 COV/SCD/REGOUT，增加 CUV |
| Enabled Protections B | `0x9025` | `0x01` | 开启 HWD；仅作辅助 |
| DSG FET Protections A | `0x9026` | `0xFF` | 保留 CUV 对 DSG 的保护位；当前 DSG 未接功率 MOS |
| COW NORMAL Check Time | `0x902B` | `0x01` | 最小非零 COW 检查间隔 |
| COW SLEEP Check Time | `0x902C` | `0x10` | COWDLY=1ms；SLEEP COW 未启用 |
| Host Watchdog Timeout | `0x902D` | `0x01` | 1s；远大于 5ms |
| CUV Threshold | `0x902E` | `1050mV` (`1A 04`) | 项目候选阈值 |
| CUV Delay | `0x9030` | `0x01` | 1 ADSCAN |
| CUV Recovery Hysteresis | `0x9031` | `0x00` | 禁止自动恢复 |
| Alarm Enable() | `0x66` | `0xE205` | 每次启动配置后写入并读回 |

注意：
- `Default Alarm Mask` 如果没有写入 OTP，复位后不能假定保留；主控每次启动必须重写并读回。
- `Alarm Enable()` 必须在 `CELL_CONFIG_VALID` 置高之前配置完成。
- `0xE1` 保留了 COV 使能，但 COV 阈值由充电/OVP 专项负责。本专项不擅自修改 COV 阈值。不得在 COV 阈值仍为 BQ 默认 4.2V 时把整套监测配置签为完成。
- HWD 最小超时为秒级，不是 5ms 保护路径。
- 当前 DSG 引脚未接放电 MOS；`DSG FET Protections A` 的配置不能替代外部 P-MOS 锁存链。

## 4. 5ms 时间预算

### 4.1 ADSCAN 计算

4S 正常扫描包含 4 个 cell slots 和 1 个 Shared Slot，即 5 个活动槽。TI 给出的典型转换时间：

| ADC speed | 典型 slot time | 4S 五槽时间（不含 COWDLY） |
|---|---:|---:|
| Fast | 366µs | 1.830ms |
| Medium-fast | 732µs | 3.660ms |
| Slow | 2.930ms | 14.650ms |

TI LFO 全温频率漂移表给出 -2.1% 至 +2.3% 的 characterization 范围。用 -2.1% 推算慢时钟，Fast slot 的派生值约 373.85µs，五槽约 1.869ms。**这是由典型转换时间和 characterization 漂移推导的工程上界估算，不是全批次生产保证的 ADSCAN 最大值。**

当启用 COW 且 COWDLY=1ms 时，模型每个 ADSCAN 另加 1ms，候选 Fast ADSCAN 周期约 2.869ms。若实际 `SSADCSPEED` 没有设为 Fast，共享槽可能成为主要瓶颈，因此 DA Config 的三个 speed 字段必须一起读回确认。

### 4.2 输入 RC

原理图 10Ω 串联电阻按 +1%、220nF 电容按 +10% 估算：

- 差分 R：20.2Ω；
- C：242nF；
- τ：4.888µs；
- 5τ：24.44µs。

这是从候选元件容差计算的输入网络稳定时间，不包含电容直流偏压、实际布局寄生和 BQ 输入采样内部行为的实测影响。

### 4.3 P-MOS 关断估算

Vishay Si7149DP 数据表给出：
- VGS(th)：最小 1.2V、最大 2.5V，测试电流 250µA；
- Qg：在 VDS=-15V、VGS=-10V、ID=-10A 条件下典型 98nC、最大 147nC；
- 动态参数脚注注明由设计保证、非生产测试项目。

现有两只 P-MOS 共用栅极。按 R501=10kΩ（+1%）、R502=1kΩ（-1%）推算，9.4V 组压下初始 |VGS| 约 8.56V。用两只器件的 Qg(max)/10V 构造总等效电容 29.4nF，得到：
- |VGS| 降到 1.2V：约 0.583ms；
- |VGS| 降到 0.1V：约 1.321ms。

这里的 0.1V 是“栅源接近相等”的工程关断代理判据，不等于已经实测电流为零。Qg 测试条件与实际 4S 工作点不同，等效电容是简化模型；**不能把 1.321ms 当作数据手册保证的 MOSFET 关断最大值。**

### 4.4 估算汇总

候选 Fast + COWDLY=1ms + 现有 P-MOS 栅极网络：

| 阶段 | 估算 |
|---|---:|
| 最坏相位等待下一次单体采样 | 2.869ms |
| 输入 RC 稳定（5τ） | 0.024ms |
| ALERT 内部/引脚传播 | 0.050ms（假设，无数据手册最大值） |
| AND/DFF 控制链 | 0.0001ms（假设，未做全链路时序测量） |
| P-MOS 栅源到 |VGS|≤0.1V | 1.321ms |
| **合计** | **4.265ms（估算）** |

这个结果表面上小于 5ms，但只有约 0.735ms 余量，而且至少三项没有可用于签核的最大值。因此结论是：**模型估算通过，最坏时间保证未通过。**

对照：
- 旧 4.06ms 算术可复现：`5 × 732µs + 0.4ms = 4.06ms`。但它没有覆盖 5τ 输入稳定、ALERT 最大传播、真实 P-MOS 完全关断和负载电流实测。
- Medium-fast + 现有栅极近零判据，模型约 5.134ms，失败。
- Fast + LOOP_SLOW 半速 + COWDLY=1ms，模型约 6.13ms，失败。
- 默认 Slow 转换远超 5ms。
- 慢扫描约 29.7ms 的历史结果属于慢速配置模型，不可用于当前 Fast 配置，也不能证明硬件通过。

## 5. 开线检测不是 5ms 保护路径

BQ76905 COW 检查电流只在 Shared Slot 中短时开启，并非连续 55µA 放电。4S 需要多个 ADSCAN 才能轮询所有 cell inputs；完成一轮后还要按 COWNTIME 等待 FULLSCAN 间隔。

按以下工程参数做一阶估算：
- Shared Slot：Fast，约 373.85µs；
- COW 电流：55µA（典型值，不是最大/最小保证）；
- 输入电容：220nF +10%；
- COWNTIME=1，按 4S 一轮 5 ADSCAN + 5 ADSCAN 休止估算；
- 浮空输入从 2.70V 降到 1.05V。

每个脉冲只使 242nF 电容下降约 85mV，需要约 20 个脉冲；单个 cell 的脉冲间隔约 10 ADSCAN。模型结果约 **576.7ms**。即使浮空输入刚好在 1.051V 附近，估算也约 31.6ms。

这不是开线检测最大时间，但足以说明：**BQ COW 不能作为 5ms 级断线保护。** 如果运行时单体采样线可能断开，必须增加独立线路完整性监督/偏置检测，并在开线状态下异步撤销 CELL_PERMIT。仅在固件里打开 COW 不够。

## 6. CELL_PERMIT 接口定义

### 6.1 信号语义

`CELL_PERMIT` 为高有效组合许可；任意监测无效或保护故障都必须拉低。它不直接代替 ARM 锁存器。

建议定义：
```text
CELL_PERMIT =
    CELL_MON_PG
  & CELL_CONFIG_VALID
  & CELL_HEARTBEAT_OK
  & CELL_ALERT_LINE_OK
  & CELL_MON_ALERT_L
  & CELL_OPENWIRE_OK
  & CELL_ADC_DIAG_OK
  & CELL_POR_CLEAR
  & CELL_COMM_OK
  & CELL_UV_OK
  & CELL_OV_OK
```

其中：
- `CELL_MON_PG`：REGOUT 监控电源有效。
- `CELL_CONFIG_VALID`：4S 模式、阈值、保护使能、报警掩码和 ADC 配置均写入且读回一致。
- `CELL_HEARTBEAT_OK`：外部硬件 watchdog 仍在超时窗口内；心跳只能在主控成功读取并检查 BQ 状态/测量后发出。
- `CELL_ALERT_LINE_OK`：物理 ALERT 引脚与 BQ BatteryStatus 的 ALERTPIN 状态一致，且线路断线监督正常。
- `CELL_MON_ALERT_L`：BQ ALERT 开漏低有效；高表示没有已屏蔽的报警。
- `CELL_OPENWIRE_OK`：所有 cell taps 的开线诊断通过；BQ COW 单独不能提供 5ms 保证。
- `CELL_ADC_DIAG_OK`：VREF/VSS/ADC 等诊断无故障。
- `CELL_POR_CLEAR`：复位/POR 已识别，初始化和配置完成。
- `CELL_COMM_OK`：I2C 读写、CRC（若启用）、状态读回均有效。
- `CELL_UV_OK/CELL_OV_OK`：单体欠压/过压保护状态正常。

总控侧建议：
```text
ARM_PERMIT = CELL_PERMIT & PACK_UV_OK & CTRL_SUPPLY_OK
```

### 6.2 锁存和重新武装

- 任一许可输入变低，异步清除 `DISCHARGE_ARM_LATCHED`。
- 故障解除、ALERT 恢复高、通信恢复，不允许自动恢复放电。
- 重新武装必须观察到 `MANUAL_ARM_REQ` 先低后高，并且 `CELL_PERMIT=1`。
- MCU 复位、BQ POR、REGOUT 欠压、I2C 错误、ALERT 线路异常、开线故障都必须保持默认禁止放电。
- `CELL_CONFIG_VALID` 必须由下拉电阻建立默认低；它不能单独承担 MCU 卡死保护。

### 6.3 ALERT 线路监督

当前 ALERT 是开漏，只有上拉。建议：
- 保留 BQ 侧 10kΩ 上拉；
- 在接收逻辑侧增加约 100kΩ 下拉，使线束/走线开路时接收端默认低；
- MCU 定期读取 BatteryStatus 的 ALERTPIN 位，并与物理 GPIO 采样比较；
- 若内部 ALERTPIN 表示低而物理线仍高，撤销 `CELL_CONFIG_VALID` 并停止外部 heartbeat。

100kΩ 下拉会与 10kΩ 上拉形成约 3.0V 高电平（3.3V 电源），需核对接收门 VIH、上拉位置和实际走线后再改图。

## 7. 故障覆盖结果

`sim/cell_permit/test_model.py` 覆盖逻辑 fail-closed：
- 单体欠压；
- 单体检测线开路；
- BQ 复位/POR；
- I2C/CRC 通信错误；
- 监测电源掉电；
- ALERT 断线/卡高和正常拉低；
- MOS 关断延迟场景；
- 故障解除但 ARM 一直保持高；
- ARM 低→高重新武装。

这些是独立 Python 行为模型测试，不是芯片实测或 SPICE 通过。开线、复位、通信、ALERT 卡高的逻辑用例通过，表示接口模型能拒绝故障输入；当前原理图尚未提供所有对应硬件信号，因此不能标为硬件测试通过。

## 8. 硬件替代方案

### A. 最小修改：保留 BQ ADC，强化关断链

1. 固定 `DA Config=0x003F`、Power Config 全速且禁用 SLEEP，固件逐项读回。
2. 确认 SAA 使能，使用 ALERT 首次告警异步清除硬件锁存。
3. 给 ALERT 增加接收端断线下拉和物理/内部状态比较。
4. 增加外部 heartbeat watchdog。候选可研究 ADI LTC6993-2 可重触发单稳态：可编程 1µs–33.6s，N_DIV≥512 时最大脉宽误差 ±2.3%，4ms 设置的上边界约 4.092ms。主控只有在完成新鲜 BQ 状态/扫描检查后才发脉冲。该器件是候选，不是已选型/已验证。
5. 把现有 10kΩ 被动栅源恢复改成高边参考的主动栅源钳位/推挽关断级，目标实测关断 <50µs。必须验证掉电默认态、VGS 绝对最大值、误触发和 MOS 反向电流。

仅做 A 仍不能让 BQ ADC/ALERT 的未保证最大延迟变成保证值。

### B. 独立硬件单体欠压比较器

可研究每节一个高共模差分测量通道：
- 4 × INA149：5V 单电源下 common-mode 输入范围 -20V 至 +25V，覆盖 4S 0–9.4V 节点；最大输入失调 1.1mV、增益误差 0.02%、500kHz 典型带宽。
- 1 × TLV1704：四路比较器，2.2–36V 供电、轨到轨输入、开漏输出；传播延迟 560ns 为典型值，不是最大值。
- 每路 INA149 以参考端偏置，将单体差分电压转换到比较器有效共模范围，再与 1.05V 阈值对应参考比较。
- 四路比较器输出 wired-OR 到异步故障锁存器；任何一路欠压直接清除 ARM。

该方案可把 UV 检测从 BQ ADSCAN 中解耦，但仍需完成：
- INA149 单电源参考偏置与输出摆幅设计；
- 5V 监测电源在 7–9.4V pack 全范围的供电设计；
- 失调、CMRR、参考误差、比较器偏移的完整阈值误差预算；
- 单体 tap 开路时比较器输入默认态设计；
- 高共模瞬态、输入 RC 和噪声误触发验证。

目前只是器件级架构候选，未生成或验证可投板原理图。

### C. BQ DSG 直接驱动低边 N-MOS

BQ76905 DSG 驱动器可直接控制低边 N-MOS，可能缩短驱动链，但当前设计是高边背靠背 P-MOS，DSG 未接。改成低边断开会改变系统地参考，需检查：
- 主备电源是否共地或存在旁路回流；
- MCU/USB/通信接口是否绕过低边开关；
- 充电回路和测量参考是否被破坏；
- 关断后是否仍有体二极管/ESD/接口回流路径。

因此不建议把 DSG 直接接到现有 P-MOS 栅极；若考虑低边 N-MOS，必须作为拓扑变更重新评审。

## 9. 当前验收结论

| 验收项 | 状态 |
|---|---|
| 现有原理图审计 | 完成 |
| 默认寄存器配置审计 | 完成 |
| 候选 BQ76905 寄存器配置表 | 已形成，未写入实物 |
| 4.06ms 算术复现 | 通过 |
| 5ms 最坏时间保证 | **未通过** |
| Python 独立行为模型 | 19 项测试通过 |
| COW 开线检测 5ms | **失败/不适用** |
| ALERT 断线/卡高硬件监督 | 未实现 |
| 外部 heartbeat watchdog | 候选方案，未实现 |
| P-MOS 实际电流隔离 | 未实测 |
| ngspice/SPICE | 本机未运行；分支 CI 已配置运行简化 RC deck，尚待取得 Actions 实际运行证据 |
| 实物测试 | 未进行 |

## 10. 下一步必须完成

1. 固件团队按本报告写入并读回寄存器；保留启动日志、所有读回值和 POR/INITCOMP 处理。
2. 电源总控确认 `CELL_PERMIT`、`CELL_HEARTBEAT_OK`、`CELL_ALERT_LINE_OK` 接口接入系统互锁。
3. 选定并实现外部 watchdog；不能使用 1s BQ HWD 代替 5ms。
4. 对 ALERT 接收端增加断线监督。
5. 设计主动 P-MOS 栅源钳位；对 7.0V、9.0V、9.4V pack、电容最坏值、温度角点做瞬态仿真。
6. 评估独立四路单体比较器方案，特别是 tap open 失效态。
7. 台架以最弱单体实际跨过 1.05V 为触发，测量 ALERT、DFF Q、P-MOS VGS 和 PACK 支路电流。建议先把“实际隔离”验收定义为 PACK 支路电流降到 10mA 以下并保持 100µs；该阈值需总控批准。
8. 未取得最大时延证据或台架最坏值之前，不得签核 5ms。

## 11. 官方资料

- TI BQ76905 数据手册：<https://www.ti.com/lit/ds/symlink/bq76905.pdf>
- TI BQ76905 Technical Reference Manual：<https://www.ti.com/lit/ug/sluuci8a/sluuci8a.pdf>
- Vishay Si7149DP 数据手册：<https://www.vishay.com/docs/68934/si7149dp.pdf>
- TI INA149 数据手册：<https://www.ti.com/lit/ds/symlink/ina149.pdf>
- TI TLV1704 产品/数据手册：<https://www.ti.com/product/TLV1704>
- ADI LTC6993-1/-2 数据手册：<https://www.analog.com/media/en/technical-documentation/data-sheets/LTC6993-6993-1-6993-2-6993-3-6993-4.pdf>
