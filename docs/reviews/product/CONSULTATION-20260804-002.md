---
doc_id: CONSULTATION-20260804-002
title: Nano Banana 模型切换与第三方数据边界咨询
category: product-consultation
status: completed
version: 2
created_at: 2026-08-04T15:10:49+08:00
updated_at: 2026-08-04T15:29:36+08:00
last_verified_at: 2026-08-04T15:29:36+08:00
source_of_truth: false
related_tasks: [TASK-20260804-001]
related_documents: [PRD-HAIR-IMAGE-001, DEV-20260804-003, DEV-20260804-004]
supersedes: null
actor_agent: product-manager
expert_role: product-manager
operation_type: query
---

# 咨询范围

- 路由角色：Product Manager。
- 选择原因：用户要求可更换模型，改变了 v1.4.0 已批准的模型、供应商、超时和评估一致性边界。
- 输入：用户截图与配置文档、无真人数据 API 探测、v1.4.0 PRD、当前代码与测试状态。
- 预期输出：最小可上线的模型选择规则、验收标准、隐私阻塞项和重新审批条件。

# 关键结论

- 同一供应商只开放两个普通版模型：Nano Banana 2 为默认速度优先，Nano Banana Pro 为细节优先；Plus 版不进入 MVP。
- 模型选择仅在新运行首次生成前开放；首次生成后锁定。换模型必须新建运行并重新执行 25 个结果集，禁止同一报告混用、自动回退或单结果集多模型对比。
- 15 秒改为慢调用标记；单次供应商调用 65 秒硬超时。每视图最多两次调用和明确终态保持不变。
- 调用记录、结果集和报告必须写入实际模型与 variant；API 密钥只允许放在后端环境变量。
- 已暴露密钥必须在真人测试前轮换。

# 冲突与处理

v1.4.0 的固定官方 Gemini 模型、旧端点和超时预算与新需求冲突。处理结果是进入 `prd_revision`、撤销当前开发授权、保留已完成代码并中断后端/前端实施，等待 v1.4.1 重新批准。

# 决策结果

用户明确接受未核实的第三方数据政策风险，并要求继续开发：Nano Banana 作为真实开发 API，Codex `$imagegen` 生成测试输入。隐私阻塞解除，但真人测试仍须逐人知情同意；开发和端到端测试优先使用登记为 `synthetic_imagegen` 的虚构正/侧素材，且不得计入正式真人评估。
