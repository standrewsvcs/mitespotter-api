"""
src/mitespotter_api/config.py
Environment, server, database, storage and dataset configuration

Created: 2026-09-17
Authors: Maxence Morel Dierckx
"""
from __future__ import annotations


import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


# MARK: Env helpers

def _env_str(environ: Mapping[str, str], name: str, default: str | None = None) -> str:
    raw = environ.get(name, "").strip()
    if raw:
        return raw
    if default is None:
        raise ValueError(f"{name} must be set")
    return str(default).strip()


def _env_bool(environ: Mapping[str, str], name: str, default: bool) -> bool:
    raw = environ.get(name, "").strip().lower()
    if raw == "":
        return default
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    raise ValueError(f"'{name}' must be a boolean, got '{raw}'")


def _env_int(environ: Mapping[str, str], name: str, default: int) -> int:
    raw = environ.get(name, "").strip()
    if raw == "":
        return default
    try:
        return int(raw)
    except ValueError as e:
        raise ValueError(f"'{name}' must be an integer, got '{raw}'") from e


def _env_choice(environ: Mapping[str, str], name: str, choices: tuple[str, ...], default: str) -> str:
    value = _env_str(environ, name, default)
    if value not in choices:
        raise ValueError(f"{name} must be one of {choices}, got '{value}'")
    return value


# MARK: Config

ENVIRONMENTS = ("dev", "test", "prod")
STORAGE_BACKENDS = ("local", "r2")
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


@dataclass(frozen=True)
class Config:
    """Application configuration: values read from the environment, plus fixed domain values"""
    environment: str
    debug: bool
    host: str
    port: int
    secret_key: str
    database_url: str
    sql_echo: bool
    data_dir: Path
    max_upload_bytes: int
    jpeg_quality: int
    storage: str
    r2_account_id: str | None
    r2_bucket: str | None
    r2_access_key_id: str | None
    r2_secret_access_key: str | None
    public_data_url: str

    # Fixed domain values; the database CHECK constraints are built from these
    splits: tuple[str, ...] = ("train", "val", "test")
    image_event_types: tuple[str, ...] = ("upload", "complete", "verify", "reject", "delete")
    annotation_event_types: tuple[str, ...] = ("create", "update", "confirm", "delete")
    report_reasons: tuple[str, ...] = (
        "not_a_board",
        "duplicate",
        "unusable_quality",
        "personal_or_inappropriate",
        "incorrect_annotations",  # verified images only
        "other",
    )

    @property
    def is_production(self) -> bool:
        return self.environment == "prod"

    @property
    def is_test(self) -> bool:
        return self.environment == "test"

    @property
    def r2_endpoint_url(self) -> str:
        return f"https://{self.r2_account_id}.r2.cloudflarestorage.com"

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Config:
        env = os.environ if environ is None else environ

        environment = _env_choice(env, "MITESPOTTER_ENV", ENVIRONMENTS, "dev")
        is_production = environment == "prod"
        debug = _env_bool(env, "MITESPOTTER_DEBUG", not is_production)

        secret_key = env.get("MITESPOTTER_SECRET_KEY", "").strip()
        if not secret_key:
            if is_production:
                raise RuntimeError("MITESPOTTER_SECRET_KEY must be set when MITESPOTTER_ENV=prod")
            secret_key = "dev-secret-key"

        storage = _env_choice(env, "MITESPOTTER_STORAGE", STORAGE_BACKENDS, "local")
        r2 = {
            name: env.get(f"MITESPOTTER_{name.upper()}", "").strip() or None
            for name in ("r2_account_id", "r2_bucket", "r2_access_key_id", "r2_secret_access_key")
        }
        if storage == "r2":
            missing = [f"MITESPOTTER_{name.upper()}" for name, value in r2.items() if value is None]
            if missing:
                raise ValueError(f"{', '.join(missing)} must be set when MITESPOTTER_STORAGE=r2")

        data_dir = Path(_env_str(env, "MITESPOTTER_DATA_DIR", str(_REPO_ROOT / "data")))

        return cls(
            environment=environment,
            debug=debug,
            host=_env_str(env, "MITESPOTTER_HOST", "127.0.0.1"),
            port=_env_int(env, "MITESPOTTER_PORT", 6776),
            secret_key=secret_key,
            database_url=_env_str(env, "MITESPOTTER_DATABASE_URL"),  # No default, must be set
            sql_echo=_env_bool(env, "MITESPOTTER_SQL_ECHO", debug),
            data_dir=data_dir.expanduser().resolve(),
            max_upload_bytes=_env_int(env, "MITESPOTTER_MAX_UPLOAD_BYTES", 60 * 1024 * 1024),  # 60 MB
            jpeg_quality=_env_int(env, "MITESPOTTER_JPEG_QUALITY", 95),
            storage=storage,
            public_data_url=_env_str(env, "MITESPOTTER_PUBLIC_DATA_URL", "/data").rstrip("/"),
            **r2,
        )


config = Config.from_env()


# MARK: Module constants (derived from config)

ENVIRONMENT = config.environment
IS_PRODUCTION = config.is_production
IS_TEST = config.is_test
DEBUG = config.debug

HOST = config.host
PORT = config.port

SECRET_KEY = config.secret_key

DATABASE_URL = config.database_url
SQL_ECHO = config.sql_echo

MAX_UPLOAD_BYTES = config.max_upload_bytes
JPEG_QUALITY = config.jpeg_quality


# MARK: Paths

DATA_DIR = config.data_dir

BACKUPS_DIR    = DATA_DIR / "backups"
DATASETS_DIR   = DATA_DIR / "datasets"
IMAGES_DIR     = DATA_DIR / "images"
ORIGINALS_DIR  = DATA_DIR / "originals"
PYRAMIDS_DIR   = DATA_DIR / "pyramids"
THUMBNAILS_DIR = DATA_DIR / "thumbnails"

DATA_DIRS = (
    BACKUPS_DIR,
    DATASETS_DIR,
    IMAGES_DIR,
    ORIGINALS_DIR,
    PYRAMIDS_DIR,
    THUMBNAILS_DIR
)


def create_data_dirs() -> None:
    for directory in DATA_DIRS:
        directory.mkdir(parents=True, exist_ok=True)


# MARK: Dataset

SPLIT_TRAIN_BELOW = 70  # First 70% of the dataset is used for training
SPLIT_VAL_BELOW = 85    # Next 15% of the dataset is used for validation
                        # Remaining 15% of the dataset is used for testing


@dataclass
class Category:
    id: int
    name: str
    supercategory: str


CATEGORY_DEBRIS = Category(id=1, name="debris", supercategory="non-mite")
CATEGORY_VARROA = Category(id=2, name="varroa destructor", supercategory="mite")
CATEGORIES = (CATEGORY_DEBRIS, CATEGORY_VARROA)
CATEGORY_BY_ID = {category.id: category for category in CATEGORIES}

COCO_LICENSE = {
    "id": 1,
    "name": "CC BY 4.0",
    "url": "https://creativecommons.org/licenses/by/4.0/"
}

COCO_CONTRIBUTOR = "St Andrews Volunteer Code Society"
COCO_DESCRIPTION = "Mitespotter annotated dataset of bee parasitic mites on sticky boards"
COCO_INFO_YEAR = 2026

COCO_FILENAMES = {
    "train": "instances_train.json",
    "val": "instances_val.json",
    "test": "instances_test.json"
}

MANIFEST_FILENAME = "MANIFEST.json"
VERSION_DIR_PREFIX = "mitespotter_v"
SNAPSHOT_DIR_PREFIX = "mitespotter_"
SNAPSHOT_DISCLAIMER = (
    "The following is an internal-only snapshot of the mitespotter.org dataset. "
    "It should not be cited or distributed. For the official versions, see "
    "https://mitespotter.org/download"
)


# MARK: File serving

IMMUTABLE_CACHE_CONTROL = "public, max-age=31536000, immutable"


# MARK: Email

# TODO: /verify-email, /reset-password, mailing list, etc.


# MARK: Jobs

# TODO: Unused until jobs/nightly.py & jobs/weekly.py are implemented
