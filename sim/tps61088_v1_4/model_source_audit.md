# TPS61088 官方模型资源核验记录

核验日期：2026-11-21  
项目器件：TPS61088（非 Q1）  
当前基线模型：sim/tps61088_v1_3/model/TPS61088_LT.LIB

## 官方资源页可观察事实

TI 普通 TPS61088 产品页列出：

| 资源 | 页面名称 | 页面标示大小 | 状态 |
|---|---|---:|---|
| SLVMDA9.ZIP | TPS61088 Unencrypted PSPICE Transient Model | 4 KB | 产品页可见；本轮未取得 ZIP 二进制 |
| SLVMAU6A.ZIP | TPS61088 Unencrypted PSpice Transient Model Package (Rev. A) | 87 KB | 产品页可见；本轮未取得 ZIP 二进制 |

来源：https://www.ti.com/product/TPS61088

页面亦在 TPS61088-Q1 产品页列出 SLVMAU6A Rev. A，但这不能把当前项目器件改称 Q1。本项目的器件与验证基线仍为普通 TPS61088。

## 当前仓库模型的可观察事实

当前 LIB 文件头部标注：
- Part: TPS61088
- Model Type: TRANSIENT
- Simulator: PSPICE
- Simulator Version: 16.2.0.p001
- EVM: TPS61088EVM-677
- Datasheet: SLVSCM8
- Model Version: Final 1.00
- Date: 11MAY2015

首轮运行环境记录给出的哈希：

| 对象 | SHA-256 |
|---|---|
| 仓库适配后 TPS61088_LT.LIB | 418466fbd205f9e9ec487bee1d9c1ada48858ff49eef67767e84706966fa1795 |
| 适配前 TI 原始 LIB | 27a088f856aaaf4219a494582fba73a801650d7bae09b5b7fd77023c791ebdf0 |
| 首轮本机归档中的 TI ZIP | 39f724accc32b8930e06c9f7a979fef5e3163ccd1e2ac027e10f546e7d624ce1 |

首轮环境记录没有保留该 ZIP 的文件名，因此最后一个哈希不能归属于 SLVMDA9 或 SLVMAU6A。此前 compatibility.md 把 ZIP 哈希误标为 LIB 哈希，已在本分支修正。

当前兼容文件记录了两处 PSpice 表达式改写：
1. (2.35-6m) → 2.344
2. (1.48+6m) → 1.486

当前模型与官方原始 LIB 的完整差异仍需从两份原始文件逐项复核；不要仅凭这两条说明断言不存在其他差异。

## 本轮未完成项

TI 搜索结果确认两个官方资源仍列在产品页，但下载服务没有向本轮检索提供可验证的 ZIP 文件字节。因此本轮没有：
- 取得 SLVMDA9.ZIP；
- 取得 SLVMAU6A.ZIP；
- 列出两份 ZIP 的内部文件；
- 计算两份下载包及内部 LIB 的 SHA-256；
- 比较模型版本、参数、子电路和加密状态；
- 执行原生 PSpice 交叉仿真。

以上均为 pending，不可写成“已比较”或“版本一致”。

## 后续核验步骤

1. 在可正常下载 TI 资源的 Windows 工作环境中，分别下载两个产品页资源。
2. 对下载文件保存最终 URL、UTC 下载时间、字节数、SHA-256。
3. 列出 ZIP 内全部文件，分别计算 LIB/模型文件 SHA-256。
4. 对比当前仓库 LIB、适配前原始 LIB、两个 ZIP 内模型；将注释差异与电路参数/行为差异分开。
5. 检查 .SUBCKT 端口顺序、FSW/ILIM/软启动/模式选择相关表达式及加密状态。
6. 若本机有原生 PSpice，用相同四个频率测试网表或等价测试台交叉验证；没有则明确报告工具限制。
7. 现有模型继续作为固定基线，下载模型放在独立目录，未经 diff 和回归不得覆盖当前模型。

## 技术判断边界

TI Rev. D 数据手册频率公式为：

R_FREQ = 4 × (1/f_SW − t_DELAY × V_OUT/V_IN) / C_FREQ

其中 C_FREQ=23 pF、t_DELAY=89 ns。本轮首个 LTspice 案例在 VIN=7 V、VOUT 约 12 V、RFSW=324 kΩ 时测得 442.336 kHz，而公式计算为 496.137 kHz。该偏差是真实存在于本次宏模型波形中的观察结果，但根因尚未定位。不能在尚未完成模型二进制对照、RFSW 多点对照和数值敏感性实验前，归因于某一个模型包或 LTspice。
