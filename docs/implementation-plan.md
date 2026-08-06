---
doc_id: IMPL-PLAN-001
title: 内部三视图 MVP 实施计划
category: implementation-plan
status: completed
version: 11
created_at: 2026-08-04T14:16:11+08:00
updated_at: 2026-08-06T10:28:21+08:00
last_verified_at: 2026-08-06T10:28:21+08:00
source_of_truth: true
related_tasks: [TASK-20260804-001, TASK-20260804-002, TASK-20260806-001]
related_documents: [PRD-HAIR-IMAGE-001, CONSULTATION-20260806-001, ROUTING-20260806-001, TASK-20260806-001]
supersedes: null
actor_agent: root
expert_role: project-shepherd
operation_type: update
---

# 实施计划与状态

## v1.5.1 中文路径分类器修复（已完成并创建 PR #2）

1. 完成：真实正面/侧面 XML 的 `AI美业` RED 测试和缺失/损坏资源用例。
2. 完成：私有 Unicode 安全加载器、内存 FileStorage、读取/空状态检查和稳定错误。
3. 完成：初始 TDD 目标 3/3 GREEN；覆盖审计后目标分支 8/8、完整 pytest 63/63，加载器路径覆盖率 85%。
4. 完成：Node 20/20、JavaScript 语法、Python `compileall` 和 `pip check`。
5. 完成：在 Windows 真实中文项目副本中导入本项目源码与级联 XML，并通过真实 API 分别提交登记合成正面和有效右侧面；两次采集均返回 201。
6. 完成：分支已推送并创建 GitHub PR #2；未自动合并或部署。
6. 完成：gstack review 无发现，QA 验收全部 PASS，DEV/handoff/progress/索引已同步。

开发批准：用户于 `2026-08-06T09:05:40+08:00` 明确输入“批准 PRD，开始开发”。核心代码范围仅 `src/hair_tryon/capture_quality.py` 与 `tests/test_capture_quality.py`，不新增依赖或迁移。

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
