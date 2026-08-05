import test from "node:test";
import assert from "node:assert/strict";
import * as workbench from "../src/hair_tryon/static/ui-state.mjs";

import {
  HAIRSTYLES,
  MODEL_OPTIONS,
  PARTICIPANTS,
  acceptDataNotice,
  applyGenerationSnapshot,
  attachSession,
  captureAccepted,
  chooseHairstyle,
  chooseModel,
  createUiState,
  deriveUi,
  finishSession,
  requestRetry,
  sessionCleanupRequest,
  chooseParticipant,
  startGeneration,
} from "../src/hair_tryon/static/ui-state.mjs";

test("a new run defaults to Nano Banana 2 and can switch to Pro before generation", () => {
  const initial = createUiState("nano_banana");
  assert.equal(initial.selectedModelId, "gemini-3.1-flash-image-preview");
  assert.deepEqual(
    MODEL_OPTIONS.map(({ id }) => id),
    ["gemini-3.1-flash-image-preview", "gemini-3-pro-image-preview"],
  );

  const changed = chooseModel(initial, "gemini-3-pro-image-preview");
  assert.equal(changed.selectedModelId, "gemini-3-pro-image-preview");
  assert.equal(deriveUi(changed).canChooseModel, true);
});

test("the first generation locks the model and changing it requires a new run", () => {
  let state = acceptDataNotice(createUiState("nano_banana"));
  state = chooseParticipant(state, "T01");
  state = attachSession(state, "session-1");
  state = captureAccepted(captureAccepted(state, "front"), "subject_right_profile");
  state = chooseHairstyle(state, "H01");
  state = startGeneration(state, "set-1");

  assert.equal(state.modelLocked, true);
  assert.equal(chooseModel(state, "gemini-3-pro-image-preview"), state);
  assert.equal(deriveUi(state).canChooseModel, false);
  assert.equal(
    deriveUi(state).modelLockMessage,
    "本次运行已锁定模型；换模型需结束并新建运行",
  );

  state = applyGenerationSnapshot(state, {
    id: "set-1",
    status: "partial_failure",
    modelLocked: false,
    views: {},
  });
  assert.equal(state.modelLocked, true);
});

test("generation status exposes the real provider and actual model, not the test input source", () => {
  const state = applyGenerationSnapshot(createUiState("checking"), {
    id: "set-1",
    status: "running",
    providerMode: "nano_banana",
    modelId: "gemini-3-pro-image-preview",
    modelLocked: true,
    source: "synthetic_imagegen",
    views: {},
  });

  const ui = deriveUi(state);
  assert.equal(ui.providerMode, "nano_banana");
  assert.equal(ui.actualModelId, "gemini-3-pro-image-preview");
  assert.equal("sourceProvider" in ui, false);
});

test("session start requires a registered participant and explicit data consent", () => {
  const initial = deriveUi(createUiState("fake"));
  assert.equal(initial.canStartSession, false);

  const accepted = acceptDataNotice(createUiState("fake"));
  assert.equal(deriveUi(accepted).canStartSession, false);

  const ready = chooseParticipant(accepted, "T01");
  assert.equal(deriveUi(ready).canStartSession, true);
  assert.deepEqual(PARTICIPANTS, ["T01", "T02", "T03", "T04", "T05"]);
});

test("camera access unlocks only after the consented session is created", () => {
  let state = acceptDataNotice(createUiState("fake"));
  state = chooseParticipant(state, "T01");
  assert.equal(deriveUi(state).canRequestCamera, false);

  state = attachSession(state, "session-1");
  assert.equal(deriveUi(state).canRequestCamera, true);
});

test("generation unlocks only after both captures and one fixed hairstyle are present", () => {
  let state = acceptDataNotice(createUiState("gemini"));
  state = chooseParticipant(state, "T01");
  state = attachSession(state, "session-1");
  state = captureAccepted(state, "front");
  state = chooseHairstyle(state, "H03");
  assert.equal(deriveUi(state).canGenerate, false);

  state = captureAccepted(state, "subject_right_profile");
  assert.equal(deriveUi(state).canGenerate, true);
  assert.deepEqual(
    HAIRSTYLES.map(({ id }) => id),
    ["H01", "H02", "H03", "H04", "H05"],
  );
});

test("a partial front result is visible while the side is still running and back stays inferred", () => {
  let state = acceptDataNotice(createUiState("gemini"));
  state = chooseParticipant(state, "T01");
  state = attachSession(state, "session-1");
  state = captureAccepted(captureAccepted(state, "front"), "subject_right_profile");
  state = chooseHairstyle(state, "H02");
  state = startGeneration(state, "set-1");
  state = applyGenerationSnapshot(state, {
    id: "set-1",
    status: "running",
    views: {
      front: { status: "succeeded", attempts: 1, imageId: "front-image" },
      subject_right_profile: { status: "running", attempts: 1 },
      back: { status: "blocked", attempts: 0 },
    },
  });

  const ui = deriveUi(state);
  assert.equal(ui.views.front.imageId, "front-image");
  assert.equal(ui.views.subject_right_profile.status, "running");
  assert.equal(ui.views.back.isAiInferred, true);
  assert.equal(ui.views.back.status, "blocked");
});

test("a view exposes exactly one retry and locks it after attempt two is submitted", () => {
  let state = createUiState("gemini");
  state = applyGenerationSnapshot(state, {
    id: "set-1",
    status: "partial_failure",
    views: {
      front: { status: "failed", attempts: 1, errorCode: "PROVIDER_TIMEOUT" },
    },
  });
  assert.equal(deriveUi(state).views.front.canRetry, true);

  state = requestRetry(state, "front");
  assert.equal(deriveUi(state).views.front.attempts, 2);
  assert.equal(deriveUi(state).views.front.canRetry, false);
  assert.equal(requestRetry(state, "front"), state);
});

test("a successful first result can be regenerated once when it has no observation value", () => {
  let state = applyGenerationSnapshot(createUiState("nano_banana"), {
    id: "set-1",
    status: "completed",
    views: {
      front: { status: "succeeded", attempts: 1, imageId: "front-image" },
    },
  });

  assert.equal(deriveUi(state).views.front.canRetry, true);
  state = requestRetry(state, "front");
  assert.equal(state.views.front.status, "running");
  assert.equal(state.views.front.attempts, 2);
  assert.equal(state.views.front.imageId, null);
});

test("closing a live page builds a keepalive request that ends the backend session", () => {
  let state = acceptDataNotice(createUiState("fake"));
  state = chooseParticipant(state, "T01");
  state = attachSession(state, "session/with spaces");

  assert.deepEqual(sessionCleanupRequest(state), {
    path: "/api/sessions/session%2Fwith%20spaces",
    options: { method: "DELETE", keepalive: true },
  });
  assert.equal(sessionCleanupRequest(finishSession(state)), null);
  assert.equal(sessionCleanupRequest(createUiState("fake")), null);
});

test("ending a session disables every action and surfaces deletion pending", () => {
  let state = acceptDataNotice(createUiState("fake"));
  state = chooseParticipant(state, "T01");
  state = attachSession(state, "session-1");
  state = finishSession(state, "deletion_pending");

  const ui = deriveUi(state);
  assert.equal(ui.canRequestCamera, false);
  assert.equal(ui.canCapture, false);
  assert.equal(ui.canGenerate, false);
  assert.equal(ui.canEndSession, false);
  assert.equal(ui.cleanupMessage, "图片读取已撤销，临时文件正在继续清理");
});

test("one primary action advances the fixed run, camera, capture, and generation sequence", () => {
  let state = createUiState("nano_banana");
  assert.deepEqual(deriveUi(state).primaryAction, {
    id: "start_session",
    label: "开始运行",
    enabled: false,
  });

  state = chooseParticipant(acceptDataNotice(state), "T01");
  assert.equal(deriveUi(state).primaryAction.enabled, true);
  state = attachSession(state, "session-1");
  assert.equal(deriveUi(state).primaryAction.id, "open_camera");

  state = workbench.markCameraReady(state);
  assert.deepEqual(deriveUi(state).primaryAction, {
    id: "capture",
    view: "front",
    label: "冻结正面",
    enabled: true,
  });

  state = captureAccepted(state, "front");
  assert.equal(deriveUi(state).primaryAction.view, "subject_right_profile");
  assert.equal(deriveUi(state).primaryAction.label, "冻结右侧面");
  state = captureAccepted(state, "subject_right_profile");
  assert.equal(deriveUi(state).primaryAction.id, "generate");
  assert.equal(deriveUi(state).primaryAction.enabled, false);

  state = chooseHairstyle(state, "H04");
  assert.deepEqual(deriveUi(state).primaryAction, {
    id: "generate",
    label: "生成三视图",
    enabled: true,
  });
});

test("result tabs synchronize matching inputs while back preserves the last real input", () => {
  let state = createUiState("nano_banana");
  state = workbench.selectInputView(state, "subject_right_profile");
  state = workbench.selectResultView(state, "front");
  assert.equal(state.activeInputView, "front");

  state = workbench.selectResultView(state, "back");
  const backUi = deriveUi(state);
  assert.equal(backUi.inputStage.view, "front");
  assert.equal(backUi.inputStage.showBackNotCaptured, true);
  assert.equal(backUi.resultStage.view, "back");
  assert.equal(backUi.resultStage.isAiInferred, true);
});

test("the first successful result auto-focuses only before a user manually chooses a result tab", () => {
  let state = applyGenerationSnapshot(createUiState("nano_banana"), {
    id: "set-1",
    status: "running",
    views: {
      subject_right_profile: {
        status: "succeeded",
        attempts: 1,
        imageId: "side-image",
      },
    },
  });
  assert.equal(state.activeResultView, "subject_right_profile");
  assert.equal(state.activeInputView, "subject_right_profile");

  state = workbench.selectResultView(state, "back");
  state = applyGenerationSnapshot(state, {
    id: "set-1",
    status: "running",
    views: {
      front: { status: "succeeded", attempts: 1, imageId: "front-image" },
    },
  });
  assert.equal(state.activeResultView, "back");
  assert.equal(state.resultSelectionManual, true);
});

test("capture errors stay with their input tab and a successful recapture clears that tab", () => {
  let state = workbench.markCaptureError(
    createUiState("nano_banana"),
    "subject_right_profile",
    "wrong_direction",
  );
  assert.equal(state.captureErrors.subject_right_profile, "wrong_direction");
  assert.equal(state.captureErrors.front, null);

  state = captureAccepted(state, "subject_right_profile");
  assert.equal(state.captureErrors.subject_right_profile, null);
});

test("preparing a frozen input for recapture returns the primary action to that angle", () => {
  let state = chooseParticipant(acceptDataNotice(createUiState("nano_banana")), "T01");
  state = attachSession(state, "session-1");
  state = workbench.markCameraReady(state);
  state = captureAccepted(captureAccepted(state, "front"), "subject_right_profile");
  state = chooseHairstyle(state, "H02");

  state = workbench.prepareRecapture(state, "front");
  assert.equal(state.captures.front, false);
  assert.equal(state.activeInputView, "front");
  assert.deepEqual(deriveUi(state).primaryAction, {
    id: "capture",
    view: "front",
    label: "冻结正面",
    enabled: true,
  });
});

test("browser camera exceptions are normalized without exposing numeric DOMException codes", () => {
  assert.equal(
    workbench.normalizeCameraErrorCode({ name: "NotFoundError", code: 8 }),
    "camera_unavailable",
  );
  assert.equal(
    workbench.normalizeCameraErrorCode({ name: "NotAllowedError", code: 0 }),
    "camera_permission_denied",
  );
  assert.equal(
    workbench.normalizeCameraErrorCode({ code: "camera_not_ready" }),
    "camera_not_ready",
  );
});

test("late generation snapshots cannot reopen an ended session", () => {
  let state = chooseParticipant(acceptDataNotice(createUiState("nano_banana")), "T01");
  state = attachSession(state, "session-1");
  state = finishSession(state);

  const afterLateSnapshot = applyGenerationSnapshot(state, {
    id: "set-late",
    status: "running",
    views: {
      front: { status: "succeeded", attempts: 1, imageId: "late-image" },
    },
  });

  assert.equal(afterLateSnapshot, state);
  assert.equal(deriveUi(afterLateSnapshot).canEndSession, false);
});

test("an older retry snapshot cannot roll attempts or status backward", () => {
  let state = createUiState("nano_banana");
  state = applyGenerationSnapshot(state, {
    id: "set-1",
    status: "partial_failure",
    views: {
      front: { status: "failed", attempts: 1, errorCode: "timeout" },
    },
  });
  state = requestRetry(state, "front");

  state = applyGenerationSnapshot(state, {
    id: "set-1",
    status: "partial_failure",
    views: {
      front: { status: "failed", attempts: 1, errorCode: "timeout" },
    },
  });

  assert.equal(state.views.front.status, "running");
  assert.equal(state.views.front.attempts, 2);
  assert.equal(state.generationStatus, "running");
  assert.equal(state.phase, "generating");
  assert.equal(deriveUi(state).views.front.canRetry, false);
});

test("a created session attaches only after the selected model is confirmed", () => {
  const ready = chooseParticipant(acceptDataNotice(createUiState("nano_banana")), "T01");
  const mismatched = workbench.attachConfirmedSession(ready, {
    sessionId: "session-1",
    providerMode: "nano_banana",
    modelId: "gemini-3-pro-image-preview",
  });
  assert.equal(mismatched, ready);

  const attached = workbench.attachConfirmedSession(ready, {
    sessionId: "session-1",
    providerMode: "nano_banana",
    modelId: ready.selectedModelId,
  });
  assert.equal(attached.sessionId, "session-1");
  assert.equal(attached.phase, "capturing");
});
