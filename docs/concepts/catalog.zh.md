# 策略目录

## 快照

`get_catalog_snapshot` 默认返回精简 header（计数、哈希、溯源、
`extensions.entry_count`），不含 1,155 条记录列表——约 340 字节而非约
315 KB。设置 `include_entries=true` 可用 `limit`（1-100）与 `offset` 分页；
分页报告 `total`/`has_more`/`truncated`。每条打包记录的
`source_available=false`：搜索与溯源可用，但原始源码字节未随包分发。

## 搜索

`search_strategy_catalog` 以确定性排名匹配文本 token 与 archetype 过滤，
返回 `total`/`has_more`/`offset` 元数据与可操作的空结果建议；未知 archetype
会枚举合法值。

## 带源码刷新

`refresh_strategy_catalog` 扫描已注册 target root（仅 AST，最多 5,000 个
文件）或重建双 functional/package 语料。扫描只做哈希与解析——语料文件绝不
被导入或执行。刷新使用 (mtime,size) 指纹缓存（未变文件不重新哈希）、单事务
写入条目，并清除已删除源文件的陈旧条目。

## 模板

`list_strategy_templates`（工具与资源）返回全部 14 个 archetype/profile
组合；`inspect_strategy` 不导入地读取打包或带源码元数据，并在源码字节自刷新
以来发生变化时报告 staleness 诊断。
