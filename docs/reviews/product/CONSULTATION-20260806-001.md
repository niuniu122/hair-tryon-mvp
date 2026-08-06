---
doc_id: CONSULTATION-20260806-001
title: Windows 中文路径下 OpenCV 人脸分类器加载失败咨询
category: product-consultation
status: completed
version: 1
created_at: 2026-08-06T08:54:13+08:00
updated_at: 2026-08-06T08:54:13+08:00
last_verified_at: 2026-08-06T08:54:13+08:00
source_of_truth: false
related_tasks: [TASK-20260806-001]
related_documents: [PRD-HAIR-IMAGE-001, ROUTING-20260806-001]
supersedes: null
actor_agent: camera_path_bug_pm
expert_role: product-manager
operation_type: query
---

# 咨询范围与输入

- 用户报告：第三方测试确认项目整体可运行，但项目位于含中文的路径时，OpenCV 人脸分类器为空并阻断摄像头采集；用户要求修复。
- Product Manager 选择原因：这是影响用户可见采集流程的 P0 兼容性缺陷，需要轻量 PRD、明确非目标和可验证验收标准。
- AI Engineer 选择原因：问题涉及 OpenCV Windows 文件路径、Haar XML 加载和真实检测行为，需要验证根因与最小技术方案。
- 输入文档与证据：`docs/product.md`、`docs/progress.md`、`src/hair_tryon/capture_quality.py`、`tests/test_capture_quality.py`、OpenCV 4.12.0 本机复现和真实级联 XML。
- 预期输出：不扩大产品范围的最小修复、测试矩阵、开发路由和重新批准边界。

# 关键问答记录

| 时间 | 问题/证据 | 用户回答 | 提问原因 | 结论 |
|---|---|---|---|---|
| 2026-08-06T08:54:13+08:00 | 第三方报告指出中文路径使两个分类器 `empty=True`，是否需要处理 | 用户明确要求修复 | 该变化影响拍摄流程，需确认业务优先级 | 定为受影响 Windows 安装的 P0 阻断问题 |

# 已验证当前状态

1. 当前 `OpenCvHaarFaceDetector` 把 `cv2.data.haarcascades` 与 XML 文件名拼接后直接传给 `cv2.CascadeClassifier(filename)`，没有初始化空分类器检查。
2. 相同的两个 XML 位于纯英文路径时均能加载；复制到 `AI美业` 路径后均为 `empty=True`。
3. 中文路径下调用 `detectMultiScale` 会稳定触发 OpenCV `!empty()` 断言；该错误会在采集质量校验阶段阻断拍摄。
4. 现有测试只实例化真实校验器，其他行为测试使用注入的固定检测器，因此没有执行真实级联分类器，也没有覆盖中文路径。
5. 使用 Python 读取 XML 文本，再通过 OpenCV `FileStorage` 内存模式和 `CascadeClassifier.read(FileNode)` 加载，两个分类器均为非空；释放 `FileStorage` 后检测仍可执行。
6. 内存加载分类器与当前英文路径分类器在现有正面和侧面合成测试素材上的检测结果一致。

# 产品结论

- 目标：项目位于英文或中文 Windows 路径时，正面和侧面人脸分类器都能加载并执行，用户可继续拍摄。
- 非目标：不调整清晰度、方向或单脸阈值；不更换检测模型；不复制 XML 到临时目录；不改变 API、页面、模型 provider、依赖、数据或安全边界。
- 不可接受结果：绕过人脸校验、静默使用空分类器、把原始 OpenCV `!empty()` 延迟到拍摄时暴露，或要求用户长期迁移到英文路径。
- 影响量化：受影响路径中的两个人脸分类器均失败，导致该路径下 100% 的真实采集质量校验无法完成。

# 专家建议与冲突处理

- 推荐：由 Python 以 Unicode 安全方式读取捆绑 XML，使用 OpenCV 内存 `FileStorage` 加载到空 `CascadeClassifier`，并在初始化阶段校验存储打开、读取结果和 `empty()`。
- 缺失或损坏的分类器应在初始化阶段抛出稳定、可理解的应用级错误，并标明逻辑资源名称；不得等到检测时产生原始 OpenCV 断言。
- 备选的 ASCII 临时文件、外置英文虚拟环境和项目迁移均会增加清理、权限或部署约束，只保留为诊断性临时绕行，不作为产品修复。
- Product Manager 与 AI Engineer 无意见冲突；均确认核心源码范围仅两个文件，不新增依赖。

# 参考

- OpenCV FileStorage 4.12.0：https://docs.opencv.org/4.12.0/da/d56/classcv_1_1FileStorage.html
- OpenCV CascadeClassifier 4.12.0：https://docs.opencv.org/4.12.0/d1/de5/classcv_1_1CascadeClassifier.html
