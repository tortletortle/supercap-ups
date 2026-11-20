# TPS61088 模型兼容性

## 来源与身份

- 器件：Texas Instruments TPS61088。
- 模型类型：TI 官方 PSpice transient macro-model，子电路名 TPS61088_TRANS。
- 模型头部标注：TPS61088EVM-677、SLVUAF2、SLVSCM8、Model Version Final 1.00。
- 仓库文件：TPS61088_LT.LIB。
- 适配文件 SHA-256：39F724ACCC32B8930E06C9F7A979FEF5E3163CCD1E2AC027E10F546E7D624CE1。

## 适配内容

LTspice 能够解析主电路，但 TI PSpice 文件中的两个带括号表达式需要改成等价数值表达式：

1. (2.35-6m) 改为 2.344。
2. (1.48+6m) 改为 1.486。

未替换功率级、控制环路、限流、软启动或反馈行为。网表实例仍使用 XU1 ... TPS61088_TRANS，因此运行的是 TI 宏模型，不是理想开关。

## LTspice 兼容性观察

- LTspice 26.1.1 可完成启动、稳态、负载阶跃和预偏置联合窗口仿真。
- 模型反复输出 N=0.0001 二极管发射系数警告。该警告在本轮窗口内未阻止收敛，但说明模型并非针对 LTspice 原生优化。
- 结果是宏模型在短窗口内的输入到负载能量比，不能直接当作实物整机效率或热设计结论。
- 网表从 sim/tps61088_v1_3/netlists 或 sim/tps61088_v1_3/joint 目录运行时，统一使用相对引用：

    .include ../model/TPS61088_LT.LIB

## 复跑方式

在安装 LTspice 并确保命令行可用的环境中，从对应目录执行，例如：

    cd sim/tps61088_v1_3/netlists
    ltspice.exe -Run vin_7.cir

联合窗口网表位于 sim/tps61088_v1_3/joint，同样从该目录运行。仓库只提交网表、日志、CSV 和 PNG，不提交 .raw、.op.raw、.db 等大文件。
