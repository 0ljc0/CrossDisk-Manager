# 任务 09 验证记录

日期：2026-10-29；Windows、Python 3.12.8、PySide6 6.10.0，依赖版本未变。

## 命令

```powershell
.\.venv\Scripts\python.exe -m app.main
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest tests/test_copy.py -q
.\.venv\Scripts\python.exe -m scripts.capture_copy_ui
.\.venv\Scripts\python.exe -m pip check
```

## 直接证据

- 复制专项：7 passed in 0.90s。覆盖真实 Windows 临时目录流式复制、SHA-256/字节核对、既有目标不覆盖、发布时出现竞争文件、空间不足、权限失败、复制中取消、临时文件清理、目录重试，以及 Qt 队列暂停/取消/重试。
- ext4 测试使用真实 pytsk3 解析普通合成镜像，导出 `/home/demo`，目标 Python 样本字节一致，源镜像 SHA-256 不变；链接跳过。没有调用真实 Ubuntu 设备读取。
- 目标保护拒绝 ext4/普通盘符字符串/卷根/系统关键目录/路径遍历及备用流。部分测试为测试普通临时目录注入目标校验替身，实机脚本则完整使用生产 Volume GUID 检查和分区策略。
- `scripts.capture_copy_ui` 已成功：真实清单定位项目所在 Windows 卷，复制 Windows 测试文件并将 ext4 镜像目录导出到项目内新临时目录。确认内容一致、源镜像不变，退出时清理临时目录。
- [队列截图](screenshots/task09-copy.png) 已打开检查；镜像目录结果为完成 4 文件、失败 0、跳过 1 链接、54/54 字节；Windows 样本另一个串行任务成功。
- 依赖检查：No broken requirements found。最终完整回归结果记录于 PROGRESS.md。

## 限制与人工待办

- 真实 Ubuntu `/home` → `D:\CrossDisk_TestExport` 尚未人工验收；此次目标选择项目内临时目录，不创建工作区外目录。任务 05/08 的实盘人工验收待办继续保留。
- 空间和无权限失败用注入测试验证，不填满真实磁盘、不修改 ACL。异常时只清理该任务独占创建的临时文件，不删除任何既有目标；部分完成文件和目录保留。
- 采用后台线程及协作暂停/取消，GUI 可继续处理事件；设备底层调用阻塞时暂停/取消与关闭需等待。时间预算也在检查点生效，不强杀写入线程。尚未实测真实设备拔出或永久阻塞。
- 重试不是断点续传；目录只允许复用同会话任务记录且身份一致的自建目录。无覆盖、既有目录合并、队列持久化、时间戳/属性保留或真实网络目标。
- Windows 长路径和非法 ext4 文件名继续按 Windows 目标名称规则拒绝，不静默改名。源变化、短读、目标校验失败停止当前任务，不发布该文件。
- 没有格式化、分区表修改、磁盘离线、原始扇区写入或 ext4 写入；EFI/Recovery/系统关键目录保护持续生效。没有实施任务 10。
