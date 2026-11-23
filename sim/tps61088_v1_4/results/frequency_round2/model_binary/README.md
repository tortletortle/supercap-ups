# 官方包文件复核材料

原始 ZIP 保留在本次工作目录的 work/v14-round2-model-audit，不提交二进制包。获取记录、ZIP 内逐项哈希、全部子电路哈希、精确 diff 和中文报告已保存于此。

重新获取时请在独立目录运行，避免覆盖本次元数据：

    py -3 download_models.py --out-dir <新目录>
    py -3 audit_models.py --repo <仓库根目录> --artifact-dir <新目录>

先将新下载 ZIP 的哈希与本目录 model_versions.csv 比较。重新获取产生的 UTC/HTTP 元数据将不同，不应替换本次原始记录。本次 audit_recheck.log 是对本地保留 ZIP 的实际重跑输出。
