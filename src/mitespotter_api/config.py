"""
src/mitespotter_api/routes/config.py
Environment, server, and database configuration

Created: 2026-09-17
Authors: Maxence Morel Dierckx
"""
from __future__ import annotations


import os
from dataclasses import dataclass
from pathlib import Path


# MARK: Env helpers

def _env_str(name: str, default: str | None = None) -> str:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        raw = default
    if raw is None:
        raise ValueError(f"Environment variable '{name}' is not set and no default value was provided")
    return str(raw).strip()


def _env_bool(name: str, default: bool | None = None) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if raw is None or raw == "":
        if default is None:
            raise ValueError(f"Environment variable '{name}' is not set and no default value was provided")
        return default
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    raise ValueError(f"Environment variable '{name}' must be a boolean, got '{raw}'")


def _env_int(name: str, default: int | None = None) -> int:
    raw = os.environ.get(name, "").strip()
    if raw is None or raw == "":
        if default is None:
            raise ValueError(f"Environment variable '{name}' is not set and no default value was provided")
        return default
    try:
        return int(raw)
    except ValueError as e:
        raise ValueError(f"Environment variable '{name}' must be an integer, got '{raw}'") from e


# MARK: Runtime env

ENVIRONMENTS = ("dev", "test", "prod")
ENVIRONMENT = _env_str("MITESPOTTER_ENV", "dev")
if ENVIRONMENT not in ENVIRONMENTS:
    raise ValueError(f"MITESPOTTER_ENV must be one of {ENVIRONMENTS}, got '{ENVIRONMENT}'")

IS_PRODUCTION = ENVIRONMENT == "prod"
IS_TEST = ENVIRONMENT == "test"
DEBUG = _env_bool("MITESPOTTER_DEBUG", not IS_PRODUCTION)


# MARK: Server

HOST = _env_str("MITESPOTTER_HOST", "127.0.0.1")
PORT = _env_int("MITESPOTTER_PORT", 6776)


# MARK: Secrets

def _resolve_secret_key() -> str:
    key = _env_str("MITESPOTTER_SECRET_KEY", "")
    if key:
        return key
    if IS_PRODUCTION:
        raise RuntimeError("MITESPOTTER_SECRET_KEY must be set when MITESPOTTER_ENV=prod")
    return "dev-secret-key"


SECRET_KEY = _resolve_secret_key()


# MARK: Database

DATABASE_URL = _env_str("MITESPOTTER_DATABASE_URL", "sqlite+aiosqlite:///mitespotter.db")
SQL_ECHO = _env_bool("MITESPOTTER_SQL_ECHO", DEBUG)


# MARK: Paths

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = Path(_env_str("MITESPOTTER_DATA_DIR", _REPO_ROOT / "data")).expanduser().resolve()

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


# MARK: Ingest

MAX_UPLOAD_BYTES = _env_int("MITESPOTTER_MAX_UPLOAD_BYTES", 60 * 1024 * 1024)  # 60 MB
JPEG_QUALITY = _env_int("MITESPOTTER_JPEG_QUALITY", 95)


# MARK: Dataset

SPLITS = ("train", "val", "test")
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

COCO_CONTRIBUTOR = "St Andrews Volunteer Coding Society"
COCO_DESCRIPTION = "Mitespotter annotated dataset of bee parasitic mites on sticky boards"
COCO_INFO_YEAR = 2026

COCO_FILENAMES = {
    "train": "instances_train.json",
    "val": "instances_val.json",
    "test": "instances_test.json"
}

MANIFEST_FILENAME = "manifest.json"
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
