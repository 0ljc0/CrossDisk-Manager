# 任务 04 验证记录

日期：2026-10-29；Windows 本机 Python 3.12.8 / PySide6 6.10.0。

## 自动化结果

`.\.venv\Scripts\python.exe -m pytest -q`：**76 passed, 1 skipped in 16.08s**。
`python -m pip check`：`No broken requirements found.`。

覆盖以下方面：

- 前三阶段回归；只读能力、目录枚举、stat、rb 文件读取；中文与空格路径。
- 越界路径、备用数据流、设备名及 PhysicalDrive/GLOBALROOT 等非法根拒绝。
- Windows 隐藏属性、超过 260 字符路径、421 项分页与目录变化检测。
- 真实子进程查询与 GUI：每批 200 项、累计 406 项加载、双击与返回、空目录、不存在路径、快速切换后忽略旧结果、GUI 事件响应。
- 权限错误去敏、共享冲突/文件锁错误分类、真实临时文件的只读独占锁不会被绕过；模拟卡住的查询可超时/取消并清理进程，不实际访问网络。
- 1 项跳过：临时目录创建循环符号链接时 Windows 返回 WinError 1314（当前令牌缺少创建符号链接权限），未尝试提权。既有 junction 的实际拒绝跟随已在下述实机检查中验证。

测试数据准备仅在 pytest 临时目录创建普通样本文件、目录及隐藏属性，不测试应用写入功能，不修改用户已有文件、真实分区状态或 Windows ACL。

## 实机只读检查

执行 `.\.venv\Scripts\python.exe -m scripts.capture_native_ui` 成功：

| 检查 | 结果 |
|---|---|
| `C:\Users`，隐藏文件关闭 | 显示 3 项 |
| `C:\Users`，隐藏文件开启 | 显示 8 项，包含链接和隐藏文件 |
| `C:\Users\All Users` 既有 junction | 明确阻止进入，不跟随链接 |
| `C:\System Volume Information` | 显示“访问被拒绝”，程序继续响应 |
| `D:\crossdisk_manager` | 当次显示 14 项；后续增加文档可能改变项数 |
| 双击 `app` 目录后后退 | 路径与列表正确恢复 |
| 新建、重命名、删除、保存 | 全部禁用 |

另对项目 README 执行了 `stat` 和只读打开，流 `readable=True`、`writable=False`，实际读取 8 字节，不输出文件内容。GUI 目录绑定使用当前扫描得到的 Volume GUID 根，盘符只负责显示与输入路由。

截图 `screenshots/task04-users.png`、`screenshots/task04-project.png` 已打开检查：分区树、文件图标、列名、属性区及状态正常。

## 限制

- 未提供真实 UNC 共享，当前只验证格式、路由和进程超时/取消，未验证 SMB/WebDAV/NAS 兼容性。
- 所有重解析点均阻止进入，包括可用的安全链接和部分云文件；本任务采取保守只读边界。
- 超大目录通过临时目录样本验证分批及响应；未创建百万项实机目录。后续批次重新枚举并跳过已扫描项，越靠后的批次可能较慢；有超时保护。
- 权限提示来自 Windows 文件属性，不是有效 ACL 权限计算。目录变化时需重新刷新，分页不保证原子快照。
- 未实测独立 Windows 10、多物理盘、真实热插拔与独立高分辨率显示器。

只读后端没有写入、删除、覆盖、格式化或原始磁盘接口；未读取真实 Ubuntu 文件，未写 EFI、Recovery、Ubuntu 分区或分区表。
