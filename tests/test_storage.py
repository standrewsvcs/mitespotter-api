"""
tests/test_storage.py
Tests:
    src/mitespotter_api/storage.py

Created: 2026-11-07
Authors: Maxence Morel Dierckx
"""
from __future__ import annotations

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from mitespotter_api.config import IMMUTABLE_CACHE_CONTROL
from mitespotter_api.storage import (
    LocalStorage,
    R2Storage,
    StorageKeyError,
    make_storage,
    validate_key,
)


BUCKET = "mitespotter-test"
R2_ENV = {
    "MITESPOTTER_STORAGE": "r2",
    "MITESPOTTER_R2_ACCOUNT_ID": "acc123",
    "MITESPOTTER_R2_BUCKET": BUCKET,
    "MITESPOTTER_R2_ACCESS_KEY_ID": "key",
    "MITESPOTTER_R2_SECRET_ACCESS_KEY": "secret",
}


@pytest.fixture
def local(tmp_path):
    return LocalStorage(tmp_path / "data", public_data_url="https://mitespotter.org/data/")


@pytest.fixture
def r2(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        yield R2Storage(client, bucket=BUCKET, public_data_url="https://mitespotter.org/data")


@pytest.fixture(params=["local", "r2"])
def storage(request):
    return request.getfixturevalue(request.param)


# MARK: Keys

@pytest.mark.parametrize("key", ["images/abc.jpg", "datasets/mitespotter_2026-08-09.zip", "a"])
def test_valid_keys(key):
    assert validate_key(key) == key


@pytest.mark.parametrize("key", ["", "/etc/passwd", "../x", "images/../../x", "images//x", "images/./x", "images/", "a\\b"])
def test_invalid_keys_are_rejected(key):
    with pytest.raises(StorageKeyError):
        validate_key(key)


# MARK: Both backends

def test_round_trip(storage):
    storage.put("images/abc.jpg", b"jpeg-bytes", "image/jpeg")
    assert storage.exists("images/abc.jpg")
    assert storage.get("images/abc.jpg") == b"jpeg-bytes"


def test_put_overwrites(storage):
    storage.put("images/abc.jpg", b"one", "image/jpeg")
    storage.put("images/abc.jpg", b"two", "image/jpeg")
    assert storage.get("images/abc.jpg") == b"two"


def test_missing_key(storage):
    assert not storage.exists("images/missing.jpg")
    with pytest.raises(FileNotFoundError):
        storage.get("images/missing.jpg")


def test_delete_is_idempotent(storage):
    storage.put("thumbnails/abc.webp", b"webp", "image/webp")
    storage.delete("thumbnails/abc.webp")
    storage.delete("thumbnails/abc.webp")
    assert not storage.exists("thumbnails/abc.webp")


def test_list_filters_by_prefix_and_sorts(storage):
    for key in ("images/b.jpg", "images/a.jpg", "thumbnails/a.webp"):
        storage.put(key, b"x", "application/octet-stream")
    assert storage.list("images/") == ["images/a.jpg", "images/b.jpg"]
    assert storage.list() == ["images/a.jpg", "images/b.jpg", "thumbnails/a.webp"]


def test_public_url(storage):
    assert storage.public_url("images/abc.jpg") == "https://mitespotter.org/data/images/abc.jpg"


def test_keys_are_validated(storage):
    with pytest.raises(StorageKeyError):
        storage.put("../escape", b"x", "text/plain")
    with pytest.raises(StorageKeyError):
        storage.public_url("/abs")


# MARK: Local

def test_local_list_of_missing_root_is_empty(tmp_path):
    assert LocalStorage(tmp_path / "nowhere").list() == []


def test_local_writes_under_root_and_leaves_no_temp_files(local):
    local.put("images/abc.jpg", b"x", "image/jpeg")
    assert (local.root / "images" / "abc.jpg").read_bytes() == b"x"
    assert [p.name for p in (local.root / "images").iterdir()] == ["abc.jpg"]


def test_local_list_ignores_hidden_files(local):
    local.put("images/abc.jpg", b"x", "image/jpeg")
    (local.root / "images" / ".abc.jpg.tmp").write_bytes(b"partial")
    assert local.list() == ["images/abc.jpg"]


# MARK: R2

def test_r2_sets_content_type_and_immutable_cache_control(r2):
    r2.put("images/abc.jpg", b"x", "image/jpeg")
    head = r2.client.head_object(Bucket=BUCKET, Key="images/abc.jpg")
    assert head["ContentType"] == "image/jpeg"
    assert head["CacheControl"] == IMMUTABLE_CACHE_CONTROL


def test_r2_cache_control_can_be_overridden(r2):
    r2.put("datasets/latest.json", b"{}", "application/json", cache_control="no-cache")
    assert r2.client.head_object(Bucket=BUCKET, Key="datasets/latest.json")["CacheControl"] == "no-cache"


def test_r2_list_paginates(r2):
    for i in range(1005):  # list_objects_v2 returns at most 1000 keys per page
        r2.client.put_object(Bucket=BUCKET, Key=f"images/{i:04d}.jpg", Body=b"")
    keys = r2.list("images/")
    assert len(keys) == 1005
    assert keys[0] == "images/0000.jpg" and keys[-1] == "images/1004.jpg"


def test_r2_exists_reraises_unexpected_errors():
    class DeniedClient:
        def head_object(self, **kwargs):
            raise ClientError({"Error": {"Code": "403", "Message": "Forbidden"}}, "HeadObject")

    with pytest.raises(ClientError):
        R2Storage(DeniedClient(), bucket=BUCKET).exists("images/abc.jpg")


# MARK: Factory

def test_make_storage_local(make_config, tmp_path):
    storage = make_storage(make_config())
    assert isinstance(storage, LocalStorage)
    assert storage.root == (tmp_path / "data").resolve()
    assert storage.public_url("images/a.jpg") == "/data/images/a.jpg"


def test_make_storage_r2(make_config):
    storage = make_storage(make_config(**R2_ENV, MITESPOTTER_PUBLIC_DATA_URL="https://data.mitespotter.org/"))
    assert isinstance(storage, R2Storage)
    assert storage.bucket == BUCKET
    assert storage.client.meta.endpoint_url == "https://acc123.r2.cloudflarestorage.com"
    assert storage.public_url("images/a.jpg") == "https://data.mitespotter.org/images/a.jpg"
