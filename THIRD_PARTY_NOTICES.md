# 第三方软件与发布边界

本地构建使用 Python 3.12.8、PySide6/shiboken6 6.10.0、pytsk3 20260715、PyInstaller 6.22.3。发布目录 third_party 保存已安装包提供的许可文本/METADATA 与 Python 完整许可证；BUILD_MANIFEST.json 记录版本、收集数量和 exe 哈希。不打包商用驱动或内核 ext4 写驱动，pytest 仅用于测试。

| 组件 | 核对依据及注意事项 |
|---|---|
| CPython 与内置第三方代码 | 随 Python 安装的 LICENSE.txt，包含 Python 及相关组件条款；保留全文。 |
| PySide6、shiboken6、Qt Core/Gui/Widgets 及图片插件 | 已安装包元数据列 LGPL/GPL/商业选项，需依据实际模块选择合适条款。当前不购买商业授权，保留 LGPL/GPL 文本及模块附带许可，不把商业许可证文件当作本项目已获商业授权。采用文件夹式动态 DLL 发布，禁止额外限制用户为调试库修改进行必要的逆向/替换。 |
| pytsk3 | 包 METADATA 为 Apache-2.0；附带 Sleuth Kit 的 CPL/IBM 条款和 talloc 的 LGPLv3，不能只写“全部 Apache”。依包完整保留许可证。 |
| PyInstaller bootloader/构建器 | GPL 及 bootloader 例外，以收集的原文为准；不据此声称用户应用自动变为 GPL。工具及 hooks 另按其版本许可，不作为商业驱动。 |

官方参考：[Qt for Python 许可](https://doc.qt.io/qtforpython-6/licenses.html)、[pytsk 源码](https://github.com/py4n6/pytsk)、[TSK 许可](https://www.sleuthkit.org/sleuthkit/licenses.php)、[PyInstaller 许可](https://pyinstaller.org/en/stable/license.html)。

本项目自身源码采用根目录 [LICENSE](LICENSE) 中的 MIT License，Copyright (c) 2026 Jianchao Liu。MIT 授权不重新许可上述第三方组件，当前产物仍为本地验收候选，没有上传或公开发布。**公开再分发前**，须按实际分发模块完成版权声明、可替换/重链接材料及 LGPL/CPL 等所要求的对应源码提供方式；仅保留本页和上游链接不代表已履行所有源码义务。不得删除 third_party、DLL 或第三方声明后单独对外发 exe；也不得把未验证的 ext4 写能力宣传成可用。
