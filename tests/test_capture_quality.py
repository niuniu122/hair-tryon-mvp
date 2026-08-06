import io
import shutil
from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image, ImageDraw

from hair_tryon.capture_quality import (
    CaptureFailureCode,
    CaptureKind,
    CaptureValidationError,
    CaptureValidator,
    FaceObservation,
    OpenCvHaarFaceDetector,
    sanitize_image,
)


def image_bytes(*, width: int = 640, height: int = 640, detailed: bool = True) -> bytes:
    image = Image.new("RGB", (width, height), "white")
    if detailed:
        draw = ImageDraw.Draw(image)
        for x in range(0, width, 16):
            for y in range(0, height, 16):
                if (x // 16 + y // 16) % 2:
                    draw.rectangle((x, y, x + 15, y + 15), fill="black")
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=95)
    return output.getvalue()


class FixedDetector:
    def __init__(self, observations: list[FaceObservation]) -> None:
        self._observations = observations

    def detect(self, image: object) -> list[FaceObservation]:
        return self._observations


def validator(observations: list[FaceObservation]) -> CaptureValidator:
    return CaptureValidator(
        detector=FixedDetector(observations),
        min_width=512,
        min_height=512,
        min_face_area_ratio=0.08,
        min_sharpness=20,
    )


def test_default_capture_validator_can_construct_the_runtime_face_detector() -> None:
    """Catches dependency versions that drop the required Haar binding."""

    check = CaptureValidator()

    assert check is not None


def test_runtime_face_detector_loads_cascades_from_a_unicode_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_root = Path(cv2.data.haarcascades)
    unicode_root = tmp_path / "AI美业"
    unicode_root.mkdir()
    for filename in (
        "haarcascade_frontalface_default.xml",
        "haarcascade_profileface.xml",
    ):
        shutil.copyfile(original_root / filename, unicode_root / filename)
    monkeypatch.setattr(cv2.data, "haarcascades", f"{unicode_root}/")

    detector = OpenCvHaarFaceDetector()

    assert detector.detect(np.zeros((640, 640, 3), dtype=np.uint8)) == []


def test_runtime_face_detector_fails_during_initialization_when_cascade_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cv2.data, "haarcascades", f"{tmp_path}/")

    with pytest.raises(RuntimeError, match="haarcascade_frontalface_default.xml"):
        OpenCvHaarFaceDetector()


def test_runtime_face_detector_fails_during_initialization_when_cascade_is_corrupt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "haarcascade_frontalface_default.xml").write_text(
        "<not-a-cascade />",
        encoding="utf-8",
    )
    monkeypatch.setattr(cv2.data, "haarcascades", f"{tmp_path}/")

    with pytest.raises(RuntimeError, match="haarcascade_frontalface_default.xml"):
        OpenCvHaarFaceDetector()


def test_runtime_face_detector_reports_a_missing_profile_cascade(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_root = Path(cv2.data.haarcascades)
    shutil.copyfile(
        original_root / "haarcascade_frontalface_default.xml",
        tmp_path / "haarcascade_frontalface_default.xml",
    )
    monkeypatch.setattr(cv2.data, "haarcascades", f"{tmp_path}/")

    with pytest.raises(RuntimeError, match="haarcascade_profileface.xml"):
        OpenCvHaarFaceDetector()


@pytest.mark.parametrize(
    ("storage_open", "read_result", "classifier_empty"),
    [
        (False, True, False),
        (True, False, False),
        (True, True, True),
    ],
)
def test_cascade_integrity_failures_release_storage_and_raise_a_stable_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    storage_open: bool,
    read_result: bool,
    classifier_empty: bool,
) -> None:
    cascade_path = tmp_path / "test-cascade.xml"
    cascade_path.write_text("<opencv_storage />", encoding="utf-8")

    class StubStorage:
        release_calls = 0

        def isOpened(self) -> bool:
            return storage_open

        def getFirstTopLevelNode(self) -> object:
            return object()

        def release(self) -> None:
            self.release_calls += 1

    class StubClassifier:
        def read(self, _node: object) -> bool:
            return read_result

        def empty(self) -> bool:
            return classifier_empty

    storage = StubStorage()
    monkeypatch.setattr(cv2, "FileStorage", lambda *_args: storage)
    monkeypatch.setattr(cv2, "CascadeClassifier", StubClassifier)

    with pytest.raises(RuntimeError, match="test-cascade.xml"):
        OpenCvHaarFaceDetector._load_cascade(cascade_path)

    assert storage.release_calls == 1


def test_cascade_cv2_errors_are_wrapped_and_release_storage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cascade_path = tmp_path / "test-cascade.xml"
    cascade_path.write_text("<opencv_storage />", encoding="utf-8")

    class StubStorage:
        release_calls = 0

        def release(self) -> None:
            self.release_calls += 1

    storage = StubStorage()
    monkeypatch.setattr(cv2, "FileStorage", lambda *_args: storage)

    def raise_cv2_error() -> None:
        raise cv2.error("classifier construction failed")

    monkeypatch.setattr(cv2, "CascadeClassifier", raise_cv2_error)

    with pytest.raises(RuntimeError, match="test-cascade.xml"):
        OpenCvHaarFaceDetector._load_cascade(cascade_path)

    assert storage.release_calls == 1


def test_undecodable_upload_is_rejected_before_face_checks() -> None:
    check = validator(
        [FaceObservation(area_ratio=0.2, orientation=CaptureKind.FRONT)]
    )

    with pytest.raises(CaptureValidationError) as error:
        check.validate(b"not-an-image", "image/jpeg", CaptureKind.FRONT)

    assert error.value.code is CaptureFailureCode.IMAGE_DECODE_FAILED


def test_multiple_faces_are_rejected_instead_of_picking_one() -> None:
    check = validator(
        [
            FaceObservation(area_ratio=0.2, orientation=CaptureKind.FRONT),
            FaceObservation(area_ratio=0.1, orientation=CaptureKind.FRONT),
        ]
    )

    with pytest.raises(CaptureValidationError) as error:
        check.validate(image_bytes(), "image/jpeg", CaptureKind.FRONT)

    assert error.value.code is CaptureFailureCode.MULTIPLE_FACES


def test_fixed_side_capture_rejects_the_wrong_direction() -> None:
    check = validator(
        [FaceObservation(area_ratio=0.2, orientation=CaptureKind.FRONT)]
    )

    with pytest.raises(CaptureValidationError) as error:
        check.validate(
            image_bytes(),
            "image/jpeg",
            CaptureKind.SUBJECT_RIGHT_PROFILE,
        )

    assert error.value.code is CaptureFailureCode.WRONG_DIRECTION


def test_uniform_blurry_capture_is_rejected() -> None:
    check = validator(
        [FaceObservation(area_ratio=0.2, orientation=CaptureKind.FRONT)]
    )

    with pytest.raises(CaptureValidationError) as error:
        check.validate(
            image_bytes(detailed=False),
            "image/jpeg",
            CaptureKind.FRONT,
        )

    assert error.value.code is CaptureFailureCode.BLURRY


def test_valid_capture_returns_only_technical_metadata_and_hash() -> None:
    check = validator(
        [FaceObservation(area_ratio=0.2, orientation=CaptureKind.FRONT)]
    )
    source = image_bytes()

    metadata = check.validate(source, "image/jpeg", CaptureKind.FRONT)

    assert metadata.width == 640
    assert metadata.height == 640
    assert metadata.mime_type == "image/jpeg"
    assert metadata.sha256 == "94fa53532488f252e7a5d65496ee6d464d6dd68a61f26a0a1797ded04bce3253"


def test_sanitized_jpeg_removes_exif_before_storage_or_provider_upload() -> None:
    image = Image.new("RGB", (640, 640), "white")
    exif = Image.Exif()
    exif[270] = "private camera note"
    source = io.BytesIO()
    image.save(source, format="JPEG", exif=exif)

    sanitized = sanitize_image(source.getvalue(), "image/jpeg")

    with Image.open(io.BytesIO(sanitized)) as cleaned:
        assert cleaned.size == (640, 640)
        assert dict(cleaned.getexif()) == {}
