# CrossDisk Manager — 第一步 V0.1

这是一个 **Windows 已挂载分区的只读图形文件浏览器**。支持浏览 C:/D:/ 和通过 Paragon 挂载的 Ubuntu E: 分区；不具备写入、删除、格式化、挂载隐藏分区等操作。

## 环境

Windows 10/11（64 位），Python 3.10+，PySide6。

## Windows PowerShell 命令

```powershell
cd D:\CrossDisk_Manager
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe .\main.py
```

若脚本放在其他文件夹，将 `cd` 调整为实际路径。无需修改 PowerShell 执行策略，也无需运行 `Activate.ps1`。

## 验收

1. 启动后弹出三栏图形界面。
2. 左侧列出已挂载卷，通常包括 C:、D:；Paragon 已挂载时列出 E:。
3. 点击 E: 可进入 `E:\home\ljc\CrossDisk_Test`。
4. 单击 `test.txt`，右侧显示 `Hello from Ubuntu`。
5. 双击目录可以进入，上一级、刷新、地址栏前往都正常。
6. 当前没有任何保存、新建、删除按钮，也不会执行文件内容。

## 下一步

第二步添加正式的分区扫描和文件系统适配器，而不是把盘符当作所有分区的全集。之后添加搜索、文件导出、权限检测以及经独立验证的 ext4 写入后端。

## 安全说明

本程序自身不调用写入文件 API，但底层第三方驱动的挂载行为由该驱动决定；测试期间请让 Ubuntu E: 保持驱动的只读挂载设置，不要更改分区表或格式化。
