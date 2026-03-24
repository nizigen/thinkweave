# MEMORY.md — 会话持久记忆（项目真值）

本文件用于记录不会频繁变化、且必须跨会话保持一致的“项目真值”。

## 1) 记忆层技术口径（当前生效）

- 使用 `cognee==0.5.5`
- 默认 provider：`graph=kuzu` + `vector=lancedb`
- `Neo4j/Qdrant` 不是当前默认实现口径；仅可作为后续可选扩展
- `MEMORY_ENABLED=false` 必须可一键关闭记忆层并回退 v1 行为

## 2) 文档/代码编辑编码协议（Windows）

- 在 PowerShell 做任何文本读写前，先执行：`.\scripts\enable_utf8_io.ps1`
- 文本变更优先使用 `apply_patch`
- 发现乱码时，先 `git restore <file>`，再重新补丁新增内容

## 3) 口径同步要求

当架构真值变化时，必须同步更新以下文件，避免会话漂移：

- `CLAUDE.md`
- `AGENTS.md`
- `docs/lessons.md`
- `docs/progress.md`（记录日期和变更说明）
