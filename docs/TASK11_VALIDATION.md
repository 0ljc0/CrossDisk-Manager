# 任务 11 验证记录

日期：2026-10-29。环境：Windows、Python 3.12.8、PySide6 6.10.0，依赖未变化。

## 运行命令

```powershell
.\.venv\Scripts\python.exe -m app.main
.\.venv\Scripts\python.exe -m pytest tests/test_ext4_write_admission.py -q
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m scripts.capture_ext4_admission_ui
.\.venv\Scripts\python.exe -m pip check
```

## 实际验证

- 专项 **9 passed in 1.58s**：7 类写/同步操作全部抛出 UnsupportedWriteError；运行时协议检查通过、write=False、operations 为空。替换 builtins.open、os.open、subprocess.Popen 和 ctypes.WinDLL 为失败函数，拒绝路径仍正常抛出定义异常，没有文件/设备/进程 I/O。
- 环境变量声称已安装/启用 Paragon、不可信能力声明 write=True 均不能开启写入；准入状态固定禁用，选择点只返回拒绝后端。
- 合成 ext4 镜像仍可通过真实 pytsk3 只读列目录；UI 旧写按钮及 Windows 专用写入入口均禁用，属性区显示明确未接入已验证驱动，准入说明包含 Linux 独立校验待办。
- `capture_ext4_admission_ui` 实际运行成功，镜像 SHA-256 前后不变，正常关闭窗口；使用普通文件镜像和样本分区清单，不打开真实 Ubuntu 原始设备。
- 只读 Get-Service、Win32_SystemDriver 按常见 ext2/ext4/paragon/lxfs/ufsd 服务/驱动名筛选均无匹配；不推断为完整安装审计，项目不存在已注册写适配实现。
- 官方资料与候选比较、共盘限制、授权/权限及支持证据缺口已记录于 [可行性报告](EXT4_WRITE_FEASIBILITY.md)。
- 截图：[只读与写入禁用状态](screenshots/task11-readonly.png)。完整回归与依赖结果见 PROGRESS.md。
- 最终完整回归 **169 passed, 1 skipped in 52.51s**，唯一跳过为旧 Windows 符号链接创建权限项；pip check：No broken requirements found。只读截图已打开检查。

## 验收边界

任务文档允许在无已验证服务时交付“安全禁用 + 可行性报告 + 可替换写入接口”，本次采用此路径，没有未完成的实际驱动接入承诺。协议为未来扩展点，不保证任意驱动天然满足协议或安全要求。

没有提供/选择/授权实际写入驱动，没有独立测试盘和 Linux 重挂载、内核日志、完整性检查、断电恢复证据；因此这些测试未执行，不能宣称通过。只读镜像散列不变不能用作实际写入兼容证据。真实 Ubuntu 以前阶段的浏览/搜索/导出人工验收继续待办。

没有驱动安装、自动提权、wsl --mount、磁盘离线、格式化、分区表修改、原始设备写入、ext4 文件写入或任务 12 打包开发。
