# Windows 修改包生成与暂存服务

2026-11-07。实现 app/services/pending_changes.py 和 app/backends/offline_bundle.py。

支持新建、替换、删除普通文件、单层 mkdir 和同目录文件重命名。已有文件的原状态由 G0 已验证的独立快照接口读取；文件系统 UUID 来自实际读取器 probe，不从用户计划中接受 UUID 或旧状态。

暂存保存在 Windows 本地随机工作目录，文件内容以流式方式复制封存。重复编辑保持第一次快照，新建后删除抵消，修改后删除保留原快照；删除后新建、重命名链、重命名后编辑、新目录内写文件和重叠路径拒绝。同一路径及重命名两端可查询暂存状态，操作可按 ID 取消。失败不替换已有草稿。

修改草稿会更换 bundle ID，未变草稿重复导出保留 ID。导出使用 schema 3 共用校验与规范化，重新验证 payload 大小/哈希。目标目录必须不存在，不合并、不覆盖；manifest.json 最后写入作为完成标记，失败保留不完整目录。正常导出不表示已应用。

通过现有 pytsk3 只读后端测试五类操作导出，再由 scripts.validate_bundle 校验；同时校验源镜像哈希不变。没有更改原始设备写入策略，没有给 ext4 读取器增加写入能力。

## 可运行的命令入口

准备本地 plan.json（payload 来源按计划文件所在目录解析）：

```json
{
  "fs_relative_root": "g0",
  "operations": [
    {"type":"create_file","path":"new.txt","source":"new-content.txt",
     "metadata":{"uid":1000,"gid":1000,"mode":420}},
    {"type":"replace_file","path":"nano-b.txt","source":"replacement.txt"},
    {"type":"delete_file","path":"empty"},
    {"type":"rename_file","path":"large.bin","new_path":"renamed.bin"},
    {"type":"mkdir","path":"documents","metadata":{"uid":1000,"gid":1000,"mode":493}}
  ]
}
```

```powershell
.\.venv\Scripts\python.exe -m scripts.create_bundle --image .\g0.img --plan <本地plan.json> --output <尚不存在的导出目录>
.\.venv\Scripts\python.exe -m scripts.validate_bundle --bundle <导出目录>
```

命令只接受普通 ext4 镜像，不读取任意物理设备句柄。GUI 后续复用同一业务模块。示例不会自动执行；源镜像的父目录与文件必须实际存在，不支持的 Linux 元数据及已变化快照在 Ubuntu 再次预检。

## 当前边界

- 暂存会话在内存中维护；显式导出后包独立可用，尚无崩溃后草稿自动恢复。
- GUI、权限建议和待应用面板尚未接入。
- 不进行 Linux 写入或自动执行修改包；正式执行器仍为后续任务。
- 输入/导出路径要求稳定、可信的本地目录；Windows 本地路径检查不承诺抵御不合作进程并发替换目录。
- 单个 payload 与单包均限制 512 MiB，与当前 Ubuntu staging 上限一致；Linux 名称只保存在清单，payload 使用随机安全名称，不将 CON 等目标名直接映射成 Windows 文件名。
- 关闭会话只清理自己记录的工作文件，不递归删除用户目录。导出文件独立保留。

## 本轮验证

完整回归 263 passed, 1 skipped；随后补充总预算拒绝测试。使用用户带回且 G0 已验收的 g0.img，命令行执行五类操作导出，再运行独立 validate_bundle，均通过。测试前后镜像 SHA-256 一致。新增业务模块未接入主窗口，正式 Linux 修改包执行器仍待实现，本轮不需要再次进入 Ubuntu。
