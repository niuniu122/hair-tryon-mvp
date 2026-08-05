# Hair Try-on MVP 项目规则

## 项目目标

实现仅供内部团队在 `localhost` 使用的男士发型三视图生成验证原型。权威产品入口是 `docs/product.md`，原始批准 PRD 为 `C:/Users/Administrator/.gstack/projects/project/Administrator-unknown-design-20260804-094450.md` v1.4.0。

## 非目标

不实现正式人工审核、自动语义质检、30 人锁定验证、多模型、外部门店、顾客自助、账号支付、多人并发或生产部署。

## 技术栈与命令

- Python 3.13、FastAPI、Pydantic、HTTPX、Pillow、OpenCV headless。
- 浏览器端使用原生 HTML/CSS/JavaScript，由 FastAPI 同一进程提供，不引入前端构建链。
- 安装：`python -m pip install -e ".[dev]"`
- 测试：`python -m pytest`
- 运行：`python -m uvicorn hair_tryon.app:create_app --factory --host 127.0.0.1 --port 8000`
- 检查：`python -m compileall src tests`

## 修改边界

- 允许修改：`src/`、`tests/`、`docs/`、`scripts/` 和根目录项目配置。
- 禁止把 API Key、图像正文、base64、长期可访问图像 URL 写入代码、日志或报告。
- PRD v1.4.1 已于 `2026-08-04T15:29:36+08:00` 获明确批准，`development_authorized: true`。Nano Banana 是真实开发 API，Codex `$imagegen` 只生成测试输入。
- 修订候选范围仅为同一供应商的普通版 Nano Banana 2 与 Nano Banana Pro；单次运行首次生成后锁定模型。新增供应商、Plus 版、自动回退或单运行混用模型必须再次进入 PRD revision。
- fake provider 只用于开发和自动测试，必须有明显标记，禁止进入正式 25 组评估报告。

## 开发与验收

- 新行为严格执行 RED → GREEN → REFACTOR。
- 每个视图最多两次模型调用；正面和侧面并行，二者技术成功后才启动背面。
- v1.4.1 待批准超时口径：15 秒只标记慢调用，单次供应商调用 65 秒硬超时；每视图最多两次调用；会话空闲 30 分钟。旧的单视图 30 秒和结果集累计 65 秒预算暂停适用。
- 完成前必须更新 `docs/progress.md`、任务 handoff、开发记录和六个索引，并运行最新测试与静态检查。
- `docs/INDEX.md` 是项目恢复和文档审查的默认入口。
