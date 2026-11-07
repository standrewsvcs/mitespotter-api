"""
src/mitespotter_api/storage.py
File storage: local disk in dev and tests, Cloudflare R2 in production

Keys are slash-separated paths relative to the storage root, e.g.
"images/<sha256>.jpg". Public URLs are served outside the app
(R2 custom domain in production), see planning.md "Deployment".

Created: 2026-11-07
Authors: Maxence Morel Dierckx
"""
from __future__ import annotations


from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, Protocol


from .config import Config


if TYPE_CHECKING:
    from collections.abc import Iterator


class StorageKeyError(ValueError):
    """Raised for keys that are empty, absolute or escape the storage root"""


def validate_key(key: str) -> str:
    path = PurePosixPath(key)
    if not key or key.endswith("/") or path.is_absolute() or "\\" in key:
        raise StorageKeyError(f"Invalid storage key: {key!r}")
    if any(part in ("", ".", "..") for part in key.split("/")):
        raise StorageKeyError(f"Invalid storage key: {key!r}")
    return key


class Storage(Protocol):
    public_data_url: str

    def put(
        self,
        key: str,
        data: bytes,
        content_type: str,
        cache_control: str | None = None,
    ) -> None:
        """Store data under key; cache_control defaults to config.immutable_cache_control"""

    def get(self, key: str) -> bytes: ...

    def exists(self, key: str) -> bool: ...

    def delete(self, key: str) -> None: ...

    def list(self, prefix: str = "") -> list[str]: ...

    def public_url(self, key: str) -> str: ...


class _PublicUrlMixin:
    public_data_url: str

    def public_url(self, key: str) -> str:
        return f"{self.public_data_url}/{validate_key(key)}"


# MARK: Local

class LocalStorage(_PublicUrlMixin):
    """Stores files under a directory; content type and cache headers are not persisted"""

    def __init__(self, root: Path, public_data_url: str = "/data") -> None:
        self.root = Path(root).resolve()
        self.public_data_url = public_data_url.rstrip("/")

    def _path(self, key: str) -> Path:
        return self.root / validate_key(key)

    def put(
        self,
        key: str,
        data: bytes,
        content_type: str,
        cache_control: str | None = None,
    ) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.tmp")
        tmp.write_bytes(data)
        tmp.replace(path)  # atomic within a filesystem

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def list(self, prefix: str = "") -> list[str]:
        if not self.root.is_dir():
            return []
        keys = (
            path.relative_to(self.root).as_posix()
            for path in self.root.rglob("*")
            if path.is_file() and not path.name.startswith(".")
        )
        return sorted(key for key in keys if key.startswith(prefix))


# MARK: R2

class R2Storage(_PublicUrlMixin):
    """Stores files in an R2 bucket through its S3-compatible API"""

    def __init__(
        self,
        client: Any,
        bucket: str,
        public_data_url: str = "/data",
        default_cache_control: str = Config.immutable_cache_control,
    ) -> None:
        self.client = client
        self.bucket = bucket
        self.public_data_url = public_data_url.rstrip("/")
        self.default_cache_control = default_cache_control

    @classmethod
    def from_config(cls, config: Config) -> R2Storage:
        import boto3

        client = boto3.client(
            "s3",
            endpoint_url=config.r2_endpoint_url,
            aws_access_key_id=config.r2_access_key_id,
            aws_secret_access_key=config.r2_secret_access_key,
            region_name="auto",
        )
        return cls(
            client,
            bucket=config.r2_bucket or "",
            public_data_url=config.public_data_url,
            default_cache_control=config.immutable_cache_control,
        )

    def put(
        self,
        key: str,
        data: bytes,
        content_type: str,
        cache_control: str | None = None,
    ) -> None:
        self.client.put_object(
            Bucket=self.bucket,
            Key=validate_key(key),
            Body=data,
            ContentType=content_type,
            CacheControl=cache_control or self.default_cache_control,
        )

    def get(self, key: str) -> bytes:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=validate_key(key))
        except self.client.exceptions.NoSuchKey as e:
            raise FileNotFoundError(key) from e
        return response["Body"].read()

    def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self.client.head_object(Bucket=self.bucket, Key=validate_key(key))
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return False
            raise
        return True

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=validate_key(key))

    def _iter_keys(self, prefix: str) -> Iterator[str]:
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for item in page.get("Contents", []):
                yield item["Key"]

    def list(self, prefix: str = "") -> list[str]:
        return sorted(self._iter_keys(prefix))


# MARK: Factory

def make_storage(config: Config) -> Storage:
    if config.storage == "r2":
        return R2Storage.from_config(config)
    return LocalStorage(config.data_dir, public_data_url=config.public_data_url)
