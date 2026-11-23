# LTspice → Weave → 嘉立创导入资格测试

> **测试性质：NET→ASC 转换资格验证，不是可直接打板的生产原理图。**

## 基线与输入

- 仓库基线：`power-stage-integration`
- 基线提交：`360508c08f23f63cdd74fba7e0c201b0907d3825`
- 隔离测试分支：`test/ltspice-weave-jlc-qualification`
- 输入网表：`sim/tps61088_v1_3/joint/eol_1p2s.cir`
- 输入模型：`sim/tps61088_v1_3/model/TPS61088_LT.LIB`
- 网表 Blob SHA：`200f5d1e65252de662e0e58f90deec15e576caef`
- 模型 Blob SHA：`ffcd200a44b1c316b8692e89201c594ad9a397d7`
- Weave 固定提交：`bc9b3d3299f3d96fae3f9a1e56de2c639e40c68a`

## 自动化结果

GitHub Actions 已成功完成以下工作：

1. 复制原始 `.cir` 和模型文件到隔离临时目录，不改写仓库原件。
2. 使用固定版本 Weave CLI 生成 LTspice `.asc`。
3. 执行 round-trip verifier，输入 NET 与 ASC 的网络连接结果为 `MATCH`。
4. 生成宏模型合成符号 `__block21.asy`。
5. 列出 ASC 引用的标准符号及仍需从本机 LTspice 库补齐的 ASY。
6. 生成转换报告、SHA256 清单和 manifest，并上传 GitHub Actions artifact。

本次 Weave 选择 safe-layout mode 3，转换日志明确报告 `MATCH (round-trip verified)`；这不是 LTspice 仿真或视觉布局验收。

## 当前转换输出需要的符号

ASC 中引用：

- `__block21`：Weave 已生成 `__block21.asy`
- `bi`
- `cap`
- `ind`
- `res`
- `voltage`

后五个标准符号需要从你本机 LTspice 安装目录的 `lib/sym` 复制。自动化没有拿第三方符号库替代本机库，也不会在缺失符号时生成不完整 ZIP。

## 生成最终嘉立创导入 ZIP

先下载并解压 GitHub Actions artifact，确保 `eol_1p2s.asc` 与 `__block21.asy` 位于同一目录。然后在 Windows PowerShell 中从仓库根目录运行：

```powershell
py -3 .\hardware\ltspice-jlc-qualification\package_jlc_import.py `
  --asc .\path\to\artifact\source\joint\eol_1p2s.asc `
  --output .\path\to\artifact\eol_1p2s-jlc-import.zip `
  --symbol-root "$env:LOCALAPPDATA\LTspice\lib\sym"
```

如果 LTspice 安装在其他目录，把 `--symbol-root` 改成实际的 `lib\sym` 路径。脚本会：
- 扫描 ASC 中的全部 `SYMBOL` 记录；
- 优先使用 ASC 同目录下 Weave 生成的 `__block21.asy`；
- 从本机 LTspice 库查找 `bi/cap/ind/res/voltage.asy`；
- 从 ZIP 副本中移除 .include/.ic/.save/.options/.tran/.meas 仿真指令；原始 ASC 不改动；
- 检查缺失和同名冲突；
- 只有全部符号唯一匹配时才生成 ZIP；
- 输出 ZIP SHA256 和 manifest。

CI 对打包器运行 4 个单元测试：完整符号集成功打包、缺失符号时拒绝、同名冲突时拒绝、SpiceOrder 错乱时拒绝。打包器同时检查标准两引脚符号和合成 21 引脚块的引脚数量及连续编号。当前远端 Linux CI 没有本机 LTspice 符号库，因此只生成 preflight artifact，没有伪造最终 JLC ZIP。

## 不在自动化验收范围内

- **LTspice 二次仿真：未执行。** Linux CI runner 没有 LTspice Windows 桌面仿真器。
- **嘉立创 EDA 实际导入：待本机 GUI 验收。** ZIP 文件完整不等于嘉立创导入器已经成功解析。
- **电气正确性：不由 Weave MATCH 证明。** MATCH 只证明 ASC 与输入网表的网络连接分区一致，不证明拓扑满足设计指标、模型有效或器件选型正确。

## 关键模型证据差异

仓库现有 `sim/tps61088_v1_3/joint/eol_1p2s.log` 记录的模型加载路径为：

`work/lt_probe/TPS61088_LT.LIB`

而本测试输入网表引用的是仓库中的：

`sim/tps61088_v1_3/model/TPS61088_LT.LIB`

因此，旧日志不能作为仓库当前模型文件已独立复跑的证据。本测试会保留并哈希原始文件，不会悄悄用未提交的适配模型替换它。

## 重要：不能拿这个 ZIP 直接打板

`eol_1p2s.cir` 是功率级仿真 testbench，含有预偏置初始条件、行为负载、仿真电压源和测量指令。Weave 生成的 21-pin `__block21` 是为保持 TPS61088 宏模型引脚连接而生成的合成符号：

- 它不是 TPS61088 的真实封装引脚图；
- 它没有经过真实芯片引脚名称/编号映射；
- 它没有绑定 PCB footprint；
- 不能把它当成生产 BOM 或 PCB 原理图。

本测试 ZIP 只用于验证 ASC + ASY 能否被嘉立创 EDA 专业版导入，不代表完整 UPS 原理图。

## 本机导入步骤

嘉立创 EDA 专业版官方说明要求将 ASC 与对应 ASY 一起打包为 ZIP；入口为：

- 开始页 → 快速开始 → 导入其他 → 导入 LTspice；
- 或打开工程后：文件 → 导入 → LTspice。

导入后请检查：
1. 是否成功创建原理图页；
2. 是否存在缺失符号、空白符号或错误旋转；
3. 电阻、电容、电感、电压源、行为电流源是否显示；
4. `__block21` 的 21 个引脚是否全部存在且没有错位；
5. 导线与引脚是否正确连接，网络标签是否可读。

**不要在未完成真实器件映射、封装绑定和 PCB DRC 前下单。**

官方文档：[导入 LTspice｜嘉立创 EDA 专业版用户指南](https://prodocs.lceda.cn/cn/import-export/import-ltspice/index.html)
