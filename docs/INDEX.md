---
doc_id: DOC-INDEX-001
title: 项目文档总索引
category: index
status: active
version: 8
created_at: 2026-08-04T14:16:11+08:00
updated_at: 2026-08-04T18:31:03+08:00
last_verified_at: 2026-08-04T18:40:32+08:00
source_of_truth: true
related_tasks: [TASK-20260804-001, TASK-20260804-002]
related_documents: [PRD-HAIR-IMAGE-001, DESIGN-001, PROGRESS-001, CONSULTATION-20260804-003, CHANGE-20260804-005, CHANGE-20260804-006, ROUTING-20260804-003, DEV-20260804-007, DEV-20260804-008, REVIEW-20260804-002, QA-20260804-002, SECURITY-20260804-001]
supersedes: null
actor_agent: root
expert_role: technical-writer
operation_type: update
---

# 项目文档总索引

当前阶段：`completed`。v1.5.0 双预览界面已按批准范围完成 TDD 实现、独立浏览器 QA、代码审查和修复；后端和 API 未变。

## 权威文档

| 更新时间 | 文档 | 状态 | 摘要 | 续接位置 |
|---|---|---|---|---|
| 2026-08-04T18:31:03+08:00 | [progress.md](progress.md) | completed | v1.5.0 本地开发与验证完成 | 目标工作站烟测 |
| 2026-08-04T18:31:03+08:00 | [implementation-plan.md](implementation-plan.md) | completed | 双预览前端 TDD 与验证完成 | 运行验证 |
| 2026-08-04T16:32:53+08:00 | [tech-stack.md](tech-stack.md) | active | 固定技术栈与锁文件 | 安装/运行 |
| 2026-08-04T18:31:03+08:00 | [product.md](product.md) | active | 已批准并实现 PRD v1.5.0 | AC-UI-01 至 AC-UI-10 |
| 2026-08-04T15:29:36+08:00 | [architecture.md](architecture.md) | active | 模块、数据流与安全边界 | 服务/API |
| 2026-08-04T17:35:29+08:00 | [design.md](design.md) | active | 左输入、右结果、底部发型轨道 | 双媒体舞台 |

## 操作、评审与恢复入口

| 更新时间 | 文档 | 状态 | 摘要 | 续接位置 |
|---|---|---|---|---|
| 2026-08-04T18:31:03+08:00 | [CHANGE-20260804-006](context/changes/2026/08/CHANGE-20260804-006.md) | completed | 实现、评审和完成状态同步 | 当前证据 |
| 2026-08-04T18:31:03+08:00 | [TASK-20260804-002](context/handoffs/TASK-20260804-002.md) | completed | 双预览前端重组 handoff | 目标工作站烟测 |
| 2026-08-04T18:31:03+08:00 | [ROUTING-20260804-003](reviews/engineering/ROUTING-20260804-003.md) | completed | Frontend Developer 实施与审查路由 | 已完成 |
| 2026-08-04T18:21:00+08:00 | [REVIEW-20260804-002](reviews/engineering/REVIEW-20260804-002.md) | completed | v1.5.0 独立代码审查 | 无 blocker |
| 2026-08-04T18:21:00+08:00 | [QA-20260804-002](reviews/qa/QA-20260804-002.md) | completed | 双舞台浏览器 QA 与摄像头错误复验 | finding 已关闭 |
| 2026-08-04T18:21:00+08:00 | [DEV-20260804-008](context/development/2026/08/DEV-20260804-008.md) | completed | QA/评审竞态与状态单调性修复 | 20 项 Node |
| 2026-08-04T18:21:00+08:00 | [DEV-20260804-007](context/development/2026/08/DEV-20260804-007.md) | completed | 双预览工作台主实现 | 前端交接 |
| 2026-08-04T17:35:29+08:00 | [CHANGE-20260804-005](context/changes/2026/08/CHANGE-20260804-005.md) | completed | v1.5.0 文档与授权状态修订 | 已批准 |
| 2026-08-04T17:26:28+08:00 | [CONSULTATION-20260804-003](reviews/product/CONSULTATION-20260804-003.md) | completed | 双预览产品与前端可行性复核 | 无阻塞 |
| 2026-08-04T16:38:35+08:00 | [TASK-20260804-001](context/handoffs/TASK-20260804-001.md) | completed | 任务 handoff 与后续运行入口 | 本地运行 |
| 2026-08-04T16:38:35+08:00 | [DEV-20260804-006](context/development/2026/08/DEV-20260804-006.md) | completed | 真实 API、TDD 修复和最终验证 | 最新证据 |
| 2026-08-04T16:32:53+08:00 | [DEV-20260804-005](context/development/2026/08/DEV-20260804-005.md) | completed | provider、后端和前端实现 | 专家交接 |
| 2026-08-04T16:32:53+08:00 | [REVIEW-20260804-001](reviews/engineering/REVIEW-20260804-001.md) | completed | 工程复核与已修缺口 | 无阻塞发现 |
| 2026-08-04T16:30:00+08:00 | [SECURITY-20260804-001](reviews/security/SECURITY-20260804-001.md) | completed | 安全复核与锁文件修复 | 无未解高置信发现 |
| 2026-08-04T16:20:08+08:00 | [QA-20260804-001](reviews/qa/QA-20260804-001.md) | completed | 浏览器和真实模型 QA | 低优先级横滑提示 |
| 2026-08-04T16:32:53+08:00 | [CHANGE-20260804-004](context/changes/2026/08/CHANGE-20260804-004.md) | completed | 实现和验证文档同步 | 当前变更记录 |
| 2026-08-04T16:32:53+08:00 | [ROUTING-20260804-002](reviews/engineering/ROUTING-20260804-002.md) | completed | 专家实施与交接 | 路由完成 |
| 2026-08-04T15:29:36+08:00 | [TEST-ASSET-20260804-001](reviews/product/TEST-ASSET-20260804-001.md) | active | Codex imagegen 测试主体 | 合成输入清单 |
| 2026-08-04T15:29:36+08:00 | [CONSULTATION-20260804-002](reviews/product/CONSULTATION-20260804-002.md) | completed | 模型与数据风险决策 | 已解决 |

## 分类索引

- [按分类](context/indexes/by-category.md)
- [按领域](context/indexes/by-domain.md)
- [按状态](context/indexes/by-status.md)
- [按 Agent](context/indexes/by-agent.md)
- [按任务](context/indexes/by-task.md)
- [按日期](context/indexes/by-date.md)
