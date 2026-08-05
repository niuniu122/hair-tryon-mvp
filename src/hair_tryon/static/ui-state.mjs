export const HAIRSTYLES = Object.freeze([
  { id: "H01", name: "Buzz Cut", nameZh: "寸头" },
  { id: "H02", name: "Crew Cut", nameZh: "圆寸" },
  { id: "H03", name: "French Crop", nameZh: "法式短碎" },
  { id: "H04", name: "Side Part", nameZh: "侧分短发" },
  { id: "H05", name: "Short Quiff", nameZh: "短款飞机头" },
]);

export const PARTICIPANTS = Object.freeze(["T01", "T02", "T03", "T04", "T05"]);

export const MODEL_OPTIONS = Object.freeze([
  {
    id: "gemini-3.1-flash-image-preview",
    name: "Nano Banana 2",
    description: "速度优先",
  },
  {
    id: "gemini-3-pro-image-preview",
    name: "Nano Banana Pro",
    description: "细节优先",
  },
]);

const CAPTURE_VIEWS = new Set(["front", "subject_right_profile"]);

const createView = (isAiInferred = false) => ({
  status: "idle",
  attempts: 0,
  imageId: null,
  errorCode: null,
  isAiInferred,
});

export function createUiState(providerMode = "unknown") {
  return {
    phase: "notice",
    providerMode,
    selectedModelId: MODEL_OPTIONS[0].id,
    actualModelId: null,
    modelLocked: false,
    consentAccepted: false,
    participantId: null,
    sessionId: null,
    cameraReady: false,
    captures: { front: false, subject_right_profile: false },
    captureErrors: { front: null, subject_right_profile: null },
    activeInputView: "front",
    lastInputView: "front",
    activeResultView: "front",
    resultSelectionManual: false,
    selectedHairstyle: null,
    generationSetId: null,
    generationStatus: "idle",
    views: {
      front: createView(),
      subject_right_profile: createView(),
      back: createView(true),
    },
    cleanupStatus: null,
  };
}

export function acceptDataNotice(state) {
  if (state.phase === "ended") return state;
  return { ...state, consentAccepted: true, phase: "ready" };
}

export function attachSession(state, sessionId) {
  if (
    !state.consentAccepted ||
    !state.participantId ||
    !sessionId ||
    state.phase === "ended"
  ) {
    return state;
  }
  return { ...state, sessionId, phase: "capturing" };
}

export function attachConfirmedSession(
  state,
  { sessionId, providerMode = state.providerMode, modelId } = {},
) {
  if (modelId !== state.selectedModelId) return state;
  return attachSession({ ...state, providerMode }, sessionId);
}

export function chooseParticipant(state, participantId) {
  if (state.phase === "ended" || !PARTICIPANTS.includes(participantId)) return state;
  return { ...state, participantId };
}

export function captureAccepted(state, view) {
  if (!CAPTURE_VIEWS.has(view) || state.phase === "ended") return state;
  const nextInputView =
    view === "front" && !state.captures.subject_right_profile
      ? "subject_right_profile"
      : view;
  return {
    ...state,
    captures: { ...state.captures, [view]: true },
    captureErrors: { ...state.captureErrors, [view]: null },
    activeInputView: nextInputView,
    lastInputView: nextInputView,
  };
}

export function markCameraReady(state) {
  if (!state.sessionId || state.phase === "ended") return state;
  return { ...state, cameraReady: true };
}

export function normalizeCameraErrorCode(error) {
  if (typeof error?.code === "string" && error.code.startsWith("camera_")) {
    return error.code;
  }
  return ["NotAllowedError", "SecurityError"].includes(error?.name)
    ? "camera_permission_denied"
    : "camera_unavailable";
}

export function markCaptureError(state, view, errorCode) {
  if (!CAPTURE_VIEWS.has(view) || state.phase === "ended") return state;
  return {
    ...state,
    activeInputView: view,
    lastInputView: view,
    captureErrors: { ...state.captureErrors, [view]: errorCode },
  };
}

export function selectInputView(state, view) {
  if (!CAPTURE_VIEWS.has(view) || state.phase === "ended") return state;
  return { ...state, activeInputView: view, lastInputView: view };
}

export function selectResultView(state, view, { manual = true } = {}) {
  if (!["front", "subject_right_profile", "back"].includes(view)) return state;
  const matchingInput = CAPTURE_VIEWS.has(view) ? view : state.lastInputView;
  return {
    ...state,
    activeResultView: view,
    activeInputView: matchingInput,
    lastInputView: matchingInput,
    resultSelectionManual: state.resultSelectionManual || manual,
  };
}

export function prepareRecapture(state, view) {
  if (
    !CAPTURE_VIEWS.has(view) ||
    !state.captures[view] ||
    state.generationSetId ||
    state.phase === "ended"
  ) {
    return state;
  }
  return {
    ...state,
    captures: { ...state.captures, [view]: false },
    captureErrors: { ...state.captureErrors, [view]: null },
    activeInputView: view,
    lastInputView: view,
  };
}

export function chooseHairstyle(state, hairstyleId) {
  if (state.phase === "ended" || !HAIRSTYLES.some(({ id }) => id === hairstyleId)) {
    return state;
  }
  return { ...state, selectedHairstyle: hairstyleId };
}

export function chooseModel(state, modelId) {
  if (
    state.phase === "ended" ||
    state.modelLocked ||
    state.generationSetId ||
    !MODEL_OPTIONS.some(({ id }) => id === modelId)
  ) {
    return state;
  }
  return { ...state, selectedModelId: modelId };
}

export function startGeneration(state, generationSetId) {
  if (!deriveUi(state).canGenerate || !generationSetId) return state;
  return {
    ...state,
    phase: "generating",
    generationSetId,
    generationStatus: "running",
    modelLocked: true,
    views: {
      front: { ...state.views.front, status: "running", attempts: 1, errorCode: null },
      subject_right_profile: {
        ...state.views.subject_right_profile,
        status: "running",
        attempts: 1,
        errorCode: null,
      },
      back: { ...state.views.back, status: "blocked", attempts: 0, errorCode: null },
    },
  };
}

export function applyGenerationSnapshot(state, snapshot) {
  if (state.phase === "ended") return state;
  const nextViews = { ...state.views };
  let ignoredStaleView = false;
  const hadSuccessfulResult = Object.values(state.views).some(
    ({ status }) => status === "succeeded",
  );
  for (const view of ["front", "subject_right_profile", "back"]) {
    const update = snapshot.views?.[view];
    if (!update) continue;
    const current = nextViews[view];
    const updateAttempts = update.attempts ?? current.attempts;
    if (updateAttempts < current.attempts) {
      ignoredStaleView = true;
      continue;
    }
    nextViews[view] = {
      ...current,
      status: update.status ?? current.status,
      attempts: updateAttempts,
      imageId: update.imageId ?? current.imageId,
      errorCode: update.errorCode ?? null,
    };
  }
  const terminal = new Set(["completed", "partial_failure", "failed", "cancelled"]);
  const nextGenerationStatus =
    ignoredStaleView && state.generationStatus === "running"
      ? state.generationStatus
      : snapshot.status ?? state.generationStatus;
  const firstSuccessfulView = !state.resultSelectionManual && !hadSuccessfulResult
    ? ["front", "subject_right_profile", "back"].find(
        (view) => nextViews[view].status === "succeeded",
      )
    : null;
  const matchingInput = firstSuccessfulView && CAPTURE_VIEWS.has(firstSuccessfulView)
    ? firstSuccessfulView
    : state.activeInputView;
  return {
    ...state,
    phase: terminal.has(nextGenerationStatus) ? "results" : "generating",
    generationSetId: snapshot.id ?? state.generationSetId,
    generationStatus: nextGenerationStatus,
    providerMode: snapshot.providerMode ?? state.providerMode,
    actualModelId: snapshot.modelId ?? state.actualModelId,
    modelLocked: state.modelLocked || snapshot.modelLocked === true || Boolean(snapshot.id),
    views: nextViews,
    activeResultView: firstSuccessfulView ?? state.activeResultView,
    activeInputView: matchingInput,
    lastInputView: firstSuccessfulView && CAPTURE_VIEWS.has(firstSuccessfulView)
      ? firstSuccessfulView
      : state.lastInputView,
  };
}

export function requestRetry(state, view) {
  const current = state.views[view];
  if (
    !current ||
    !["failed", "succeeded"].includes(current.status) ||
    current.attempts !== 1 ||
    state.phase === "ended"
  ) {
    return state;
  }
  return {
    ...state,
    phase: "generating",
    generationStatus: "running",
    views: {
      ...state.views,
      [view]: { ...current, status: "running", attempts: 2, imageId: null, errorCode: null },
    },
  };
}

export function finishSession(state, cleanupStatus = "deleted") {
  return {
    ...state,
    phase: "ended",
    cameraReady: false,
    generationStatus: "cancelled",
    cleanupStatus,
  };
}

export function sessionCleanupRequest(state) {
  if (!state.sessionId || state.phase === "ended") return null;
  return {
    path: `/api/sessions/${encodeURIComponent(state.sessionId)}`,
    options: { method: "DELETE", keepalive: true },
  };
}

export function deriveUi(state) {
  const ended = state.phase === "ended";
  const capturesReady = state.captures.front && state.captures.subject_right_profile;
  const generationStarted = Boolean(state.generationSetId);
  const views = Object.fromEntries(
    Object.entries(state.views).map(([view, value]) => [
      view,
      {
        ...value,
        canRetry:
          !ended && ["failed", "succeeded"].includes(value.status) && value.attempts === 1,
      },
    ]),
  );
  const canStartSession =
    !ended && state.consentAccepted && Boolean(state.participantId) && !state.sessionId;
  const canGenerate =
    !ended &&
    Boolean(state.sessionId) &&
    capturesReady &&
    Boolean(state.selectedHairstyle) &&
    !generationStarted;
  const primaryAction = derivePrimaryAction(state, {
    ended,
    canStartSession,
    canGenerate,
  });
  const inputView = state.activeInputView ?? "front";
  const resultView = state.activeResultView ?? "front";
  return {
    ...state,
    views,
    canStartSession,
    canChooseModel: !ended && !state.modelLocked && !generationStarted,
    canRequestCamera: !ended && Boolean(state.sessionId) && !state.cameraReady,
    canCapture: !ended && Boolean(state.sessionId) && state.cameraReady,
    canGenerate,
    canEndSession: !ended && Boolean(state.sessionId),
    primaryAction,
    inputStage: {
      view: inputView,
      mode: ended
        ? "ended"
        : state.captures[inputView]
          ? "frozen"
          : state.cameraReady
            ? "live"
            : state.sessionId
              ? "camera_required"
              : "notice",
      errorCode: state.captureErrors[inputView],
      showBackNotCaptured: resultView === "back",
    },
    resultStage: { view: resultView, ...views[resultView] },
    modelLockMessage: state.modelLocked
      ? "本次运行已锁定模型；换模型需结束并新建运行"
      : null,
    cleanupMessage:
      state.cleanupStatus === "deletion_pending"
        ? "图片读取已撤销，临时文件正在继续清理"
        : state.cleanupStatus === "deleted"
          ? "会话已结束，临时图片已清理"
          : null,
  };
}

function derivePrimaryAction(state, { ended, canStartSession, canGenerate }) {
  if (ended) return { id: "ended", label: "运行已结束", enabled: false };
  if (!state.sessionId) {
    return { id: "start_session", label: "开始运行", enabled: canStartSession };
  }
  if (!state.cameraReady) {
    return { id: "open_camera", label: "开启摄像头", enabled: true };
  }
  if (!state.captures.front) {
    return { id: "capture", view: "front", label: "冻结正面", enabled: true };
  }
  if (!state.captures.subject_right_profile) {
    return {
      id: "capture",
      view: "subject_right_profile",
      label: "冻结右侧面",
      enabled: true,
    };
  }
  if (!state.generationSetId) {
    return {
      id: "generate",
      label: state.selectedHairstyle ? "生成三视图" : "请先选择发型",
      enabled: canGenerate,
    };
  }
  const labels = {
    running: "三视图生成中",
    completed: "三视图已完成",
    partial_failure: "查看失败视图",
    failed: "生成失败",
    cancelled: "生成已取消",
  };
  return {
    id: "generation_status",
    label: labels[state.generationStatus] ?? "查看生成状态",
    enabled: false,
  };
}
