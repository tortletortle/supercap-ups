# TPS61088 官方模型资源核验记录

更新：2026-11-21，V1.4 第二轮。器件为普通 TPS61088。

已从 TI 官方 ZIP 服务重新下载 SLVMDA9 与 SLVMAU6A Rev. A，验证 ZIP CRC、内部文件哈希和全部 27 个子电路。**两份 LIB 的差异仅为 CRLF/LF；统一换行后全文逐字节相同。** 未发现可用“两个下载包电路版本不同”解释频偏的证据。

完整证据：[中文版本对照报告](results/frequency_round2/model_binary/model_version_comparison_zh.md)、[获取记录](results/frequency_round2/model_binary/download_attempts.json)、[机器可读比较](results/frequency_round2/model_binary/model_comparison.json)、[ZIP 逐项清单](results/frequency_round2/model_binary/zip_inventory.csv)、[子电路对照](results/frequency_round2/model_binary/subcircuit_comparison.csv)。

## 获取过程与身份

普通型号入口为 https://www.ti.com/product/TPS61088 。本次刷新该页及几个变体返回 HTTP 404；不能声称本轮成功读取产品页。采用既有普通型号资源编号，通过 TI 官方 https://www.ti.com/lit/zip/slvmda9 与 https://www.ti.com/lit/zip/slvmau6a 取得完整二进制，均 HTTP 200。未使用 TPS61088-Q1 页面或模型替代。最终 URL、UTC 时间、字节数和允许保存的响应头见获取记录。

| 对象 | 字节数 | SHA-256 |
|---|---:|---|
| SLVMDA9 ZIP | 4,826 | 6636d108c3abca3086c14c006b01e373ab8f3d57bf3be299aa9df30e5b857432 |
| SLVMAU6A ZIP | 89,888 | 39f724accc32b8930e06c9f7a979fef5e3163ccd1e2ac027e10f546e7d624ce1 |
| SLVMDA9 内部 TPS61088_lib/TPS61088.lib | 16,799 | 8361a8a007780942f484a180f791b0712504b99d186ab12546bf5d44bc5ebba5 |
| SLVMAU6A 内部 SLVMAU6/TPS61088_PSPICE_TRANS/TPS61088_TRANS.LIB | 16,360 | 27a088f856aaaf4219a494582fba73a801650d7bae09b5b7fd77023c791ebdf0 |
| 当前仓库 TPS61088_LT.LIB | 16,352 | 418466fbd205f9e9ec487bee1d9c1ada48858ff49eef67767e84706966fa1795 |

首轮已有的 ZIP 哈希 39f724...24ce1 现由新下载字节明确对应 SLVMAU6A。它仍然是 ZIP 哈希，不能标为 LIB 哈希。早期文档“未取得二进制、无法归属”的状态已被本次证据更新；首轮原始环境记录保持不变。

## 内容与适配

两包共同模型头部：TPS61088、TRANSIENT、PSPICE 16.2.0.p001、TPS61088EVM-677、SLVSCM8、Final 1.00、11MAY2015。Rev. A 是包修订标记，并不表示其内部 LIB 已变为另一个模型版本。较大包还包含 OLB/DSN/OPJ 与启动/负载工程。

两份 LIB 的主子电路端口顺序、全部 27 个子电路、FSW/ILIM/软启动/MODE 源码一致。SLVMDA9 的 439 个 CRLF 转为 LF 后，与 SLVMAU6A 完全一致，包括注释。

本次新下载的 SLVMAU6A LIB 仅做下列两处等值表达式替换，各一次，即与当前仓库模型逐字节相同：

1. (2.35-6m) → 2.344。
2. (1.48+6m) → 1.486。

[完整适配 diff](results/frequency_round2/model_binary/official_to_repository.diff) 未发现额外参数或行为路径改动。未覆盖当前仿真基线。

## 判断边界

文件来源和文本差异已验证；原生 PSpice 与 LTspice 交叉仿真尚未完成。源码相同不证明模型无缺陷，也不证明某个求解器存在缺陷。频偏应结合[第二轮频率与 FSW 实验报告](results/frequency_round2/实验报告.md)判断。实际器件效率、饱和安全与温度行为仍需台架证据。

原始 ZIP 保留在本地 work/v14-round2-model-audit，不纳入本轮 Git 提交。复核脚本与精确哈希已提交；再次下载应使用独立目录，先检查哈希再对比，不覆盖本次获取记录。
