# TPS61088 模型兼容性与文件身份

更新：2026-11-21，V1.4 第二轮官方包二进制复核。

本项目器件为普通 TPS61088，使用 TI 官方 PSpice 瞬态宏模型，主子电路 TPS61088_TRANS；文件头标注 TPS61088EVM-677、SLVSCM8、Final 1.00、11MAY2015、PSPICE 16.2.0.p001。不是理想开关替代模型。

当前文件 TPS61088_LT.LIB 为 16,352 字节，SHA-256：

    418466fbd205f9e9ec487bee1d9c1ada48858ff49eef67767e84706966fa1795

本轮实际重新下载普通 TPS61088 资源 SLVMDA9 与 SLVMAU6A Rev. A，完整哈希表、获取记录与版本见[模型来源审计](../../tps61088_v1_4/model_source_audit.md)及[版本对照报告](../../tps61088_v1_4/results/frequency_round2/model_binary/model_version_comparison_zh.md)。产品页本轮刷新 HTTP 404，两个 TI 官方 ZIP 端点均 HTTP 200；未用 Q1 模型替代。

旧版误标的 39f724accc32b8930e06c9f7a979fef5e3163ccd1e2ac027e10f546e7d624ce1 是 ZIP 哈希；新下载字节确认它对应 SLVMAU6A，不能当作 LIB 哈希。先前“包名称未确认、二进制对照 pending”的状态由本轮证据补齐，历史原始记录保持不变。

两包 LIB 只有换行差异：SLVMDA9 为 CRLF，SLVMAU6A 为 LF；统一后全文（含注释）和全部 27 个子电路逐字节一致。包 Rev. A 与内部模型 Final 1.00 是不同层次的版本标记。

SLVMAU6A 原始 LIB 的 SHA-256 为 27a088f856aaaf4219a494582fba73a801650d7bae09b5b7fd77023c791ebdf0。本次新下载 LIB 仅做两处替换，各一次，即与仓库模型逐字节相同：

1. (2.35-6m) → 2.344。
2. (1.48+6m) → 1.486。

完整 [diff](../../tps61088_v1_4/results/frequency_round2/model_binary/official_to_repository.diff) 已保存。没有发现额外端口、参数、FSW 或 ILIM 改动。文件关系已验证，跨求解器功能等价性仍需回归。未覆盖当前模型基线。

LTspice 26.1.1 / Normal / Gear 已完成 V1.4 首轮及本轮指定案例。日志均保留 5 条二极管 N=0.0001 警告。退出码、完整 RAW、终止时间与测量有效性需联合判断；低频案例固定边沿计数不足属于测量失败，不等同于求解不收敛。

[第二轮报告](../../tps61088_v1_4/results/frequency_round2/实验报告.md)记录频率差异和 FSW 定时路径诊断。两包源码相同，不能用版本差异解释本次频偏；也不能仅凭源码审计判定模型或 LTspice 存在缺陷。

未完成原生 PSpice 交叉仿真。宏模型功率比不等于实物效率；电感仅有 L 与 DCR，不能验证磁芯饱和安全。
