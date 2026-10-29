# ext4 写入可行性与准入报告

核对日期：2026-10-29。结论：**当前不接入实际写驱动，使用 UnsupportedWriteBackend；所有 ext4 写操作禁用。** 这符合任务 11 在缺少驱动/授权/独立验证证据时的交付要求。只读 pytsk3 后端保持原样，不新增写接口。

## 共盘限制与本机证据

Windows 与 Ubuntu 位于同一正在使用的物理系统盘。Microsoft 说明 `wsl --mount` 附加整个磁盘，即使指定单一分区也不能附加正在使用的 Windows 启动盘；需要管理员权限。不能靠把系统盘 Offline 规避。WSL 方案只保留为将来独立测试盘/可丢弃 VHD 的研究候选，不用于当前 Ubuntu 分区。[Microsoft 官方限制](https://learn.microsoft.com/en-us/windows/wsl/wsl2-mount-disk)

本机只读查询 Get-Service 和 Win32_SystemDriver，按 ext2/ext4/paragon/lxfs/ufsd 等常见名称筛选，均未返回匹配条目。查询不是完整安装审计，不证明不存在其他名称的驱动；项目也没有已注册且经过验证的写入服务、授权、版本/签名和隔离 Linux 校验证据。本次没有下载、安装、启动驱动，没有挂载或打开真实 Ubuntu 文件系统。

## 候选对比（官方声明不等于本机验证）

| 候选 | 许可证及 Windows 兼容声明 | 特征/写操作及接口 | 权限与共盘判断 | 本项目结论 |
|---|---|---|---|---|
| Paragon Linux File Systems for Windows | 商业专有，需相应许可；产品页列 Windows 11 x64/ARM64、Windows 10 x64 1809+ | 厂商声明 ext4 创建、编辑、删除、重命名；经挂载卷供普通文件 API 使用，并列 CLI；64bit/extents/has_journal 等支持，不支持 bigalloc/journal_dev/meta_bg/inline_data；metadata_csum 等具体版本支持证据仍需确认 | 安装内核驱动及卷管理权限需独立核实；厂商未在所查页面明确保证当前共盘 Ubuntu 系统分区安全，不能套用 WSL 限制，也不能推断已安全。自动挂载会扩大 OS 访问范围 | 可进一步向厂商取得版本、许可、CLI/SDK 文档及特征矩阵；没有接入或授权证明 |
| Ext4Fsd（Bo Branten 分支） | GPLv2；README 提供 Windows 10/11 签名驱动说明 | README 声明 metadata checksums、jbd2 64 位块号及 ext4 读写；列出仅内部 journal replay、链接、UID/GID mount-as-user。某些特征强制只读；encrypt/casefold/inline_data 等拒绝挂载。普通文件 API 与源码为集成途径，未验证稳定应用 SDK | 安装/管理内核驱动需相应权限及签名核实；源码和签名不证明目标盘兼容，共盘/并发挂载需独立验证 | 研究候选，不认定已通过安全准入。必须区分发布二进制与发布后源码新增特征 |
| Ext2Fsd / Matt Wu Ext3Fsd 原分支 | GPLv2；官方仓库 README 列到 Windows 10，未在该 README 声明 Windows 11 验证 | 官方源码提供 Ext2/3/4 文件系统驱动及管理/服务组件；本次未取得可证明现代 ext4 完整写语义的发布版证据 | 内核驱动安装与管理权限；当前 Windows 11、签名及复杂 ext4 组合均未验证 | 不选择旧分支作为现代 Ubuntu 写后端，不把后续 Ext4Fsd 分支声明归于旧版本 |
| WSL2 的 Linux 原生 ext4 服务路径 | Linux 内核 GPLv2，Windows/WSL 平台及发行版组件各依其许可；非单一可再分发驱动许可 | 可通过 Linux 系统调用/受控服务处理文件并同步；具体特征依内核版本，不是 pytsk3 写入。WSL CLI 是平台入口，不是本项目已实现 IPC/API | 附加磁盘需管理员；当前使用中的 Windows 系统盘不能附加，只能另行考虑隔离测试介质 | 对当前共盘物理盘不可用，本次不执行任何 mount |

来源：[Paragon 产品与特征说明](https://www.paragon-software.com/home/linuxfs-windows/)、[Ext4Fsd 官方 README](https://github.com/bobranten/Ext4Fsd/blob/master/README.md)、[原分支官方仓库](https://github.com/matt-wu/Ext3Fsd)、[WSL 官方说明](https://learn.microsoft.com/en-us/windows/wsl/wsl2-mount-disk)。表中的待核实项明确为证据缺口，不构成购买或安装建议。

## 必须验证的语义与证据

| 项目 | 风险及所需验证 |
|---|---|
| journal / jbd2 | 验证事务提交、重放及拒绝不干净卷策略。日志保护元数据不意味着任意文件内容在断电后完整；不得在真实 Ubuntu 上主动制造断电。 |
| metadata_csum / 64bit | 记录完整特征位、校验和算法及 64 位块寻址支持，覆盖不同组合；不能把可浏览一个目录当作可安全更新 inode/位图/日志。 |
| 大小写、Unicode 与名称 | 测试 a/A 共存、UTF-8/规范化、Windows 保留名与非法字符；不通过静默改名或覆盖消除冲突。casefold 卷需单独支持证据。 |
| UID/GID、mode、ACL、xattr | 记录权限映射、拒绝策略及属性保存，不能把 Windows 可写视为 Linux 权限已正确保留；覆盖普通用户与非所有者访问。 |
| symlink / hardlink | 默认不跟随符号链接；路径必须留在白名单用户目录，不允许借链接触及 /etc、/boot 等；硬链接与覆盖语义需要专项验证。 |
| 时间戳 | 核对精度、时区、纳秒、2038 扩展字段和修改/访问/创建时间语义，不静默截断。 |
| 同步、锁及冲突 | 明确 flush/fsync/rename 的驱动保证、文件锁映射、外部修改检测与同卷替换；验证不同进程读写及取消失败的结果。 |
| 断电一致性 | 在隔离介质中验证中断、重启、journal replay、Linux 原生重挂载及离线只检查的完整性报告；同时记录数据哈希与目录结构。 |

背景依据：[Linux ext4 journal 文档](https://www.kernel.org/doc/html/latest/filesystems/ext4/journal.html)、[metadata checksums 文档](https://www.kernel.org/doc/html/latest/filesystems/ext4/checksums.html)。这些文档解释文件系统机制，不证明候选 Windows 驱动实现符合要求。

## 后续隔离验证流程（本次未执行）

1. 用户另行提供已存在的可丢弃 ext4 镜像或独立测试盘，核对其稳定身份与来源，明确与当前双系统物理盘无关；本项目不提供格式化或原始扇区写入工具。
2. 固定驱动安装包版本、签名、许可证、Windows/内核版本及接口协议；准备基线文件、目录清单、字节数、哈希、UID/GID/mode、时间戳与特征位，保存到 Windows 用户数据目录。
3. 通过厂商受支持文件接口进行新增、修改、重命名、删除；检查冲突、权限、锁、大小写、链接、空间不足、取消和显式同步。每一步记录成功/失败及目标范围，不把内部缓存命中当作落盘成功。
4. 正常同步卸载后由 Linux 原生 ext4 驱动重新挂载测试介质，逐项核对目录、字节/哈希及元数据，收集内核日志；离线后进行不修复的文件系统完整性检查。中断恢复另用可丢弃副本，绝不作用于当前 Ubuntu。
5. 保存驱动/内核日志、完整性检查原文、特征兼容矩阵、操作结果和限制；没有证据时维持未通过。本次没有这些 Linux 重挂载或写入日志，不能宣称隔离写入已验收。

真实 Ubuntu 写入还必须另有可恢复备份及恢复验证、用户明确选择读写模式和风险确认、固定驱动兼容结论、稳定身份复核、允许的 `/home/具体用户` 白名单；禁止系统路径。满足证据也不会自动打开当前构建中的写入开关，接入须另行代码审查和授权实施。

## 代码交付边界

Ext4WritableAdapter 协议定义创建、写入、重命名、移动、删除、同步与关闭；UnsupportedWriteBackend 对全部变更/同步方法抛出 UnsupportedWriteError，无设备或文件 I/O。选择点只返回此拒绝后端，无配置、环境变量、驱动名称或自行声明 write=True 的解锁入口。UI 显示“只读：未接入已验证的受控写入驱动”，避免把服务名筛选误报成全面的“未安装”结论。只读 pytsk3 层、Windows 受控写入及原有读协议均保持兼容。
