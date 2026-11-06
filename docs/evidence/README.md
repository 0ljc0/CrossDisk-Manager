# 本地验收证据归档

此目录的原始 ZIP 仅在本地保留，由 .gitignore 排除，不随源码上传 GitHub。公开的复核摘要位于 docs 下对应 RESULT JSON；复验工具源码位于 scripts/。克隆仓库不会获得本地测试镜像或原始结果包。

2026-11-07 清理时，将项目根目录的原始结果 ZIP 移到此目录，保留文件名和 SHA-256；清单见 ../CLEANUP_2026-11-07.json。现有正式交付包没有改动。

G0_fixture_2026-11-06.zip 包含 g0.img、truth.json 和 e2fsck.txt。压缩前已核对镜像摘要与 Linux 真值一致，压缩后再次核对。原始 128 MiB 镜像已从根目录移除，需要复验时可将此 ZIP 解压到新的测试目录。

结果 ZIP 是原始证据，docs 下 RESULT JSON 和 PHASE6 文档是此前的复核记录。早期恢复 V1/V2 未提供的结果包不在本目录。

旧实验工具包及 G0 解压副本已删除，相关源码保留在 scripts/，需要时可以重新生成。最新版 Ubuntu 工具仍包含在 dist/CrossDiskManager/Ubuntu-tools 和正式交付 ZIP 中。
