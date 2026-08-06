---
doc_id: DOC-INDEX-001
title: 项目文档总索引
category: index
status: active
version: 13
created_at: 2026-08-04T14:16:11+08:00
updated_at: 2026-08-06T10:28:21+08:00
last_verified_at: 2026-08-06T10:28:21+08:00
source_of_truth: true
related_tasks: [TASK-20260804-001, TASK-20260804-002, TASK-20260806-001]
related_documents: [PRD-HAIR-IMAGE-001, PROGRESS-001, IMPL-PLAN-001, CONSULTATION-20260806-001, ROUTING-20260806-001, TASK-20260806-001, DEV-20260806-001, REVIEW-20260806-001, QA-20260806-001, CHANGE-20260806-003, CHANGE-20260806-004, GITHUB-PR-2]
supersedes: null
actor_agent: root
expert_role: technical-writer
operation_type: update
---

# 项目文档总索引

当前阶段：`completed`。v1.5.1 Windows 中文路径分类器 P0 修复已完成 TDD、完整回归、中文项目 API 烟测、代码审查、分支推送和 [GitHub PR #2](https://github.com/niuniu122/hair-tryon-mvp/pull/2) 创建，无未解决 blocker。

## 权威文档

| 更新时间 | 文档 | 状态 | 摘要 | 续接位置 |
|---|---|---|---|---|
| 2026-08-06T10:28:21+08:00 | [progress.md](progress.md) | completed | PR #2 已创建，未自动合并或部署 | 用户审阅 PR |
| 2026-08-06T10:28:21+08:00 | [implementation-plan.md](implementation-plan.md) | completed | 修复计划完成并创建 PR #2 | 用户审阅 PR |
| 2026-08-06T09:05:40+08:00 | [product.md](product.md) | active | PRD v1.5.1 已批准 | AC-PATH-01 至 AC-PATH-07 |
| 2026-08-04T17:35:29+08:00 | [design.md](design.md) | active | 左输入、右结果、底部发型轨道 | 双媒体舞台 |
| 2026-08-04T16:32:53+08:00 | [tech-stack.md](tech-stack.md) | active | 固定技术栈与锁文件 | 安装/运行 |
| 2026-08-04T15:29:36+08:00 | [architecture.md](architecture.md) | active | 模块、数据流与安全边界 | 服务/API |

## 操作、评审与恢复入口

| 更新时间 | 文档 | 状态 | 摘要 | 续接位置 |
|---|---|---|---|---|
| 2026-08-06T10:28:21+08:00 | [CHANGE-20260806-004](context/changes/2026/08/CHANGE-20260806-004.md) | completed | 分支推送与 GitHub PR #2 交付完成 | 用户审阅 PR |
| 2026-08-06T10:28:21+08:00 | [TASK-20260806-001](context/handoffs/TASK-20260806-001.md) | completed | 中文路径分类器修复 handoff | 用户审阅 PR |
| 2026-08-06T10:00:00+08:00 | [CHANGE-20260806-003](context/changes/2026/08/CHANGE-20260806-003.md) | completed | 覆盖强化、中文项目烟测与 ship-ready 状态 | 创建 PR |
| 2026-08-06T10:00:00+08:00 | [QA-20260806-001](reviews/qa/QA-20260806-001.md) | completed | AC-PATH 验收、63/63 与 85% 覆盖通过 | 完成前验证 |
| 2026-08-06T10:00:00+08:00 | [REVIEW-20260806-001](reviews/engineering/REVIEW-20260806-001.md) | completed | Pre-Landing Review 无发现，覆盖门槛通过 | ship |
| 2026-08-06T10:00:00+08:00 | [DEV-20260806-001](context/development/2026/08/DEV-20260806-001.md) | completed | Unicode 安全加载、覆盖强化与 API 烟测 | ship |
| 2026-08-06T09:26:40+08:00 | [ROUTING-20260806-001](reviews/engineering/ROUTING-20260806-001.md) | completed | Minimal Change Engineer 实施路由 | 已完成 |
| 2026-08-06T09:05:40+08:00 | [CHANGE-20260806-002](context/changes/2026/08/CHANGE-20260806-002.md) | completed | PRD v1.5.1 开发批准状态 | RED 测试 |
| 2026-08-06T08:54:13+08:00 | [CHANGE-20260806-001](context/changes/2026/08/CHANGE-20260806-001.md) | completed | 轻量 PRD 与等待批准状态同步 | 用户批准 |
| 2026-08-06T08:54:13+08:00 | [CONSULTATION-20260806-001](reviews/product/CONSULTATION-20260806-001.md) | completed | 中文路径根因与最小方案复核 | PRD 批准 |
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
