"""
tests/test_config.py
Tests:
    src/mitespotter_api/config.py

Created: 2026-09-17
Authors: Maxence Morel Dierckx
"""
from __future__ import annotations

import pytest
import importlib.util
import itertools
import sys
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "src" / "mitespotter_api" / "config.py"


# Every environment variable config reads
CONFIG_ENV_VARS = (
    "MITESPOTTER_ENV",
    "MITESPOTTER_DEBUG",
    "MITESPOTTER_HOST",
    "MITESPOTTER_PORT",
    "MITESPOTTER_SECRET_KEY",
    "MITESPOTTER_DATABASE_URL",
    "MITESPOTTER_SQL_ECHO",
    "MITESPOTTER_DATA_DIR",
    "MITESPOTTER_MAX_UPLOAD_BYTES",
    "MITESPOTTER_JPEG_QUALITY",
    "MITESPOTTER_STORAGE",
    "MITESPOTTER_R2_ACCOUNT_ID",
    "MITESPOTTER_R2_BUCKET",
    "MITESPOTTER_R2_ACCESS_KEY_ID",
    "MITESPOTTER_R2_SECRET_ACCESS_KEY",
    "MITESPOTTER_PUBLIC_DATA_URL",
)


@pytest.fixture
def load_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, required_env: dict[str, str]):
    """Load a fresh config module under a controlled environment.

    Init loads all REQUIRED_ENV vars plus an isolated DATA_DIR, then
    applies the caller's overrides. Can unset a var by passing None,
    e.g. MITESPOTTER_DATABASE_URL=None
    """
    counter = itertools.count()

    def _load(**env: str | None) -> ModuleType:
        for name in CONFIG_ENV_VARS:
            monkeypatch.delenv(name, raising=False)

        baseline = {**required_env, "MITESPOTTER_DATA_DIR": str(tmp_path / "data")}
        for name, value in {**baseline, **env}.items():
            if value is not None:
                monkeypatch.setenv(name, value)

        module_name = f"{next(counter)}"
        spec = importlib.util.spec_from_file_location(module_name, CONFIG_PATH)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        # dataclasses resolves cls.__module__ so we set it in sys.modules
        # monkeypatch removes the module from sys.modules after the test, so it won't leak
        monkeypatch.setitem(sys.modules, module_name, module)
        spec.loader.exec_module(module)
        return module

    return _load


# MARK: Environments


def test_dev_defaults(load_config):
    config = load_config()

    assert config.ENVIRONMENT == "dev"
    assert config.IS_PRODUCTION is False
    assert config.IS_TEST is False
    assert config.DEBUG is True
    assert config.SQL_ECHO is True          # defaults to DEBUG
    assert config.HOST == "127.0.0.1"
    assert config.PORT == 6776


def test_test_environment_defaults(load_config):
    config = load_config(MITESPOTTER_ENV="test")

    assert config.IS_TEST is True
    assert config.IS_PRODUCTION is False
    assert config.DEBUG is True             # anything that is not prod is debuggable
    assert config.SQL_ECHO is True


def test_prod_environment_defaults(load_config):
    config = load_config(MITESPOTTER_ENV="prod", MITESPOTTER_SECRET_KEY="s3cret")

    assert config.IS_PRODUCTION is True
    assert config.IS_TEST is False
    assert config.DEBUG is False
    assert config.SQL_ECHO is False


@pytest.mark.parametrize("value", ["staging", "development", "PROD", "production"])
def test_unknown_environment_is_rejected(load_config, value):
    with pytest.raises(ValueError, match="MITESPOTTER_ENV must be one of"):
        load_config(MITESPOTTER_ENV=value)


# MARK: Value parsing

def test_values_are_stripped(load_config):
    assert load_config(MITESPOTTER_HOST="  0.0.0.0  ").HOST == "0.0.0.0"


@pytest.mark.parametrize("raw", ["1", "true", "TRUE", "yes", "on"])
def test_truthy_boolean_spellings(load_config, raw):
    assert load_config(MITESPOTTER_SQL_ECHO=raw).SQL_ECHO is True


@pytest.mark.parametrize("raw", ["0", "false", "FALSE", "no", "off"])
def test_falsy_boolean_spellings(load_config, raw):
    assert load_config(MITESPOTTER_SQL_ECHO=raw).SQL_ECHO is False


def test_malformed_boolean_is_rejected(load_config):
    with pytest.raises(ValueError, match="must be a boolean"):
        load_config(MITESPOTTER_SQL_ECHO="maybe")


def test_malformed_integer_is_rejected(load_config):
    with pytest.raises(ValueError, match="must be an integer"):
        load_config(MITESPOTTER_PORT="80x")


def test_port_can_be_overridden(load_config):
    assert load_config(MITESPOTTER_PORT="9000").PORT == 9000


def test_empty_string_is_not_treated_as_absent(load_config):
    assert load_config(MITESPOTTER_HOST="").HOST == "127.0.0.1"


# MARK: Secrets

def test_secret_key_falls_back_in_dev(load_config):
    assert load_config().SECRET_KEY == "dev-secret-key"


def test_secret_key_is_read_from_the_environment(load_config):
    assert load_config(MITESPOTTER_SECRET_KEY="s3cret").SECRET_KEY == "s3cret"


def test_prod_without_secret_key_is_rejected(load_config):
    with pytest.raises(RuntimeError, match="MITESPOTTER_SECRET_KEY"):
        load_config(MITESPOTTER_ENV="prod")


def test_prod_with_secret_key(load_config):
    assert load_config(MITESPOTTER_ENV="prod", MITESPOTTER_SECRET_KEY="s3cret").SECRET_KEY == "s3cret"


# MARK: Database

def test_database_url_is_required(load_config):
    with pytest.raises(ValueError, match="MITESPOTTER_DATABASE_URL must be set"):
        load_config(MITESPOTTER_DATABASE_URL=None)


def test_database_url_can_be_overridden(load_config):
    overridden = load_config(MITESPOTTER_DATABASE_URL="postgresql+psycopg://u:p@localhost/db")
    assert overridden.DATABASE_URL == "postgresql+psycopg://u:p@localhost/db"


def test_database_url_falls_back_to_test_baseline(load_config, required_env):
    assert load_config().DATABASE_URL == required_env["MITESPOTTER_DATABASE_URL"]


# MARK: Paths

def test_data_dir_follows_the_environment(load_config, tmp_path):
    config = load_config(MITESPOTTER_DATA_DIR=str(tmp_path / "elsewhere"))
    assert config.DATA_DIR == (tmp_path / "elsewhere").resolve()


def test_data_dirs_are_children_of_data_dir(load_config):
    config = load_config()
    assert [d.name for d in config.DATA_DIRS] == [
        "backups",
        "datasets",
        "images",
        "originals",
        "pyramids",
        "thumbnails",
    ]
    assert all(d.parent == config.DATA_DIR for d in config.DATA_DIRS)


def test_create_data_dirs_creates_the_whole_tree(load_config):
    config = load_config()
    assert not config.DATA_DIR.exists()

    config.create_data_dirs()

    assert all(d.is_dir() for d in config.DATA_DIRS)


# MARK: Ingest

def test_ingest_defaults(load_config):
    config = load_config()
    assert config.MAX_UPLOAD_BYTES == 60 * 1024 * 1024
    assert config.JPEG_QUALITY == 95


def test_ingest_overrides(load_config):
    config = load_config(MITESPOTTER_MAX_UPLOAD_BYTES="1024", MITESPOTTER_JPEG_QUALITY="80")
    assert config.MAX_UPLOAD_BYTES == 1024
    assert config.JPEG_QUALITY == 80


# MARK: Dataset

def test_categories_match_the_database_seed(load_config):
    config = load_config()

    assert config.CATEGORY_DEBRIS.id == 1
    assert (config.CATEGORY_DEBRIS.name, config.CATEGORY_DEBRIS.supercategory) == ("debris", "non-mite")
    assert config.CATEGORY_VARROA.id == 2
    assert (config.CATEGORY_VARROA.name, config.CATEGORY_VARROA.supercategory) == ("varroa destructor", "mite")
    assert config.CATEGORY_BY_ID[2] is config.CATEGORY_VARROA
    assert {c.id for c in config.CATEGORIES} == {1, 2}


def test_splits_match_the_split_check_constraint(load_config):
    config = load_config()
    assert config.SPLITS == ("train", "val", "test")


def test_split_thresholds_are_ordered_percentages(load_config):
    config = load_config()
    assert 0 < config.SPLIT_TRAIN_BELOW < config.SPLIT_VAL_BELOW < 100


def test_coco_filenames_cover_every_split(load_config):
    config = load_config()
    assert set(config.COCO_FILENAMES) == set(config.SPLITS)
    assert all(name.endswith(".json") for name in config.COCO_FILENAMES.values())


def test_coco_license_is_cc_by_4(load_config):
    config = load_config()
    assert config.COCO_LICENSE["id"] == 1
    assert config.COCO_LICENSE["name"] == "CC BY 4.0"
    assert config.COCO_LICENSE["url"].startswith("https://creativecommons.org/licenses/by/4.0/")


def test_immutable_cache_control(load_config):
    config = load_config()
    assert config.IMMUTABLE_CACHE_CONTROL == "public, max-age=31536000, immutable"



# MARK: Storage

R2_ENV = {
    "MITESPOTTER_STORAGE": "r2",
    "MITESPOTTER_R2_ACCOUNT_ID": "acc123",
    "MITESPOTTER_R2_BUCKET": "mitespotter",
    "MITESPOTTER_R2_ACCESS_KEY_ID": "key",
    "MITESPOTTER_R2_SECRET_ACCESS_KEY": "secret",
}


def test_storage_defaults_to_local(load_config):
    config = load_config()
    assert config.settings.storage == "local"
    assert config.settings.public_data_url == "/data"
    assert config.settings.r2_bucket is None


def test_unknown_storage_is_rejected(load_config):
    with pytest.raises(ValueError, match="MITESPOTTER_STORAGE must be one of"):
        load_config(MITESPOTTER_STORAGE="s3")


def test_r2_storage_reads_its_settings(load_config):
    settings = load_config(**R2_ENV).settings
    assert settings.storage == "r2"
    assert settings.r2_bucket == "mitespotter"
    assert settings.r2_endpoint_url == "https://acc123.r2.cloudflarestorage.com"


@pytest.mark.parametrize("missing", [name for name in R2_ENV if name != "MITESPOTTER_STORAGE"])
def test_r2_storage_requires_every_r2_setting(load_config, missing):
    with pytest.raises(ValueError, match=f"{missing}.*must be set when MITESPOTTER_STORAGE=r2"):
        load_config(**{**R2_ENV, missing: None})


def test_public_data_url_trailing_slash_is_stripped(load_config):
    assert load_config(MITESPOTTER_PUBLIC_DATA_URL="https://data.mitespotter.org/").settings.public_data_url == (
        "https://data.mitespotter.org"
    )


# MARK: Settings

def test_settings_from_an_explicit_mapping_ignores_os_environ(load_config, tmp_path):
    config = load_config(MITESPOTTER_PORT="9000")
    settings = config.Settings.from_env({
        "MITESPOTTER_DATABASE_URL": "postgresql+psycopg://x/y",
        "MITESPOTTER_ENV": "prod",
        "MITESPOTTER_SECRET_KEY": "s3cret",
        "MITESPOTTER_DATA_DIR": str(tmp_path),
    })
    assert settings.port == 6776
    assert settings.is_production and not settings.is_test
    assert settings.data_dir == tmp_path.resolve()


def test_settings_are_frozen(load_config):
    import dataclasses
    settings = load_config().settings
    with pytest.raises(dataclasses.FrozenInstanceError):
        settings.port = 1


def test_module_constants_mirror_settings(load_config):
    config = load_config(MITESPOTTER_ENV="test", MITESPOTTER_PORT="9001")
    s = config.settings
    assert (config.ENVIRONMENT, config.PORT, config.DATABASE_URL, config.DATA_DIR) == (
        s.environment, s.port, s.database_url, s.data_dir
    )
    assert config.IS_TEST is s.is_test is True
