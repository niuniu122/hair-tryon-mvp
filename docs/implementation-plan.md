---
doc_id: IMPL-PLAN-001
title: 内部三视图 MVP 实施计划
category: implementation-plan
status: completed
version: 6
created_at: 2026-08-04T14:16:11+08:00
updated_at: 2026-08-04T18:31:03+08:00
last_verified_at: 2026-08-04T18:40:32+08:00
source_of_truth: true
related_tasks: [TASK-20260804-001, TASK-20260804-002]
related_documents: [PRD-HAIR-IMAGE-001, DESIGN-001, CONSULTATION-20260804-003, ARCH-001, REVIEW-20260804-001, REVIEW-20260804-002, QA-20260804-002]
supersedes: null
actor_agent: root
expert_role: project-shepherd
operation_type: update
---

# 实施计划与状态

1. 完成：领域状态、每视图最多两次、重试定稿和背面门槛。
2. 完成：fake 与 Nano Banana provider、密钥隔离、响应解析、15 秒慢调用和 65 秒硬超时。
3. 完成：正侧并行、部分结果、背面后置、取消和迟到结果隔离。
4. 完成：图片哈希、EXIF 清洗、读取撤销、删除重试、JSONL 和 fake/混模型报告门禁。
5. 完成：会话、上传、模型选择与锁定、幂等生成、状态、重试、结束和报告 API。
6. 完成：摄像头采集、两模型选择、五款目录、结果状态、一次重试、警示和页面关闭清理。
7. 完成：pytest 55 项、Node 11 项、JS 语法、compileall、pip check、浏览器、文档与安全验证。

## v1.5.0 双预览界面修订（已完成）

1. 完成：先以 RED 测试固定活动标签、舞台状态、手动选择保护、动态主按钮、重采、摄像头错误和并发竞态，再实现 GREEN。
2. 完成：页面重组为顶部工具条、左输入舞台、右结果舞台、底部发型轨道和单一动态主按钮；API 与后端数据结构未变。
3. 完成：统一标签、舞台和状态渲染，保留模型锁定、幂等、每视图唯一重试和 Fake provider 警示。
4. 完成：Node 20 项、pytest 55 项、JS 语法、Edge 双舞台/键盘/720px 有效视口/清理验证通过；独立 QA 和 Code Reviewer 无未解决 blocker。

该修订不需要安装依赖、修改 API、数据库或 provider。v1.5.0 已于 `2026-08-04T17:35:29+08:00` 获明确批准。

真实 Key 只在进程环境中临时使用，不写文件。Codex imagegen 合成输入和 fake 运行不进入正式真人 5×5 评估。正式真人摄像头烟测、Chrome 200% 复验和评估活动属于上线前操作，不扩展当前代码范围。
