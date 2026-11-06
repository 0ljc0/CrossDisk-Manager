# 1.0.0rc2 本地候选交付

日期：2026-11-07。Windows 11 x64、Python 3.12.8、PySide6 6.10.0、pytsk3 20260715、PyInstaller 6.22.3。本地未签名候选，不上传或创建正式版标签。

## 功能

Windows 具备 ext4 只读浏览、快照、五类操作暂存、取消与修改包导出。Ubuntu 工具支持固定注册、预检、镜像范围五类操作应用、重复执行保护、检查、显式继续与还原。

## 验收证据

- 源码完整回归：277 passed, 1 skipped（54.09 秒）；跳过项为 Windows 符号链接创建权限。pip check 通过。
- G0 跨系统快照、预检、单文件写入、I/O 故障以及正式执行器报告已复核，结果见对应 RESULT JSON；早期恢复 V1/V2 仅用户确认通过，未取得原始结果包，不计为独立复核证据。
- Ubuntu 正式执行器的镜像端到端 11 项通过，含五类应用/还原、重复执行和提交日志前退出后的继续。随附事件链、计划摘要及备份元数据已核对；没有在 Windows 重跑 Linux 检查。
- 打包 exe 黑盒检查结果保存于 FROZEN_SMOKE_1.0.0rc2.json。包含新暂存面板实际导出修改包与独立包校验，不仅是窗口启动。
- 实际 exe 9 项黑盒检查全部通过，管理员身份 false，源镜像哈希不变。最终归档完成后再核对内嵌 exe 与该报告摘要相同。

## 构建与交付

```powershell
.\.venv\Scripts\python.exe -m scripts.build_release
.\.venv\Scripts\python.exe -m scripts.smoke_frozen
.\.venv\Scripts\python.exe -m scripts.build_release --package-only
.\.venv\Scripts\python.exe -m scripts.build_delivery
```

Windows ZIP 必须完整解压；Ubuntu 工具位于 Windows 程序目录的 Ubuntu-tools 下，同时在组合交付包单独提供。归档带 SHA-256；BUILD_MANIFEST 包含 exe 摘要及第三方版本和许可清单。

## 验收边界

Windows 不直接写 ext4。Ubuntu 应用目前仅限额外授权的 loop 测试镜像；真实分区仍被程序拒绝。不是多文件事务，不保证任意断电自动恢复。跨启动身份迁移、真实坏块、独立 Windows 10/其他电脑、真实数据写入和完整 ACL/xattr 尚未验收。候选交付不等于这些边界已经通过。

本轮“整体”指现有源码/GUI、schema 3、镜像执行器和实际 exe 的组合证据。尚未把同一次 GUI 导出的包带到 Ubuntu 完整往返；已分别验证 Windows 实际导出的格式和 Ubuntu 执行同格式包。因此不把分段证据描述成已完成同一包的跨系统闭环。
