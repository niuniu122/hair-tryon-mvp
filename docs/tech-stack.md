---
doc_id: TECH-STACK-001
title: 最小技术栈
category: technical-specification
status: active
version: 3
created_at: 2026-08-04T14:16:11+08:00
updated_at: 2026-08-04T16:32:53+08:00
last_verified_at: 2026-08-04T16:32:53+08:00
source_of_truth: true
related_tasks: [TASK-20260804-001]
related_documents: [PRD-HAIR-IMAGE-001, ADR-001, SECURITY-20260804-001]
supersedes: null
actor_agent: root
expert_role: ai-engineer
operation_type: update
---

# 最小技术栈

| 层 | 选择 | 版本/约束 | 理由 |
|---|---|---|---|
| 运行时 | Python | 3.13.x | 单进程 API、静态页和异步任务 |
| Web | FastAPI / Uvicorn | 0.141.1 / 0.52.1 | 轻量异步 API 和静态文件服务 |
| 数据模型 | Pydantic | 2.13.4 | 固定请求和响应结构 |
| 模型 HTTP | HTTPX | 0.28.1 | Nano Banana Gemini 兼容边界与超时 |
| 图像 | Pillow / OpenCV headless | 12.3.0 / 4.12.0.88 | 解码、清洗、清晰度和基础人脸方向检查 |
| 上传 | python-multipart | 0.0.32 | multipart 图片上传 |
| 前端 | 原生 HTML/CSS/JavaScript | 浏览器内置 | 不增加构建链 |
| 测试 | pytest / pytest-asyncio / Node test | 9.1.1 / 1.4.0 / Node 24 | 后端、异步编排和前端状态测试 |

OpenCV 固定为 4.12.0.88，因为 5.0.0.93 Windows wheel 缺少本项目所需的 `CascadeClassifier` Python 绑定。`requirements.lock` 锁定当前验证过的直接和传递依赖；安装时先使用锁文件，再以 `--no-deps` 安装可编辑项目。

provider 只允许 `fake|nano_banana`。真实模式只从后端环境变量 `BANANAPRO_API_KEY` 取密钥，固定基址 `https://bananapro.aigenmedia.art`，允许模型仅为 `gemini-3.1-flash-image-preview` 和 `gemini-3-pro-image-preview`。15 秒标记慢调用，单次调用 65 秒硬超时；不实现 Plus、多供应商、自动回退或单运行混用模型。

不使用数据库、Redis、队列、WebSocket、Docker、前端框架或云部署。
