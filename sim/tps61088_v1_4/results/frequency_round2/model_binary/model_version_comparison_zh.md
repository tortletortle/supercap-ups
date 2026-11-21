# TPS61088 普通型号官方模型二进制对照（V1.4 第二轮）

审计日期：2026-11-21。审计仓库基线：
f24cf8e72681097c2e148064ddd3cb6ca5f1704c。
本项仅做文件获取、校验与源码差异审计；未替换仓库模型，未运行仿真。

## 结论

本次从 TI 官方下载服务取得 SLVMDA9 与 SLVMAU6A 两个完整 ZIP。
两包内部 LIB 的原始哈希不同，但唯一差异是换行编码：SLVMDA9 使用 439 个 CRLF，SLVMAU6A 使用 439 个 LF。
把前者 CRLF 转为 LF 后，整个 LIB（含注释）逐字节相同。27 个子电路的端口、参数、逻辑行和正文均相同。
因此，没有发现这两个下载包之间可用于解释首轮频率偏差的电路或行为版本差异。
这项结论仅排除“两个包包含不同版本电路内容”这一解释；不能据此认定宏模型无缺陷，也不能确认 LTspice 与原生 PSpice 的行为相同。

## 官方获取记录

普通型号产品入口：https://www.ti.com/product/TPS61088 。
此次重新读取该产品页及多个区域/查询变体均返回 HTTP 404；没有声称成功刷新产品页。
下载使用既有普通型号资源编号对应的 TI 官方 ZIP 服务，二者均得到 HTTP 200、application/zip，且 ZIP CRC 全部通过。
ZIP 内模型头部器件均为 TPS61088；未获取或使用 TPS61088-Q1 替代模型。
完整尝试、最终 URL、UTC 时间和允许保留的响应头在 download_attempts.json。

| 项目 | SLVMDA9 | SLVMAU6A（包标签 Rev. A） |
|---|---|---|
| 官方下载入口 | https://www.ti.com/lit/zip/slvmda9 | https://www.ti.com/lit/zip/slvmau6a |
| 获取 UTC | 2026-11-21T08:41:30.353829+00:00 | 2026-11-21T08:41:31.356558+00:00 |
| ZIP 字节数 | 4,826 | 89,888 |
| ZIP 文件/目录条目数 | 1 / 1 | 10 / 7 |
| LIB 内部路径 | TPS61088_lib/TPS61088.lib | SLVMAU6/TPS61088_PSPICE_TRANS/TPS61088_TRANS.LIB |
| LIB 原始字节数 | 16,799 | 16,360 |
| LIB 换行 | 439 × CRLF | 439 × LF |
| ZIP 完整性检查 | 通过 | 通过 |
| ZIP 加密标记 | 全部条目未设置 | 全部条目未设置 |

SLVMDA9 ZIP SHA-256：
6636d108c3abca3086c14c006b01e373ab8f3d57bf3be299aa9df30e5b857432

SLVMAU6A ZIP SHA-256：
39f724accc32b8930e06c9f7a979fef5e3163ccd1e2ac027e10f546e7d624ce1

SLVMDA9 原始 LIB SHA-256：
8361a8a007780942f484a180f791b0712504b99d186ab12546bf5d44bc5ebba5

SLVMAU6A 原始 LIB SHA-256（亦为两者统一 LF 后的 SHA-256）：
27a088f856aaaf4219a494582fba73a801650d7bae09b5b7fd77023c791ebdf0

ZIP 中逐文件的解压大小、压缩大小、CRC32、SHA-256 与加密标记见 zip_inventory.csv。
SLVMAU6A 除 LIB 外还含 OLB、DSN、OPJ 与 STARTUP / LOAD_TRANS 工程；较大包大小来自工程材料，不能据此推断模型更新。
HTTP Last-Modified 分别为 2020-03-19、2020-05-12，不能把它们当作 LIB 内部电路版本日期。

## 模型版本与子电路

两份 LIB 的共同头部：

| 字段 | 内容 |
|---|---|
| Part | TPS61088 |
| Date | 11MAY2015 |
| Model Type | TRANSIENT |
| Simulator / Version | PSPICE / 16.2.0.p001 |
| EVM | TPS61088EVM-677 |
| Datasheet | SLVSCM8 |
| Model Version | Final 1.00 |

Rev. A 是发布包的修订标记；两份 LIB 的内部模型版本仍为 Final 1.00。
未发现 .PROTECT / ENCRYPT 标记，模型文本可直接读取。
主子电路均为 TPS61088_TRANS，端口顺序：

    AGND BOOT COMP EN FB FSW ILIM MODE NC_0 NC_1 PGND SS
    SW_0 SW_1 SW_2 SW_3 VCC VIN VOUT_0 VOUT_1 VOUT_2

subcircuit_comparison.csv 列出全部 27 个子电路的声明、逻辑内容哈希与比较结果；全部相同。
仅统一换行后的 official_models_lf.diff 是零字节文件，表示无任何剩余文本差异。

FSW、ILIM、软启动与 MODE 路径也逐字节一致，例如共同源码中的：

- 第 150 行 E_U5_ABM9：U5_TSW = 23p × V(SW) / V(U5_IFSW) / 4。
- 第 162 行 C_U5_C1：AGND 与 U5_N01584 之间为 23p。
- 第 214 行 X_U5_H1：FSW U5_N01584 U5_IFSW AGND OFF_TIMER_U5_H1。
- 第 117 行 ILIM 电流检测；第 123–128 行 SS；第 44、54、107 行 MODE 路径。

这些语句支持继续检查 FSW 定时波形，但源码相同本身不证明某一偏差根因。

## 与仓库适配模型的精确关系

当前仓库 sim/tps61088_v1_3/model/TPS61088_LT.LIB 为 16,352 字节，SHA-256：
418466fbd205f9e9ec487bee1d9c1ada48858ff49eef67767e84706966fa1795

对本次新下载的 SLVMAU6A 原始 LIB 仅作以下两个字节替换，各出现一次：

1. (2.35-6m) → 2.344（V_U2_V3）
2. (1.48+6m) → 1.486（V_U2_V4）

所得文件与仓库适配模型逐字节相同。完整两处差异保存在 official_to_repository.diff。
没有发现额外参数、FSW、ILIM 或端口顺序修改。
因此，首轮记录的 ZIP 哈希 39f724...24ce1 现在可由本次实际取得的字节明确对应至 SLVMAU6A；此前“ZIP 名称未确认”的状态已被新证据补齐。
这里的等值表达式化简证明文件来源关系，不能代替跨求解器功能回归。

## 复核与判断边界

使用标准库复核：

    py -3 audit_models.py --repo <仓库路径> --artifact-dir <本审计文件夹>

脚本从保留 ZIP 重新读取字节、验证获取记录哈希、逐项检查 CRC、生成全部 CSV/JSON/diff，最后断言换行归一后相等、全部子电路相等以及两处替换后与仓库相等。
model_comparison.json 保留机器可读结果。
原始 ZIP 与已解压材料保持独立；不覆盖仿真基线。

本项已验证文件来源和源码差异，未做原生 PSpice 与 LTspice 交叉仿真，也未证明实际器件效率、频率或电感饱和安全。
频率偏差仍需结合本轮三组频率对照与 FSW probe 的真实 RAW / 日志判断。
