# 任务 06 验证记录

日期：2026-10-29。仅实现统一只读路径、导航、能力及展示，不开发任务 07 预览或任何写入驱动。

## 实际结果

- 全套回归：**111 passed, 1 skipped in 25.78s**。
- 随后补充“错误注册 EFI 根仍被拒绝”和“旧失败回调不覆盖新页”的断言，专项 **11 passed in 5.87s**。
- `python -m pip check`：`No broken requirements found.`。
- 跳过项仍为任务 04 的 Windows 临时循环链接创建（WinError 1314）；ext4 镜像链接边界测试正常执行，没有申请额外权限。
- 运行 `python -m scripts.capture_unified_navigation` 成功：真实 `C:\Users` → 合成 ext4 镜像 `/home` → 后退至 C:\Users → 前进至镜像 /home → 点击镜像根面包屑，全程保持正确分区与目录。
- 已打开检查 `screenshots/task06-windows.png` 和 `task06-ext4-image.png`：面包屑、七列表头、后端来源、属性区与只读状态正常；测试镜像明确标识为“非 Ubuntu 实盘”。

## 新增验证

1. VirtualPath 的分区身份、规范化、父目录、单层子目录、根到当前目录的面包屑；旧 Location 导入及 relative_path 关键字兼容。
2. `..` 越过分区根、控制字符和错误内部分隔符拒绝，不执行后端访问。
3. 伪造普通昵称/category 不能覆盖 EFI/MSR/Recovery GPT 保护；能力提供者不会被调用。
4. 即使将 EFI 错误加入 roots 并呈现 browsable=True，request_spec 与后台工厂仍拒绝，Windows 后端构造函数不会运行。
5. 未知 GPT、缺少后端及 Linux→Windows 错误路由被拒绝。后端声明 write=True 仍得到 write=False 的策略结果。
6. 缺失类型、大小、时间、权限、链接与来源显示未知，不把未知写成“否”或 0 字节。
7. Windows 与 ext4 结构化实现 FileSystemBackend；真实目录/镜像元数据标出来源。
8. 临时 Windows 目录与真实 pytsk3 镜像之间切换，历史和面包屑保留分区；在加载前清空旧数据，过期成功与失败回调都被忽略。
9. 快速切换后的文件条目仅来自当前后端；切换保护分区立即清空列表，所有写按钮禁用。

## 本次文件

- 新增核心：`app/core/backend.py`、`virtual_path.py`、`capability_policy.py`。
- 新增服务：`app/services/backend_access.py`、`messages.py`。
- 修改浏览模型、Windows/ext4/mock 元数据、InventoryBrowserSource、目录子进程及主窗口。
- 新增 `tests/test_navigation_policy.py`，迁移已有测试的保护分区 fixture 和统一错误断言。
- 新增 `scripts/capture_unified_navigation.py`、两张截图，更新 README 与 PROGRESS。
- 无新增依赖。

## 未验证与限制

- 本次没有自动读取真实 Ubuntu 分区。任务 05 的实盘根/home/样本人工验收仍未完成；本次跨后端证据中的 `/home` 来自可丢弃 ext4 镜像，不能宣称实盘 Ubuntu 验收成功。
- 普通 GUI 不自动提权；独立读取工具及无管理员代理 IPC 的限制保留。
- 真正 UNC 共享、物理热插拔、多盘和独立 Windows 10/高分辨率显示器仍未实测。
- 面包屑做逻辑路径规范化，不解析或跟随真实链接；受限条目不会通过地址或双击绕过后端边界。
- 本阶段没有右键写入功能、文件内容预览、通用复制队列或任何磁盘修改。
