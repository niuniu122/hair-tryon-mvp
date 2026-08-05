import {
  HAIRSTYLES,
  MODEL_OPTIONS,
  acceptDataNotice,
  applyGenerationSnapshot,
  attachConfirmedSession,
  captureAccepted,
  chooseHairstyle,
  chooseModel,
  chooseParticipant,
  createUiState,
  deriveUi,
  finishSession,
  markCameraReady,
  markCaptureError,
  normalizeCameraErrorCode,
  prepareRecapture,
  requestRetry,
  selectInputView,
  selectResultView,
  sessionCleanupRequest,
  startGeneration,
} from "./ui-state.mjs";

// API contract adaptation lives only in this block. UI code below consumes the
// stable camelCase shape even if backend response fields evolve.
const apiAdapter = Object.freeze({
  health(payload) {
    const body = unwrap(payload);
    return {
      providerMode: body.provider_mode ?? body.providerMode ?? body.provider ?? "unknown",
      fakeWarning: body.fake_warning ?? body.fakeWarning ?? null,
    };
  },

  catalog(payload) {
    const body = unwrap(payload);
    const records = Array.isArray(body)
      ? body
      : body.hairstyles ?? body.catalog ?? body.items ?? [];
    return records
      .map((item) => ({ id: item.id ?? item.hairstyle_id, name: item.name ?? item.label }))
      .filter((item) => item.id && item.name);
  },

  createSessionRequest(participantId) {
    return { participant_id: participantId, explicit_consent: true };
  },

  session(payload) {
    const body = unwrap(payload);
    return {
      id: body.session_id ?? body.id,
      providerMode: body.provider_mode ?? body.providerMode,
      fakeWarning: body.fake_warning ?? body.fakeWarning ?? null,
      modelId: body.model_id ?? body.modelId ?? null,
      modelLocked: body.model_locked ?? body.modelLocked ?? false,
    };
  },

  selectModelRequest(modelId) {
    return { model_id: modelId };
  },

  modelSelection(payload) {
    const body = unwrap(payload);
    return {
      modelId: body.model_id ?? body.modelId,
      modelLocked: body.model_locked ?? body.modelLocked ?? false,
    };
  },

  captureBody(blob, view) {
    const form = new FormData();
    form.append("file", blob, `${view}.jpg`);
    return form;
  },

  createGenerationRequest({ hairstyleId, modelId, idempotencyKey }) {
    void modelId;
    return {
      hairstyle_id: hairstyleId,
      idempotency_key: idempotencyKey,
    };
  },

  generation(payload) {
    const body = unwrap(payload);
    const rawViews = body.views ?? {};
    const views = {};
    for (const [backendView, uiView] of [
      ["front", "front"],
      ["side", "subject_right_profile"],
      ["subject_right_profile", "subject_right_profile"],
      ["back", "back"],
    ]) {
      if (!rawViews[backendView]) continue;
      views[uiView] = normalizeView(rawViews[backendView], uiView);
    }
    return {
      id: body.generation_set_id ?? body.set_id ?? body.id,
      status: normalizeGenerationStatus(body.state ?? body.status),
      providerMode: body.provider_mode ?? body.providerMode,
      modelId:
        body.model_id ?? body.actual_model_id ?? body.model?.id ?? body.model?.model_id ?? null,
      modelLocked: body.model_locked ?? body.modelLocked,
      views,
    };
  },

  cleanup(payload) {
    const body = unwrap(payload);
    const status = body.cleanup_status ?? body.storage_state ?? body.state ?? body.status;
    return status === "deletion_pending" ? "deletion_pending" : "deleted";
  },

  error(payload, fallbackStatus) {
    const detail = payload?.detail ?? payload?.error ?? payload;
    if (typeof detail === "string") {
      return /^[a-z0-9_-]{1,80}$/i.test(detail) ? detail : `http_${fallbackStatus}`;
    }
    if (Array.isArray(detail)) return detail[0]?.msg ?? `http_${fallbackStatus}`;
    return detail?.code ?? detail?.error_code ?? detail?.message ?? `http_${fallbackStatus}`;
  },
});

function unwrap(payload) {
  return payload?.data ?? payload ?? {};
}

function normalizeView(raw, uiView) {
  const attempts = Array.isArray(raw.attempts)
    ? raw.attempts.length
    : Number(raw.attempt ?? raw.attempt_count ?? raw.attempts ?? 0);
  const rawStatus = raw.state ?? raw.status ?? "idle";
  return {
    status: rawStatus === "queued" && uiView === "back" ? "blocked" : rawStatus,
    attempts: Number.isFinite(attempts) ? attempts : 0,
    imageId: raw.result_id ?? raw.image_id ?? raw.imageId ?? null,
    errorCode: raw.error_code ?? raw.errorCode ?? null,
  };
}

function normalizeGenerationStatus(value = "running") {
  const statuses = {
    generating_front_side: "running",
    partial_ready: "running",
    ready_for_back: "running",
    generating_back: "running",
    three_views_ready: "completed",
    partial_failure: "partial_failure",
    ended: "cancelled",
  };
  return statuses[value] ?? value;
}

const ERROR_MESSAGES = Object.freeze({
  image_decode_failed: "图片无法解码，请重新采集。",
  unsupported_format: "图片格式不受支持，请重新采集。",
  image_too_small: "画面尺寸过小，请靠近镜头后重新采集。",
  no_face: "未检测到清晰的人脸，请调整位置后重新采集。",
  multiple_faces: "画面中出现多张人脸，请仅保留一位参与者。",
  face_too_small: "人脸在画面中太小，请靠近镜头。",
  blurry: "画面清晰度不足，请保持稳定并重新采集。",
  wrong_direction: "侧面方向不符合要求，请向参与者自己的右侧转头。",
  participant_not_registered: "参与者编号不在 T01–T05 预登记范围内。",
  explicit_consent_required: "必须获得本次测试的明确同意。",
  active_session_exists: "已有一个活动测试，请先结束该运行。",
  captures_incomplete: "需要先完成正面和右侧面采集。",
  hairstyle_not_found: "所选发型不在固定目录中。",
  model_not_allowed: "所选模型不在本次批准的两个普通版模型中。",
  model_not_approved: "所选模型不在本次批准的两个普通版模型中。",
  model_locked: "本次运行已锁定模型；换模型需结束并新建运行。",
  idempotency_conflict: "本次生成请求与已创建结果集冲突。",
  generation_set_not_found: "找不到本次结果集。",
  session_not_found: "找不到本次测试会话。",
  session_ended: "本次测试已结束，图片读取已撤销。",
  technical_failure: "模型调用发生技术错误。",
  timeout: "模型调用超过 65 秒硬超时。",
  safety_rejection: "供应商安全策略拒绝了本次生成。",
  http_error: "供应商接口返回错误。",
  no_image: "供应商响应中没有可用图片。",
  invalid_response: "供应商响应格式无效。",
  camera_unavailable: "当前浏览器无法访问摄像头。",
  camera_permission_denied: "摄像头权限被拒绝，请在浏览器设置中允许后重试。",
  camera_not_ready: "摄像头画面尚未准备好，请稍候。",
  network_error: "无法连接本机服务，请确认后端仍在运行。",
  http_404: "本机 API 路由不可用，请确认后端路由和静态挂载。",
});

const VIEW_META = Object.freeze({
  front: { label: "正面", inputTabId: "input-tab-front", resultTabId: "result-tab-front" },
  subject_right_profile: {
    label: "右侧面",
    inputTabId: "input-tab-side",
    resultTabId: "result-tab-side",
  },
  back: { label: "背面", resultTabId: "result-tab-back" },
});

const dom = {
  providerBadge: document.querySelector("#provider-badge"),
  actualModelBadge: document.querySelector("#actual-model-badge"),
  fakeBanner: document.querySelector("#fake-banner"),
  sessionStatus: document.querySelector("#session-status"),
  generationStatus: document.querySelector("#generation-status"),
  inputStageStatus: document.querySelector("#input-stage-status"),
  participant: document.querySelector("#participant-id"),
  consent: document.querySelector("#explicit-consent"),
  modelSelect: document.querySelector("#model-select"),
  modelLockNote: document.querySelector("#model-lock-note"),
  endSession: document.querySelector("#end-session"),
  video: document.querySelector("#camera-preview"),
  captureImage: document.querySelector("#capture-image"),
  cameraEmpty: document.querySelector("#camera-empty"),
  cameraGuide: document.querySelector("#camera-guide"),
  canvas: document.querySelector("#capture-canvas"),
  backInputNote: document.querySelector("#back-input-note"),
  inputStage: document.querySelector("#input-stage"),
  inputStageCaption: document.querySelector("#input-stage-caption"),
  captureError: document.querySelector("#capture-error"),
  recaptureInput: document.querySelector("#recapture-input"),
  resultStage: document.querySelector("#result-stage"),
  resultImage: document.querySelector("#result-image"),
  resultPlaceholder: document.querySelector("#result-placeholder"),
  resultInference: document.querySelector("#result-inference"),
  resultStageStatus: document.querySelector("#result-stage-status"),
  resultMeta: document.querySelector("#result-meta"),
  resultError: document.querySelector("#result-error"),
  retryView: document.querySelector("#retry-view"),
  hairstyleStrip: document.querySelector("#hairstyle-strip"),
  primaryAction: document.querySelector("#primary-action"),
  summaryParticipant: document.querySelector("#summary-participant"),
  summaryHairstyle: document.querySelector("#summary-hairstyle"),
  summaryModel: document.querySelector("#summary-model"),
  activity: document.querySelector("#activity-message"),
};

let state = createUiState("checking");
let catalog = [...HAIRSTYLES];
let cameraStream = null;
let pollTimer = null;
let idempotencyKey = null;
let runEpoch = 0;
let activityMessage = "阅读数据说明，选择参与者与模型后开始运行。";
const busy = new Set();
const capturePreviewUrls = new Map();

function isActiveRun(epoch, sessionId) {
  return (
    epoch === runEpoch &&
    state.phase !== "ended" &&
    Boolean(sessionId) &&
    state.sessionId === sessionId
  );
}

function modelLabel(modelId) {
  return MODEL_OPTIONS.find(({ id }) => id === modelId)?.name ?? modelId ?? "—";
}

function providerLabel(mode) {
  const labels = {
    checking: "检查中",
    fake: "Fake provider",
    nano_banana: "Nano Banana",
    gemini: "Gemini",
    unknown: "未确认",
  };
  return labels[mode] ?? mode;
}

function describeError(code) {
  if (!code) return "发生未分类错误。";
  return `${ERROR_MESSAGES[code] ?? "操作失败，请查看后端日志。"}（${code}）`;
}

async function request(path, { method = "GET", json, body, signal } = {}) {
  const headers = new Headers();
  let requestBody = body;
  if (json !== undefined) {
    headers.set("Content-Type", "application/json");
    requestBody = JSON.stringify(json);
  }
  let response;
  try {
    response = await fetch(path, { method, headers, body: requestBody, signal });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw codedError("network_error");
  }
  const contentType = response.headers.get("content-type") ?? "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : await response.text();
  if (!response.ok) {
    const code = apiAdapter.error(payload, response.status);
    const error = codedError(code);
    error.status = response.status;
    throw error;
  }
  return payload;
}

function setBusy(key, active) {
  if (active) busy.add(key);
  else busy.delete(key);
  render();
}

function setButtonLoading(button, isLoading, label, loadingLabel) {
  button.dataset.loading = String(isLoading);
  button.setAttribute("aria-busy", String(isLoading));
  button.querySelector(".button__label").textContent = isLoading ? loadingLabel : label;
}

function renderCatalog() {
  dom.hairstyleStrip.replaceChildren();
  const zhNames = new Map(HAIRSTYLES.map(({ id, nameZh }) => [id, nameZh]));
  for (const style of catalog) {
    const label = document.createElement("label");
    label.className = "hairstyle-option";
    const input = document.createElement("input");
    input.type = "radio";
    input.name = "hairstyle";
    input.value = style.id;
    input.addEventListener("change", () => {
      state = chooseHairstyle(state, style.id);
      activityMessage = `已选择 ${style.id} ${style.name}。`;
      render();
    });
    const surface = document.createElement("span");
    surface.className = "hairstyle-option__surface";
    const code = document.createElement("span");
    code.className = "hairstyle-option__code";
    code.textContent = style.id;
    const name = document.createElement("span");
    name.className = "hairstyle-option__name";
    name.textContent = zhNames.get(style.id) ?? style.name;
    surface.append(code, name);
    label.append(input, surface);
    dom.hairstyleStrip.append(label);
  }
}

function render() {
  const ui = deriveUi(state);
  const ended = state.phase === "ended";
  const hasSession = Boolean(state.sessionId);

  dom.providerBadge.textContent = `Provider：${providerLabel(state.providerMode)}`;
  dom.actualModelBadge.textContent = `实际模型：${
    state.actualModelId ? modelLabel(state.actualModelId) : "尚未调用"
  }`;
  dom.fakeBanner.hidden = state.providerMode !== "fake";

  dom.participant.value = state.participantId ?? "";
  dom.participant.disabled = hasSession || ended || busy.has("session");
  dom.consent.checked = state.consentAccepted;
  dom.consent.disabled = hasSession || ended || busy.has("session");
  dom.modelSelect.value = state.selectedModelId;
  dom.modelSelect.disabled =
    !ui.canChooseModel ||
    busy.has("session") ||
    busy.has("model") ||
    busy.has("end-session");
  dom.modelLockNote.hidden = !ui.modelLockMessage;
  dom.modelLockNote.textContent = ui.modelLockMessage ?? "";

  dom.endSession.hidden = !hasSession || ended;
  dom.endSession.disabled = !ui.canEndSession || busy.has("end-session");
  setButtonLoading(
    dom.endSession,
    busy.has("end-session"),
    "结束运行",
    "正在清理…",
  );

  renderSessionStatus(hasSession, ended);
  renderGenerationStatus();
  renderInputTabs();
  renderInputStage(ui);
  renderResultTabs(ui);
  renderResultStage(ui, ended);
  renderPrimaryAction(ui);

  for (const input of dom.hairstyleStrip.querySelectorAll('input[name="hairstyle"]')) {
    input.checked = input.value === state.selectedHairstyle;
    input.disabled = ended || Boolean(state.generationSetId) || busy.has("end-session");
  }

  dom.summaryParticipant.textContent = `参与者 ${state.participantId ?? "—"}`;
  const selectedStyle = catalog.find(({ id }) => id === state.selectedHairstyle);
  dom.summaryHairstyle.textContent = selectedStyle
    ? `发型 ${selectedStyle.id} ${selectedStyle.name}`
    : "发型 —";
  dom.summaryModel.textContent = modelLabel(state.selectedModelId);
  dom.activity.textContent = ui.cleanupMessage ?? activityMessage;
}

function renderSessionStatus(hasSession, ended) {
  dom.sessionStatus.className = "status-pill";
  if (ended) {
    dom.sessionStatus.classList.add(
      state.cleanupStatus === "deletion_pending" ? "status-pill--error" : "status-pill--success",
    );
    dom.sessionStatus.textContent =
      state.cleanupStatus === "deletion_pending" ? "清理待重试" : "已结束";
    return;
  }
  dom.sessionStatus.classList.add(hasSession ? "status-pill--success" : "status-pill--neutral");
  dom.sessionStatus.textContent = hasSession ? "运行中" : "未开始";
}

function renderGenerationStatus() {
  const presentation = presentGeneration(state.generationStatus);
  dom.generationStatus.className = `status-pill ${presentation.className}`;
  dom.generationStatus.textContent = presentation.label;
}

function renderInputTabs() {
  for (const tab of document.querySelectorAll("[data-input-view]")) {
    const view = tab.dataset.inputView;
    const selected = view === state.activeInputView;
    tab.setAttribute("aria-selected", String(selected));
    tab.tabIndex = selected ? 0 : -1;
    const status = state.captureErrors[view]
      ? "需重采"
      : state.captures[view]
        ? "已冻结"
        : state.cameraReady
          ? "可采集"
          : "待采集";
    tab.querySelector("[data-tab-state]").textContent = status;
    tab.dataset.status = state.captureErrors[view]
      ? "failed"
      : state.captures[view]
        ? "succeeded"
        : state.cameraReady
          ? "running"
          : "idle";
  }
}

function renderInputStage(ui) {
  const { view, mode, errorCode, showBackNotCaptured } = ui.inputStage;
  const meta = VIEW_META[view];
  const previewUrl = capturePreviewUrls.get(view);
  const frozen = mode === "frozen" && Boolean(previewUrl);
  const live = mode === "live";

  dom.inputStage.setAttribute("aria-labelledby", meta.inputTabId);
  dom.inputStage.dataset.mode = mode;
  dom.video.hidden = !live;
  dom.captureImage.hidden = !frozen;
  if (frozen) {
    dom.captureImage.src = previewUrl;
    dom.captureImage.alt = `${meta.label}冻结的原始照片`;
  } else {
    dom.captureImage.removeAttribute("src");
  }
  dom.cameraGuide.hidden = !live;
  dom.backInputNote.hidden = !showBackNotCaptured;

  const emptyCopy = inputEmptyCopy(mode, meta.label);
  dom.cameraEmpty.hidden = live || frozen;
  if (!dom.cameraEmpty.hidden) {
    dom.cameraEmpty.querySelector("strong").textContent = emptyCopy.title;
    dom.cameraEmpty.querySelector("p").textContent = emptyCopy.detail;
  }

  dom.inputStageCaption.textContent = inputCaption(view, mode);
  dom.captureError.hidden = !errorCode;
  dom.captureError.textContent = errorCode ? describeError(errorCode) : "";
  dom.recaptureInput.hidden =
    !state.captures[view] || Boolean(state.generationSetId) || state.phase === "ended";
  dom.recaptureInput.textContent = `重新采集${meta.label}`;

  dom.inputStageStatus.className = "status-pill";
  if (errorCode) {
    dom.inputStageStatus.classList.add("status-pill--error");
    dom.inputStageStatus.textContent = `${meta.label}需重采`;
  } else if (mode === "frozen") {
    dom.inputStageStatus.classList.add("status-pill--success");
    dom.inputStageStatus.textContent = `${meta.label}已冻结`;
  } else if (mode === "live") {
    dom.inputStageStatus.classList.add("status-pill--running");
    dom.inputStageStatus.textContent = `${meta.label}实时预览`;
  } else {
    dom.inputStageStatus.classList.add("status-pill--neutral");
    dom.inputStageStatus.textContent = mode === "ended" ? "输入已撤销" : "等待采集";
  }
}

function inputEmptyCopy(mode, label) {
  if (mode === "ended") {
    return { title: "运行已结束", detail: "图片读取已撤销；开始新运行可重新采集。" };
  }
  if (mode === "notice") {
    return { title: "等待开始运行", detail: "选择参与者、确认同意后使用下方主按钮开始。" };
  }
  if (mode === "camera_required") {
    return { title: "摄像头尚未开启", detail: "点击下方主按钮授权；画面仅在本机浏览器预览。" };
  }
  return { title: `${label}等待采集`, detail: "使用下方主按钮冻结当前画面。" };
}

function inputCaption(view, mode) {
  if (mode === "ended") return "本次运行的原始图片已不可读取。";
  if (mode === "frozen") return `${VIEW_META[view].label}已冻结，可与右侧同角度结果对照。`;
  if (view === "subject_right_profile") {
    return "向参与者自己的右侧转头，保留完整头部与侧脸轮廓。";
  }
  return "正视镜头，完整露出头部和面部轮廓。";
}

function renderResultTabs(ui) {
  for (const tab of document.querySelectorAll("[data-result-view]")) {
    const view = tab.dataset.resultView;
    const selected = view === state.activeResultView;
    tab.setAttribute("aria-selected", String(selected));
    tab.tabIndex = selected ? 0 : -1;
    tab.dataset.status = ui.views[view].status;
    const label = resultTabStatus(ui.views[view].status);
    tab.querySelector("[data-tab-state]").textContent =
      view === "back" ? `AI 推测 · ${label}` : label;
  }
}

function resultTabStatus(status) {
  const labels = {
    idle: "等待",
    queued: "排队",
    blocked: "等待正侧面",
    running: "生成中",
    succeeded: "已完成",
    failed: "失败",
    cancelled: "已取消",
  };
  return labels[status] ?? "等待";
}

function renderResultStage(ui, ended) {
  const viewName = ui.resultStage.view;
  const view = ui.resultStage;
  const meta = VIEW_META[viewName];
  const status = ended ? "cancelled" : view.status;
  const hasImage = !ended && Boolean(view.imageId);

  dom.resultStage.setAttribute("aria-labelledby", meta.resultTabId);
  dom.resultStage.dataset.status = status;
  dom.resultInference.hidden = viewName !== "back";
  dom.resultImage.hidden = !hasImage;
  dom.resultPlaceholder.hidden = hasImage;
  if (hasImage) {
    if (dom.resultImage.dataset.imageId !== view.imageId) {
      dom.resultImage.src = `/api/sessions/${encodeURIComponent(
        state.sessionId,
      )}/images/${encodeURIComponent(view.imageId)}`;
      dom.resultImage.dataset.imageId = view.imageId;
    }
    dom.resultImage.alt = `${meta.label}生成的发型效果`;
  } else {
    dom.resultImage.removeAttribute("src");
    delete dom.resultImage.dataset.imageId;
    const placeholder = resultPlaceholder(status, viewName);
    dom.resultPlaceholder.querySelector(".result-placeholder__index").textContent =
      { front: "01", subject_right_profile: "02", back: "03" }[viewName];
    dom.resultPlaceholder.querySelector("strong").textContent = placeholder.title;
    dom.resultPlaceholder.querySelector("p").textContent = placeholder.detail;
  }

  dom.resultStageStatus.textContent = resultStageStatus(status);
  dom.resultMeta.textContent = `${viewName === "back" ? "AI 推测 · " : ""}当前视图 ${
    view.attempts
  }/2 次`;
  dom.resultError.hidden = !view.errorCode;
  dom.resultError.textContent = view.errorCode ? describeError(view.errorCode) : "";
  const retryKey = `retry-${viewName}`;
  dom.retryView.hidden = !view.canRetry || ended;
  dom.retryView.disabled =
    !view.canRetry || busy.has(retryKey) || busy.has("end-session");
  setButtonLoading(
    dom.retryView,
    busy.has(retryKey),
    view.status === "succeeded" ? "再生成一次" : "重试此视图",
    "正在提交…",
  );
}

function resultPlaceholder(status, view) {
  if (status === "running" || status === "queued") {
    return { title: "正在生成", detail: "完成的结果会立即显示，可先查看其他页签。" };
  }
  if (status === "failed") {
    return { title: "此视图生成失败", detail: "成功视图仍会保留；可在此处局部重试一次。" };
  }
  if (status === "cancelled") {
    return { title: "运行已结束", detail: "结果图片读取已撤销。" };
  }
  if (view === "back") {
    return { title: "等待 AI 推测", detail: "正面与右侧面成功后开始；本次不会采集背面。" };
  }
  return { title: "等待生成", detail: "完成两张采集并选择一款发型。" };
}

function resultStageStatus(status) {
  const labels = {
    idle: "尚未调用",
    queued: "已进入队列",
    blocked: "等待正面与右侧面",
    running: "模型生成中",
    succeeded: "已完成",
    failed: "生成失败",
    cancelled: "已取消",
  };
  return labels[status] ?? "尚未调用";
}

function renderPrimaryAction(ui) {
  const action = ui.primaryAction;
  const busyKey = primaryBusyKey(action);
  const isBusy = Boolean(busyKey && busy.has(busyKey));
  const hasBlockingBusy = ["session", "camera", "generation", "model", "end-session"].some((key) => busy.has(key)) ||
    [...busy].some((key) => key.startsWith("capture-"));
  dom.primaryAction.disabled = !action.enabled || hasBlockingBusy;
  dom.primaryAction.dataset.action = action.id;
  setButtonLoading(
    dom.primaryAction,
    isBusy,
    action.label,
    primaryLoadingLabel(action),
  );
}

function primaryBusyKey(action) {
  if (action.id === "start_session") return "session";
  if (action.id === "open_camera") return "camera";
  if (action.id === "capture") return `capture-${action.view}`;
  if (action.id === "generate") return "generation";
  return null;
}

function primaryLoadingLabel(action) {
  if (action.id === "start_session") return "正在建立…";
  if (action.id === "open_camera") return "正在请求权限…";
  if (action.id === "capture") return "正在检查…";
  if (action.id === "generate") return "正在创建结果集…";
  return action.label;
}

function presentGeneration(status) {
  const mapping = {
    idle: { label: "等待输入", className: "status-pill--neutral" },
    running: { label: "生成中", className: "status-pill--running" },
    completed: { label: "三视图完成", className: "status-pill--success" },
    partial_failure: { label: "部分失败", className: "status-pill--error" },
    failed: { label: "生成失败", className: "status-pill--error" },
    cancelled: { label: "已取消", className: "status-pill--neutral" },
  };
  return mapping[status] ?? mapping.idle;
}

function stopStream(stream) {
  for (const track of stream?.getTracks?.() ?? []) track.stop();
  if (dom.video.srcObject === stream) dom.video.srcObject = null;
}

function stopCamera() {
  const streams = new Set([cameraStream, dom.video.srcObject].filter(Boolean));
  for (const stream of streams) stopStream(stream);
  cameraStream = null;
  dom.video.srcObject = null;
}

function clearCapturePreviews() {
  for (const url of capturePreviewUrls.values()) URL.revokeObjectURL(url);
  capturePreviewUrls.clear();
  dom.captureImage.removeAttribute("src");
  dom.captureImage.hidden = true;
}

async function startCamera() {
  if (!navigator.mediaDevices?.getUserMedia) throw codedError("camera_unavailable");
  let stream = null;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 960 } },
    });
    dom.video.srcObject = stream;
    await dom.video.play();
    return stream;
  } catch (error) {
    stopStream(stream);
    throw codedError(normalizeCameraErrorCode(error));
  }
}

function codedError(code) {
  const error = new Error(code);
  error.code = code;
  return error;
}

async function captureFrame() {
  if (!cameraStream || !dom.video.videoWidth || !dom.video.videoHeight) {
    throw codedError("camera_not_ready");
  }
  const scale = Math.min(1, 1280 / dom.video.videoWidth);
  dom.canvas.width = Math.round(dom.video.videoWidth * scale);
  dom.canvas.height = Math.round(dom.video.videoHeight * scale);
  const context = dom.canvas.getContext("2d", { alpha: false });
  context.drawImage(dom.video, 0, 0, dom.canvas.width, dom.canvas.height);
  return new Promise((resolve, reject) => {
    dom.canvas.toBlob(
      (blob) => (blob ? resolve(blob) : reject(codedError("image_decode_failed"))),
      "image/jpeg",
      0.92,
    );
  });
}

function saveCapturePreview(view, blob) {
  const previous = capturePreviewUrls.get(view);
  if (previous) URL.revokeObjectURL(previous);
  capturePreviewUrls.set(view, URL.createObjectURL(blob));
}

function schedulePoll(delay = 750) {
  window.clearTimeout(pollTimer);
  if (state.phase === "ended" || !state.generationSetId) return;
  pollTimer = window.setTimeout(pollGeneration, delay);
}

function isGenerationTerminal(status) {
  return ["completed", "partial_failure", "failed", "cancelled"].includes(status);
}

async function pollGeneration() {
  if (!state.sessionId || !state.generationSetId || state.phase === "ended") return;
  const operationEpoch = runEpoch;
  const sessionId = state.sessionId;
  const generationSetId = state.generationSetId;
  try {
    const payload = await request(
      `/api/sessions/${encodeURIComponent(sessionId)}/generation-sets/${encodeURIComponent(
        generationSetId,
      )}`,
    );
    if (!isActiveRun(operationEpoch, sessionId) || state.generationSetId !== generationSetId) {
      return;
    }
    const snapshot = apiAdapter.generation(payload);
    state = applyGenerationSnapshot(state, snapshot);
    activityMessage = statusActivity(snapshot.status);
    render();
    if (!isGenerationTerminal(snapshot.status)) schedulePoll();
  } catch (error) {
    if (!isActiveRun(operationEpoch, sessionId) || state.generationSetId !== generationSetId) {
      return;
    }
    if (error.code === "session_ended") return;
    activityMessage = `${describeError(error.code)} 将继续查询状态。`;
    render();
    schedulePoll(1500);
  }
}

function statusActivity(status) {
  const completeCount = Object.values(state.views).filter(
    ({ status: viewStatus }) => viewStatus === "succeeded",
  ).length;
  if (status === "completed") return "三视图均已生成。背面结果仍是 AI 推测。";
  if (status === "partial_failure") {
    return `当前 ${completeCount}/3 个视图成功；失败视图可在画布内重试一次。`;
  }
  if (completeCount > 0) return `已显示 ${completeCount}/3 个结果，其余视图仍在生成。`;
  return "正面与右侧面正在并行生成；完成的结果会立即显示。";
}

async function createSession() {
  if (!deriveUi(state).canStartSession || busy.has("session")) return;
  let createdSessionId = null;
  setBusy("session", true);
  try {
    const payload = await request("/api/sessions", {
      method: "POST",
      json: apiAdapter.createSessionRequest(state.participantId),
    });
    const session = apiAdapter.session(payload);
    if (!session.id) throw codedError("invalid_response");
    createdSessionId = session.id;
    let confirmedModelId = session.modelId;
    if (session.modelId !== state.selectedModelId) {
      const selectionPayload = await request(
        `/api/sessions/${encodeURIComponent(session.id)}/model`,
        {
          method: "PUT",
          json: apiAdapter.selectModelRequest(state.selectedModelId),
        },
      );
      const selection = apiAdapter.modelSelection(selectionPayload);
      if (selection.modelId !== state.selectedModelId) throw codedError("invalid_response");
      confirmedModelId = selection.modelId;
    }
    const nextState = attachConfirmedSession(state, {
      sessionId: session.id,
      providerMode: session.providerMode ?? state.providerMode,
      modelId: confirmedModelId,
    });
    if (nextState === state) throw codedError("invalid_response");
    runEpoch += 1;
    state = nextState;
    createdSessionId = null;
    activityMessage = "运行已建立。下一步开启摄像头并采集正面。";
  } catch (error) {
    if (createdSessionId) {
      try {
        await request(`/api/sessions/${encodeURIComponent(createdSessionId)}`, {
          method: "DELETE",
        });
      } catch {
        // The original model-selection failure remains the actionable message.
      }
    }
    activityMessage = describeError(error.code);
  } finally {
    setBusy("session", false);
  }
}

async function openCamera() {
  if (busy.has("camera") || !deriveUi(state).canRequestCamera) return;
  const operationEpoch = runEpoch;
  const sessionId = state.sessionId;
  setBusy("camera", true);
  try {
    const stream = await startCamera();
    if (!isActiveRun(operationEpoch, sessionId)) {
      stopStream(stream);
      return;
    }
    cameraStream = stream;
    state = markCameraReady(state);
    activityMessage = "摄像头已开启。请先冻结正面，再冻结参与者右侧面。";
  } catch (error) {
    if (isActiveRun(operationEpoch, sessionId)) {
      activityMessage = describeError(error.code);
    }
  } finally {
    setBusy("camera", false);
  }
}

async function captureView(view) {
  const key = `capture-${view}`;
  if (busy.has(key) || !deriveUi(state).canCapture) return;
  const operationEpoch = runEpoch;
  const sessionId = state.sessionId;
  state = selectInputView(state, view);
  setBusy(key, true);
  try {
    const blob = await captureFrame();
    if (!isActiveRun(operationEpoch, sessionId)) return;
    await request(
      `/api/sessions/${encodeURIComponent(sessionId)}/captures/${encodeURIComponent(view)}`,
      { method: "POST", body: apiAdapter.captureBody(blob, view) },
    );
    if (!isActiveRun(operationEpoch, sessionId)) return;
    saveCapturePreview(view, blob);
    state = captureAccepted(state, view);
    activityMessage =
      view === "front"
        ? "正面已通过检查并冻结。请继续采集右侧面。"
        : "右侧面已通过检查并冻结。请选择发型后生成。";
  } catch (error) {
    if (isActiveRun(operationEpoch, sessionId)) {
      state = markCaptureError(state, view, error.code ?? "technical_failure");
      activityMessage = describeError(error.code);
    }
  } finally {
    setBusy(key, false);
  }
}

async function generateViews() {
  if (!deriveUi(state).canGenerate || busy.has("generation")) return;
  const operationEpoch = runEpoch;
  const sessionId = state.sessionId;
  idempotencyKey ||= globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`;
  setBusy("generation", true);
  try {
    const payload = await request(
      `/api/sessions/${encodeURIComponent(sessionId)}/generation-sets`,
      {
        method: "POST",
        json: apiAdapter.createGenerationRequest({
          hairstyleId: state.selectedHairstyle,
          modelId: state.selectedModelId,
          idempotencyKey,
        }),
      },
    );
    if (!isActiveRun(operationEpoch, sessionId)) return;
    const snapshot = apiAdapter.generation(payload);
    if (!snapshot.id) throw codedError("invalid_response");
    state = startGeneration(state, snapshot.id);
    state = applyGenerationSnapshot(state, snapshot);
    activityMessage = "模型已锁定。正面与右侧面正在并行生成。";
    if (!isGenerationTerminal(snapshot.status)) schedulePoll(250);
  } catch (error) {
    if (isActiveRun(operationEpoch, sessionId)) {
      activityMessage = describeError(error.code);
    }
  } finally {
    setBusy("generation", false);
  }
}

async function retryActiveView() {
  const view = state.activeResultView;
  if (!deriveUi(state).views[view].canRetry) return;
  const key = `retry-${view}`;
  const operationEpoch = runEpoch;
  const sessionId = state.sessionId;
  const generationSetId = state.generationSetId;
  setBusy(key, true);
  try {
    const backendView = view === "subject_right_profile" ? "side" : view;
    const payload = await request(
      `/api/sessions/${encodeURIComponent(sessionId)}/generation-sets/${encodeURIComponent(
        generationSetId,
      )}/views/${backendView}/retry`,
      { method: "POST", json: {} },
    );
    if (!isActiveRun(operationEpoch, sessionId) || state.generationSetId !== generationSetId) {
      return;
    }
    state = requestRetry(state, view);
    state = applyGenerationSnapshot(state, apiAdapter.generation(payload));
    activityMessage = "已提交该视图的第 2 次、也是最后一次生成。";
    schedulePoll(250);
  } catch (error) {
    if (isActiveRun(operationEpoch, sessionId) && state.generationSetId === generationSetId) {
      activityMessage = describeError(error.code);
    }
  } finally {
    setBusy(key, false);
  }
}

async function endSession() {
  if (!deriveUi(state).canEndSession || busy.has("end-session")) return;
  const sessionId = state.sessionId;
  setBusy("end-session", true);
  runEpoch += 1;
  window.clearTimeout(pollTimer);
  stopCamera();
  try {
    const payload = await request(`/api/sessions/${encodeURIComponent(sessionId)}`, {
      method: "DELETE",
    });
    clearCapturePreviews();
    state = finishSession(state, apiAdapter.cleanup(payload));
    activityMessage = deriveUi(state).cleanupMessage;
  } catch (error) {
    activityMessage = describeError(error.code);
  } finally {
    setBusy("end-session", false);
  }
}

async function runPrimaryAction() {
  const action = deriveUi(state).primaryAction;
  if (!action.enabled) return;
  if (action.id === "start_session") await createSession();
  else if (action.id === "open_camera") await openCamera();
  else if (action.id === "capture") await captureView(action.view);
  else if (action.id === "generate") await generateViews();
}

function bindTablist(selector, select) {
  const tabs = [...document.querySelectorAll(selector)];
  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => select(tab));
    tab.addEventListener("keydown", (event) => {
      let nextIndex = null;
      if (["ArrowRight", "ArrowDown"].includes(event.key)) nextIndex = (index + 1) % tabs.length;
      if (["ArrowLeft", "ArrowUp"].includes(event.key)) {
        nextIndex = (index - 1 + tabs.length) % tabs.length;
      }
      if (event.key === "Home") nextIndex = 0;
      if (event.key === "End") nextIndex = tabs.length - 1;
      if (nextIndex === null) return;
      event.preventDefault();
      tabs[nextIndex].click();
      tabs[nextIndex].focus();
    });
  });
}

dom.participant.addEventListener("change", () => {
  state = dom.participant.value
    ? chooseParticipant(state, dom.participant.value)
    : { ...state, participantId: null };
  render();
});

dom.consent.addEventListener("change", () => {
  state = dom.consent.checked
    ? acceptDataNotice(state)
    : { ...state, consentAccepted: false, phase: "notice" };
  render();
});

dom.modelSelect.addEventListener("change", async () => {
  const previousState = state;
  const nextState = chooseModel(state, dom.modelSelect.value);
  if (nextState === state) return;
  state = nextState;
  if (!state.sessionId) {
    activityMessage = `本次运行选择 ${modelLabel(state.selectedModelId)}；首次生成后锁定。`;
    render();
    return;
  }
  const operationEpoch = runEpoch;
  const sessionId = state.sessionId;
  setBusy("model", true);
  try {
    const payload = await request(`/api/sessions/${encodeURIComponent(sessionId)}/model`, {
      method: "PUT",
      json: apiAdapter.selectModelRequest(state.selectedModelId),
    });
    if (!isActiveRun(operationEpoch, sessionId)) return;
    const selection = apiAdapter.modelSelection(payload);
    if (selection.modelId !== state.selectedModelId) throw codedError("invalid_response");
    activityMessage = `本次运行已选择 ${modelLabel(selection.modelId)}；首次生成后锁定。`;
  } catch (error) {
    if (isActiveRun(operationEpoch, sessionId)) {
      state = previousState;
      activityMessage = describeError(error.code);
    }
  } finally {
    setBusy("model", false);
  }
});

bindTablist("[data-input-view]", (tab) => {
  state = selectInputView(state, tab.dataset.inputView);
  render();
});

bindTablist("[data-result-view]", (tab) => {
  state = selectResultView(state, tab.dataset.resultView);
  render();
});

dom.recaptureInput.addEventListener("click", () => {
  const view = state.activeInputView;
  const nextState = prepareRecapture(state, view);
  if (nextState === state) return;
  state = nextState;
  activityMessage = `${VIEW_META[view].label}已返回实时预览；使用主按钮重新冻结。`;
  render();
});

dom.retryView.addEventListener("click", retryActiveView);
dom.primaryAction.addEventListener("click", runPrimaryAction);
dom.endSession.addEventListener("click", endSession);

async function initialize() {
  renderCatalog();
  render();
  const [healthResult, catalogResult] = await Promise.allSettled([
    request("/api/health"),
    request("/api/catalog"),
  ]);
  if (healthResult.status === "fulfilled") {
    const health = apiAdapter.health(healthResult.value);
    state = { ...state, providerMode: health.providerMode };
  } else {
    state = { ...state, providerMode: "unknown" };
    activityMessage = describeError(healthResult.reason.code);
  }
  if (catalogResult.status === "fulfilled") {
    const backendCatalog = apiAdapter.catalog(catalogResult.value);
    if (backendCatalog.length === 5) catalog = backendCatalog;
  }
  renderCatalog();
  render();
}

window.addEventListener("beforeunload", () => {
  const cleanup = sessionCleanupRequest(state);
  if (cleanup) void fetch(cleanup.path, cleanup.options).catch(() => {});
  window.clearTimeout(pollTimer);
  stopCamera();
  clearCapturePreviews();
});

initialize();
