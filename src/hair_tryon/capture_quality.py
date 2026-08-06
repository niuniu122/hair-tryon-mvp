from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError


class CaptureKind(str, Enum):
    FRONT = "front"
    SUBJECT_RIGHT_PROFILE = "subject_right_profile"


class CaptureFailureCode(str, Enum):
    IMAGE_DECODE_FAILED = "image_decode_failed"
    UNSUPPORTED_FORMAT = "unsupported_format"
    IMAGE_TOO_SMALL = "image_too_small"
    NO_FACE = "no_face"
    MULTIPLE_FACES = "multiple_faces"
    FACE_TOO_SMALL = "face_too_small"
    BLURRY = "blurry"
    WRONG_DIRECTION = "wrong_direction"


class CaptureValidationError(ValueError):
    def __init__(self, code: CaptureFailureCode) -> None:
        self.code = code
        super().__init__(code.value)


@dataclass(frozen=True)
class FaceObservation:
    area_ratio: float
    orientation: CaptureKind


class FaceDetector(Protocol):
    def detect(self, image: np.ndarray) -> list[FaceObservation]: ...


@dataclass(frozen=True)
class CaptureMetadata:
    width: int
    height: int
    mime_type: str
    sha256: str


class CaptureValidator:
    def __init__(
        self,
        *,
        detector: FaceDetector | None = None,
        min_width: int = 512,
        min_height: int = 512,
        min_face_area_ratio: float = 0.08,
        min_sharpness: float = 20.0,
    ) -> None:
        self._detector = detector or OpenCvHaarFaceDetector()
        self._min_width = min_width
        self._min_height = min_height
        self._min_face_area_ratio = min_face_area_ratio
        self._min_sharpness = min_sharpness

    def validate(
        self,
        data: bytes,
        mime_type: str,
        expected_kind: CaptureKind,
    ) -> CaptureMetadata:
        if mime_type not in {"image/jpeg", "image/png"}:
            raise CaptureValidationError(CaptureFailureCode.UNSUPPORTED_FORMAT)

        try:
            with Image.open(io.BytesIO(data)) as source:
                image = ImageOps.exif_transpose(source).convert("RGB")
                image.load()
        except (UnidentifiedImageError, OSError, ValueError):
            raise CaptureValidationError(CaptureFailureCode.IMAGE_DECODE_FAILED) from None

        width, height = image.size
        if width < self._min_width or height < self._min_height:
            raise CaptureValidationError(CaptureFailureCode.IMAGE_TOO_SMALL)

        pixels = np.asarray(image)
        gray = cv2.cvtColor(pixels, cv2.COLOR_RGB2GRAY)
        sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        if sharpness < self._min_sharpness:
            raise CaptureValidationError(CaptureFailureCode.BLURRY)

        faces = self._detector.detect(pixels)
        if not faces:
            raise CaptureValidationError(CaptureFailureCode.NO_FACE)
        if len(faces) > 1:
            raise CaptureValidationError(CaptureFailureCode.MULTIPLE_FACES)

        face = faces[0]
        if face.area_ratio < self._min_face_area_ratio:
            raise CaptureValidationError(CaptureFailureCode.FACE_TOO_SMALL)
        if face.orientation is not expected_kind:
            raise CaptureValidationError(CaptureFailureCode.WRONG_DIRECTION)

        return CaptureMetadata(
            width=width,
            height=height,
            mime_type=mime_type,
            sha256=hashlib.sha256(data).hexdigest(),
        )


class OpenCvHaarFaceDetector:
    """Basic capture gate only; it is not an identity or hairstyle classifier."""

    def __init__(self) -> None:
        cascade_root = Path(cv2.data.haarcascades)
        self._front = self._load_cascade(
            cascade_root / "haarcascade_frontalface_default.xml"
        )
        self._profile = self._load_cascade(
            cascade_root / "haarcascade_profileface.xml"
        )

    @staticmethod
    def _load_cascade(path: Path) -> cv2.CascadeClassifier:
        error_message = f"Failed to load OpenCV Haar cascade: {path.name}"
        try:
            xml = path.read_text(encoding="utf-8")
            storage = cv2.FileStorage(
                xml,
                cv2.FILE_STORAGE_READ | cv2.FILE_STORAGE_MEMORY,
            )
        except (OSError, UnicodeError, cv2.error, SystemError) as error:
            raise RuntimeError(error_message) from error

        try:
            classifier = cv2.CascadeClassifier()
            if (
                not storage.isOpened()
                or not classifier.read(storage.getFirstTopLevelNode())
                or classifier.empty()
            ):
                raise RuntimeError(error_message)
            return classifier
        except cv2.error as error:
            raise RuntimeError(error_message) from error
        finally:
            storage.release()

    def detect(self, image: np.ndarray) -> list[FaceObservation]:
        gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        height, width = gray.shape
        image_area = float(width * height)

        front_rects = self._front.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(60, 60),
        )
        if len(front_rects):
            return [
                FaceObservation(
                    area_ratio=float(face_width * face_height) / image_area,
                    orientation=CaptureKind.FRONT,
                )
                for _, _, face_width, face_height in front_rects
            ]

        profile_rects = self._profile.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=4,
            minSize=(60, 60),
        )
        if len(profile_rects):
            return [
                FaceObservation(
                    area_ratio=float(face_width * face_height) / image_area,
                    orientation=CaptureKind.SUBJECT_RIGHT_PROFILE,
                )
                for _, _, face_width, face_height in profile_rects
            ]

        mirrored_rects = self._profile.detectMultiScale(
            cv2.flip(gray, 1),
            scaleFactor=1.1,
            minNeighbors=4,
            minSize=(60, 60),
        )
        return [
            FaceObservation(
                area_ratio=float(face_width * face_height) / image_area,
                orientation=CaptureKind.FRONT,
            )
            for _, _, face_width, face_height in mirrored_rects
        ]


def sanitize_image(data: bytes, mime_type: str) -> bytes:
    """Re-encode an accepted image without EXIF or ancillary metadata."""

    if mime_type not in {"image/jpeg", "image/png"}:
        raise CaptureValidationError(CaptureFailureCode.UNSUPPORTED_FORMAT)
    try:
        with Image.open(io.BytesIO(data)) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            output = io.BytesIO()
            if mime_type == "image/jpeg":
                image.save(output, format="JPEG", quality=95)
            else:
                image.save(output, format="PNG")
            return output.getvalue()
    except (UnidentifiedImageError, OSError, ValueError):
        raise CaptureValidationError(CaptureFailureCode.IMAGE_DECODE_FAILED) from None
