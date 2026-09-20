from __future__ import annotations

import hashlib
import os
import re
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Protocol


@dataclass(frozen=True)
class BlobInfo:
    key: str
    byte_size: int
    sha256: str


class BlobStore(Protocol):
    def put(self, key: str, source: BinaryIO, *, max_bytes: int | None = None) -> BlobInfo: ...
    def open(self, key: str) -> BinaryIO: ...
    def delete(self, key: str) -> None: ...
    def path_for(self, key: str) -> Path: ...


class BlobTooLargeError(ValueError):
    pass


class LocalBlobStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def generated_key(namespace: str) -> str:
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,31}", namespace):
            raise ValueError("Invalid blob namespace")
        token = uuid.uuid4().hex
        return f"{namespace}/{token[:2]}/{token[2:]}"

    def path_for(self, key: str) -> Path:
        pure = PurePosixPath(key)
        if (
            pure.is_absolute()
            or not pure.parts
            or any(part in {"", ".", ".."} for part in pure.parts)
        ):
            raise ValueError("Invalid blob key")
        candidate = self.root.joinpath(*pure.parts).resolve()
        if not candidate.is_relative_to(self.root):
            raise ValueError("Blob key escapes configured root")
        return candidate

    def put(self, key: str, source: BinaryIO, *, max_bytes: int | None = None) -> BlobInfo:
        destination = self.path_for(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        size = 0
        descriptor, temporary_name = tempfile.mkstemp(prefix=".upload-", dir=destination.parent)
        try:
            with os.fdopen(descriptor, "wb") as target:
                while chunk := source.read(1024 * 1024):
                    size += len(chunk)
                    if max_bytes is not None and size > max_bytes:
                        raise BlobTooLargeError(f"Upload exceeds {max_bytes} bytes")
                    digest.update(chunk)
                    target.write(chunk)
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary_name, destination)
        except BaseException:
            Path(temporary_name).unlink(missing_ok=True)
            raise
        return BlobInfo(key=key, byte_size=size, sha256=digest.hexdigest())

    def open(self, key: str) -> BinaryIO:
        return self.path_for(key).open("rb")

    def delete(self, key: str) -> None:
        self.path_for(key).unlink(missing_ok=True)


def safe_filename(value: str) -> str:
    name = Path(value.replace("\\", "/")).name.strip().replace("\x00", "")
    name = re.sub(r"[^\w.()\[\] -]+", "_", name, flags=re.UNICODE)
    name = re.sub(r"\s+", " ", name).strip(" .")
    if not name or name in {".", ".."}:
        name = "upload"
    stem, suffix = os.path.splitext(name)
    return f"{stem[:160]}{suffix[:24]}"[:184]
