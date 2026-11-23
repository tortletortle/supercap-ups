# LTspice → Weave → 嘉立创导入资格测试

> **测试性质：转换链路验证，不是可直接打板的生产原理图。**

## 基线与输入

- 仓库基线：`power-stage-integration`
- 基线提交：`360508c08f23f63cdd74fba7e0c201b0907d3825`
- 测试分支：`test/ltspice-weave-jlc-qualification`
- 输入网表：`sim/tps61088_v1_3/joint/eol_1p2s.cir`
- 输入模型：`sim/tps61088_v1_3/model/TPS61088_LT.LIB`
- 网表 Blob SHA：`200f5d1e65252de662e0e58f90deec15e576caef`
- 模型 Blob SHA：`ffcd200a44b1c316b8692e89201c594ad9a397d7`
- Weave 固定提交：`bc9b3d3299f3d96fae3f9a1e56de2c639e40c68a`
- 测试符号库固定提交：`8b77969893ad4330b9ec288e4da48121f7914b0a`

## 自动化验收范围

GitHub Actions 执行：

1. 复制原始 `.cir` 和模型文件到隔离临时目录，不改写仓库原件。
2. 使用固定版本 Weave CLI 生成 LTspice `.asc`。
3. 使用 Weave round-trip verifier 比较输入 NET 与 ASC 的网络连接。
4. 为 Weave 生成的标准符号和合成多引脚块收集对应 `.asy`。
5. 检查 ASC 引用的每个符号都有对应 ASY。
6. 生成嘉立创导入 ZIP、LTspice 源文件包、SHA256 清单和转换报告。
7. 上传 GitHub Actions artifact。

## 不在自动化验收范围内

- **LTspice 二次仿真：未执行。** Linux CI runner 没有 LTspice Windows 桌面仿真器。
- **嘉立创 EDA 实际导入：待本机 GUI 验收。** CI 只能验证 ZIP 内容与文件引用，不能证明嘉立创导入器已成功解析。
- **电气正确性：不由 Weave MATCH 证明。** MATCH 只证明 ASC 与输入网表的网络连接分区一致，不证明拓扑满足设计指标、模型有效或器件选型正确。

## 关键模型证据差异

仓库现有 `sim/tps61088_v1_3/joint/eol_1p2s.log` 记录的模型加载路径为：

`work/lt_probe/TPS61088_LT.LIB`

而本测试输入网表引用的是仓库中的：

`sim/tps61088_v1_3/model/TPS61088_LT.LIB`

因此，旧日志不能作为仓库当前模型文件已独立复跑的证据。本测试会保留并哈希原始文件，不会悄悄用未提交的适配模型替换它。

## 重要：不能拿这个 ZIP 直接打板

`eol_1p2s.cir` 是功率级仿真 testbench，含有预偏置初始条件、行为负载、仿真电压源和测量指令。Weave 生成的 22-pin `__block22` 是为保持宏模型引脚连接而生成的合成符号：

- 它不是 TPS61088 的真实封装引脚图；
- 它没有经过真实芯片引脚名称/编号映射；
- 它没有绑定 PCB footprint；
- 不能把它当成生产 BOM 或 PCB 原理图。

该 ZIP 只用于验证“ASC + ASY 是否能被嘉立创 EDA 专业版导入”。

## 本机导入步骤

嘉立创 EDA 专业版官方说明要求将 ASC 与对应 ASY 一起打包为 ZIP；入口为：

- 开始页 → 快速开始 → 导入其他 → 导入 LTspice；
- 或打开工程后：文件 → 导入 → LTspice。

导入后请检查：
1. 是否成功创建原理图页；
2. 是否存在缺失符号、空白符号或错误旋转；
3. 电阻、电容、电感、电压源、行为电流源是否显示；
4. `__block22` 的 22 个引脚是否全部存在且没有错位；
5. 导线与引脚是否正确连接，网络标签是否可读。

**不要在未完成真实器件映射、封装绑定和 PCB DRC 前下单。**

官方文档：[导入 LTspice｜嘉立创 EDA 专业版用户指南](https://prodocs.lceda.cn/cn/import-export/import-ltspice/index.html)
