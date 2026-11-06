# Schema 3 修改包校验（2026-11-06）

已实现 app/core/bundle.py 与 scripts/validate_bundle.py。支持 create_file、replace_file、delete_file、mkdir、rename_file 的严格字段检查、旧状态必需字段、UUID 规范化、规范 JSON 和 SHA-256；拒绝重复键/ID、未知字段、非整数、特殊权限、硬链接快照、跨目录重命名及重叠路径。限制清单 4 MiB、1000 操作。

运行：

```powershell
.\.venv\Scripts\python.exe -m scripts.validate_bundle --bundle <修改包目录>
```

包目录含 manifest.json 和 files/ 下的 payload。命令只读，核对大小和内容哈希。正常退出仅表示 package_valid，不表示 Ubuntu 目标预检通过；输出始终 apply_allowed=false、target_preflight=NOT_IMPLEMENTED。

此便携工具用于稳定、可信本地输入的开发验证。路径 lstat 检查不是并发安全边界，不替代 Ubuntu openat2 私有 staging。没有 apply 参数、目标写入或授权入口。

2026-11-06 已新增 Linux 固定注册、挂载身份/允许根验证、私有 staging 和目标状态预检，实现说明见 PHASE6_LINUX_PREFLIGHT.md。Ubuntu 实机验收待执行。当前仍未交付 GUI/生成器、实际写入及恢复；本便携校验命令仍不调用 Linux 预检，不得用其结果解锁写入。

2026-11-07 更新：修改包生成器和暂存业务已实现，见 PHASE6_PENDING_EXPORT.md。Ubuntu 预检报告已复核通过，见 PREFLIGHT_RESULT_2026-11-06.json；GUI 和正式写入/恢复执行器仍待交付。
