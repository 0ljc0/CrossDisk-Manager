# 任务 10 验证记录

日期：2026-10-29；Windows、Python 3.12.8、PySide6 6.10.0，依赖无变化。

## 运行

```powershell
.\.venv\Scripts\python.exe -m app.main
.\.venv\Scripts\python.exe -m pytest tests/test_windows_write.py -q
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m scripts.capture_write_ui
.\.venv\Scripts\python.exe -m pip check
```

## 验证范围

- 默认 NativeWindowsBackend 不提供写入授权；直接调用写方法拒绝。新建/编辑窗口需要独立 WriteContext，绑定分区、磁盘及本次会话的数据目录。
- 分类测试：系统启动卷、隐藏分区、未知文件系统、EFI、锁定状态、离线/只读/不稳定磁盘拒绝；拒绝作用域自身、外部路径、系统目录、路径遍历及备用数据流。
- Windows 临时目录实际执行新建文件/目录、文本读取、保存、备份、重命名、同卷移动及经确认永久删除；核对保存内容与备份原字节。测试清单使用固定样本，卷 GUID 是真实临时目录卷。
- 外部修改后保存报冲突，不替换外部内容；GUI 后台线程测试确认错误后用户编辑正文仍保留。修复测试发现的 QDialog.finished 与回调同名问题。
- 同名创建及重命名失败，不覆盖已有文件。真实只读共享句柄阻止替换时原文件保持；注入权限、空间、替换错误及 fsync 磁盘满异常，原字节不变且本任务临时文件清理。
- 回收站默认路由及失败不调用永久删除由替身验证；永久删除缺少二次确认标志时后端拒绝。Shell 原生确认交互未自动化操作。
- 生产脚本在项目新建临时目录中，通过真实 Storage 快照、真实 Volume GUID、生产 CapabilityPolicy 和 WriteContext 执行新建/保存/备份/重命名/移动/删除；每次操作重新扫描并复核身份，内容与备份断言通过，测试目录退出后清理。
- 另执行 `python -m scripts.capture_write_ui --test-root D:\CrossDisk_TestWrite` 成功，在指定测试根内独占新建临时子目录完成同一操作链并清理；未修改该根的任何既有文件。
- 最终完整回归：**160 passed, 1 skipped in 52.22s**；最新专项：**9 passed in 0.69s**；pip check：No broken requirements found。唯一跳过为旧 Windows 符号链接创建权限测试。
- [编辑窗口截图](screenshots/task10-write.png) 已打开检查，目录范围、操作按钮、正文和备份提示可读。

## 限制与待办

- 指定 `D:\CrossDisk_TestWrite` 已完成独立临时子目录的自动化验收；真实回收站交互与恢复仍需人工操作。
- 系统回收站的真实确认、恢复、不可回收介质警告尚待人工测试。Shell 保留确认且设置回收/永久删除警告标志，不静默调用自身的永久删除路径。仅文件和空目录，不递归删除；不承诺所有删除可撤销。
- 仅同卷操作，不合并目录或覆盖冲突，不提供跨卷移动、其他编码编辑、自动备份清理或持久写入授权。Windows 启动卷也保守拒绝，即便某些普通用户目录可写。
- 文本限制 2 MiB；保存统一无 BOM UTF-8。SHA-256 为乐观冲突检测，最终阶段限制普通写句柄；外部进程同时重命名/替换名称不具有事务隔离保证。重要文件应避免同时由其他程序操作，并人工核对保留备份；不宣称任意并发操作可串行化。
- ReplaceFileW 适用同卷文件替换；不支持或权限不足就报错，无非原子覆盖降级。失败后保留系统留下的备份以供人工检查。真实磁盘耗尽和设备拔出未主动制造。
- 暂无操作撤销或强制中断写入；关闭需等待后台操作及身份扫描完成。扫描超时继续沿用已有 30 秒查询保护。
- 真实 Ubuntu 浏览/搜索/导出验收待办继续保留；本任务没有访问真实 Ubuntu 文件，更没有 ext4 写入、格式化、分区修改或磁盘离线。任务 11 未开始。

最终完整回归、专项结果见 PROGRESS.md。
