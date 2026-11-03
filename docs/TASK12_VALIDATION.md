# 任务 12：V1.0 只读 ext4 版候选验收

日期：2026-10-29；本机 Windows 11 22631 x64，Python 3.12.8、PySide6 6.10.0，PyInstaller 6.22.3/hooks 2026.9。版本 **1.0.0rc1**，未签名、本地验收候选，未上传、公开发布或创建正式版 Git 标签。

## 实际执行与证据

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m scripts.build_release
.\.venv\Scripts\python.exe -m scripts.smoke_frozen
.\.venv\Scripts\python.exe -m scripts.build_release --package-only
.\.venv\Scripts\python.exe -m pip check
```

- 最终完整 pytest：**173 passed, 1 skipped in 47.46s**，唯一跳过为旧 Windows 符号链接创建权限（WinError 1314）。已有真实 Windows 与镜像测试包含长路径、中文路径、分区身份、能力保护、预览预算、分页、搜索取消、复制哈希和写入失败保护。pip check 无依赖冲突。
- 新增测试验证源码/冻结后台分派白名单、固定日志文件末尾 64 KiB、缺失日志提示、异常日志不记录消息中的令牌/私有路径/内容。
- 帮助菜单增加本地日志查看，保留既有错误页与弹窗；修正过期的“任务08/全部写入禁用”关于文案。后台线程/子进程取消与关闭回归通过；不宣称底层阻塞调用可强制中断。
- 首轮构建暴露 QtCore DLL 导入失败；分析发现宿主 PATH 中图像运行库的旧 UCRT 被误收集。构建脚本改为隔离 PATH，并 clean 重建；不把该失败包当可交付版本。
- exe 黑盒验收从另一个含中文的临时工作目录运行，使用临时 LOCALAPPDATA：Windows 目录、文本预览、无盘符 ext4 普通镜像目录/预览、跨后端 *.py 搜索、demo GUI、真实 Storage 清单及 GUI 目录导航、镜像 SHA-256 不变，**8 项均通过**。当前进程 Administrator=False；没有本机 Python 解释器子进程依赖，冻结后台通过自身 exe --worker 调度。
- 冻结 windowed 子进程显式恢复父进程匿名管道；不创建普通 GUI 控制台，不以 `exe -m` 启动子任务。后台仅支持固定 native/search，不提供任意模块入口。
- `docs/TASK12_FROZEN_SMOKE.json` 保存已验证 exe SHA-256、权限与检查项。最终 ZIP、校验文件及 BUILD_MANIFEST.json 由构建脚本产生；dist/build 不进入源码 Git。
- 最终 exe 的 8 项黑盒测试再次通过；源码 `python -m app.main --smoke-test` 真实清单/导航自动退出成功。直接解析 PE 资源确认 manifest 为 asInvoker 且无 requireAdministrator；文件清单确认 VirtualKeyboard 不在产物中，Qt LGPL 原文存在。最终打包归档包含最新黑盒报告，不重新编译已验证 exe。

## 六种典型场景

| 场景 | 证据与结果 |
|---|---|
| 无盘符 ext4 | 真实 pytsk3 合成普通镜像，经稳定分区上下文读取 /home；冻结查询同样成功。真实 Ubuntu 实盘仍未人工验收。 |
| 无管理员 | 本机普通用户清单与 C/D 浏览的既有证据、exe 实际启动 Administrator=False；原始设备读权限不足仍明确拒绝，不承诺自动提权代理。 |
| 写驱动缺失 | task11 拒绝后端全部变更/flush 抛 UnsupportedWriteError，UI 不开放 ext4 写入；不能由配置声明绕过。 |
| 目标写保护/权限不足 | policy 拒绝只读/离线/锁定/系统卷，故障注入验证权限拒绝和磁盘满；真实文件锁测试保留原文件。没有故意把真实磁盘改只读或耗尽空间。 |
| 已存在文件 | Windows 独占新建与不覆盖 rename，复制默认跳过，发布竞争测试及保存版本冲突保护通过。 |
| EFI/Recovery 禁写 | GPT 分类优先于后端能力，模拟错误 browsable/write=True 不能绕过；UI 和直接后端拒绝均在回归中验证，无真实保护卷写测试。 |

## 模块与打包审查

core 为路径/协议/能力，backends 为只读文件系统及明确受限 Windows 写接口，services 负责策略路由，jobs/UI 分离耗时调用。新增 runtime/bootstrap 仅处理部署差异，既有后端公共接口不变。日志只记录计数/固定状态/异常类型；未加入网络上传。

文件夹式包保留 Qt DLL、平台/图像插件和 pytsk3 扩展。排除不用的 Qt Virtual Keyboard 插件及其 DLL（该模块许可与基本 Widgets 不同），不捆绑商用驱动、测试镜像、用户配置、日志或 pytest。构建期从已安装依赖收集许可证并补充对应 Qt 版本 GPL/LGPL 原文来源与哈希，附 Python、TSK、talloc 等条款；具体信息见 THIRD_PARTY_NOTICES.md。普通用户 manifest 不请求全局管理员权限。

## 尚未通过的外部验收

- 独立 Windows 10、其他 Windows 11/干净机器未具备环境，不能把本机启动当作跨机器验收通过。无代码签名/安装器；当前为解压即用文件夹。
- 真实 Ubuntu /home 浏览、搜索与导出仍待人工；回收站 Shell 原生确认和恢复仍待人工。之前镜像只读测试不能替代实盘证据。
- 真实 UNC、物理热插拔、多物理盘、实际磁盘耗尽、断电/掉电及恢复未全部实测。故障注入/取消模拟不代表硬件掉电一致性认证。
- ext4 写入永远不在本候选中开放，没有驱动安装或隔离写入/Linux 重挂载验证。
- 项目再分发许可尚未由用户确定；公开发布前还需完成第三方对应源码/重链接等实际义务。当前仅构建本地候选，没有向外部发布。

因此不创建“已完全验收”的 V1.0 正式标签。下一步为用户本地候选验收及上述人工/独立环境验证，通过后再单独决定正式发布与维护，不存在任务 13 的自动开发。
