---
doc_id: ARCH-001
title: 内部三视图原型架构
category: architecture
status: active
version: 2
created_at: 2026-08-04T14:16:11+08:00
updated_at: 2026-08-04T15:29:36+08:00
last_verified_at: 2026-08-04T15:29:36+08:00
source_of_truth: true
related_tasks: [TASK-20260804-001]
related_documents: [PRD-HAIR-IMAGE-001, TECH-STACK-001]
supersedes: null
actor_agent: ai-engineer
expert_role: ai-engineer
operation_type: update
---

# 内部三视图原型架构

```text
Browser on 127.0.0.1
  -> FastAPI API + static page
      -> SessionStore (single active session, memory)
      -> Orchestrator (front/side parallel -> back)
          -> ImageProvider
              -> FakeProvider (development/test only)
              -> NanoBananaProvider (only real provider; two standard models)
      -> TempImageStore (session directory)
      -> JSONL EventLog -> raw integer report
```

## 模块边界

- `domain`: 会话、结果集、视图、attempt、终态、错误码和不变量。
- `providers`: 一个窄接口；fake 与 Gemini 共享返回结构。它不是动态多供应商平台。
- `orchestration`: 并行、背面后置、幂等、15 秒慢调用标记、单次 65 秒硬超时、取消与迟到隔离。
- `storage`: 临时图片、哈希、读取授权、封存、TTL 删除和 `deletion_pending`。
- `telemetry`: append-only JSONL，禁止图像正文；报告按事件重建。
- `capture_quality`: 技术解码、尺寸、清晰度、基础单脸和方向检查，不声称身份或款式语义认证。
- `api`: 会话、上传、创建结果集、查询状态、一次重试、结束和报告。
- `static`: 摄像头、运行前模型选择、五款目录、三视图状态、内部警示和背面推测警示。

## 关键不变量

1. 全局同时只有一个活动会话。
2. 一个结果集由幂等键唯一确定；重复请求复用。
3. 每视图 `attempt <= 2`。
4. 背面只有在最终正面和最终侧面均技术成功时启动。
5. 重试提交后第二次结果成为最终版本；第一次仍保留在事件记录中。
6. 会话结束后结果写回令牌失效；迟到任务不得恢复读取能力。
7. fake 与 nano_banana 事件都记录 `provider_mode`；正式报告只接受全 nano_banana。
8. 模型只在新运行首次生成前可选；首次生成后锁定，结果集、事件和报告都保存实际 `model_id`/`variant`。

## Nano Banana API

`NanoBananaProvider` 从 `BANANAPRO_API_KEY` 读取 Key，调用 `POST /api/gemini/v1beta/models/{model}:generateContent`，按固定顺序发送文本和 Base64 参考图，只接受响应中的第一张有效最终输出图。没有图像、额外图、解码失败、安全拒绝、HTTP 错误和 65 秒超时都映射为冻结错误码。记录模型、variant、请求 ID、请求配置哈希、响应哈希、usage、耗时、`slow_call` 和错误，不记录 Key 或 base64。

Codex `$imagegen` 不在产品运行时内；它只生成登记为 `synthetic_imagegen` 的测试输入。真实端到端测试仍必须经过 `NanoBananaProvider`。
