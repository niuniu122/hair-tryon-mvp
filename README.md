# Hair Try-on Internal MVP

仅供内部团队在 `127.0.0.1` 使用的男士发型三视图生成验证原型。权威文档入口见 [docs/INDEX.md](docs/INDEX.md)。

## 安装与测试

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pip install -e . --no-deps
.\.venv\Scripts\python.exe -m pytest -q
node --test tests/ui-state.test.mjs
```

## 本地 fake 模式

```powershell
$env:HAIR_TRYON_PROVIDER = 'fake'
.\.venv\Scripts\python.exe -m uvicorn hair_tryon.app:create_app --factory --host 127.0.0.1 --port 8000
```

浏览器打开 `http://127.0.0.1:8000`。fake 输出带有持续警示，不能进入正式报告。

## Nano Banana 真实开发 API

只在当前 PowerShell 进程中设置密钥，不要写入 `.env`、代码、前端或日志：

```powershell
$env:HAIR_TRYON_PROVIDER = 'nano_banana'
$env:BANANAPRO_API_KEY = '<在本机设置，不要提交>'
.\.venv\Scripts\python.exe -m uvicorn hair_tryon.app:create_app --factory --host 127.0.0.1 --port 8000
```

新运行默认 Nano Banana 2（`gemini-3.1-flash-image-preview`），首次生成前可换为 Nano Banana Pro（`gemini-3-pro-image-preview`）；开始生成后模型锁定。Plus、自动回退、多供应商和单运行混用模型不在 MVP 范围。

Codex `$imagegen` 只用于生成标记为 `synthetic_imagegen` 的测试输入，实际输出必须经过 Nano Banana API。正式真人测试前应轮换已在聊天或截图中暴露的密钥。
