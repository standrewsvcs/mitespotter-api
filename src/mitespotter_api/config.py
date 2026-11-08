"""
src/mitespotter_api/config.py
Environment, server, database, storage and dataset configuration

Everything read-only lives on the frozen Config: values read from the
environment, fixed domain values, and paths derived from both. Use the
module-level `config` instance, or build one with Config.from_env(mapping).

Created: 2026-09-17
Authors: Maxence Morel Dierckx
"""
from __future__ import annotations


import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from types import MappingProxyType
from typing import ClassVar


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


# MARK: Value types

@dataclass(frozen=True)
class Category:
    id: int
    name: str
    supercategory: str


@dataclass(frozen=True)
class License:
    id: int
    name: str
    url: str


# MARK: Config

@dataclass(frozen=True)
class Config:
    """Application configuration: values read from the environment, plus fixed domain values"""

    ENVIRONMENTS: ClassVar[tuple[str, ...]] = ("dev", "test", "prod")
    STORAGE_BACKENDS: ClassVar[tuple[str, ...]] = ("local", "r2")
    MAILERS: ClassVar[tuple[str, ...]] = ("outbox", "resend")

    # Read from the environment
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
    public_url: str
    mailer: str
    resend_api_key: str | None
    email_from: str
    google_client_id: str | None
    google_client_secret: str | None

    # API
    api_prefix: str = "/api"
    api_title: str = "Mitespotter API"
    api_version: str = "0.1.0"

    # Database
    session_dependency_key: str = "db_session"
    migrations_dir: Path = Path(__file__).resolve().parent / "migrations"
    alembic_version_table: str = "alembic_version"

    # Domain values; the database CHECK constraints are built from these
    splits: tuple[str, ...] = ("train", "val", "test")
    image_event_types: tuple[str, ...] = ("upload", "complete", "verify", "reject", "delete")
    annotation_event_types: tuple[str, ...] = ("create", "update", "confirm", "delete")
    email_code_purposes: tuple[str, ...] = ("register", "recover")
    report_reasons: tuple[str, ...] = (
        "not_a_board",
        "duplicate",
        "unusable_quality",
        "personal_or_inappropriate",
        "incorrect_annotations",  # verified images only
        "other",
    )
    categories: tuple[Category, ...] = (
        Category(id=1, name="debris", supercategory="non-mite"),
        Category(id=2, name="varroa destructor", supercategory="mite"),
    )

    # Dataset split: buckets [0, train) train, [train, val) val, the rest test
    split_train_below: int = 70
    split_val_below: int = 85

    # Dataset export
    coco_license: License = License(id=1, name="CC BY 4.0", url="https://creativecommons.org/licenses/by/4.0/")
    coco_contributor: str = "St Andrews Volunteer Code Society"
    coco_description: str = "Mitespotter annotated dataset of bee parasitic mites on sticky boards"
    coco_info_year: int = 2026
    coco_filenames: Mapping[str, str] = MappingProxyType({
        "train": "instances_train.json",
        "val": "instances_val.json",
        "test": "instances_test.json",
    })
    manifest_filename: str = "MANIFEST.json"
    version_dir_prefix: str = "mitespotter_v"
    snapshot_dir_prefix: str = "mitespotter_"
    snapshot_disclaimer: str = (
        "The following is an internal-only snapshot of the mitespotter.org dataset. "
        "It should not be cited or distributed. For the official versions, see "
        "https://mitespotter.org/download"
    )

    # File serving
    immutable_cache_control: str = "public, max-age=31536000, immutable"

    # Sessions
    session_cookie_name: str = "mitespotter_session"
    session_lifetime: timedelta = timedelta(days=30)
    csrf_cookie_name: str = "mitespotter_csrf"
    csrf_header_name: str = "x-csrftoken"
    auth_rate_limit: tuple[str, int] = ("minute", 30)  # per client IP, every /api/auth request

    # Passwords (argon2-cffi defaults for hashing parameters)
    password_min_length: int = 8
    password_max_length: int = 1024

    # Emailed codes
    code_digits: int = 6
    code_lifetime: timedelta = timedelta(minutes=15)
    code_attempts: int = 5
    code_resend_interval: timedelta = timedelta(minutes=1)
    resend_api_url: str = "https://api.resend.com/emails"

    # Google (OpenID Connect)
    google_issuer: str = "https://accounts.google.com"
    google_authorization_endpoint: str = "https://accounts.google.com/o/oauth2/v2/auth"
    google_token_endpoint: str = "https://oauth2.googleapis.com/token"
    google_jwks_uri: str = "https://www.googleapis.com/oauth2/v3/certs"
    google_scopes: str = "openid email profile"
    google_flow_cookie_name: str = "mitespotter_google"
    google_flow_lifetime: timedelta = timedelta(minutes=10)

    # Usernames: "<adjective> <noun>", plus a number if taken
    username_adjectives: tuple[str, ...] = (
        "amber", "bold", "bright", "brisk", "buzzy", "calm", "clever", "curious",
        "dapper", "deft", "eager", "fleet", "fuzzy", "gentle", "golden", "hardy",
        "honeyed", "humble", "jolly", "keen", "kind", "lively", "lucky", "merry",
        "mellow", "nimble", "patient", "plucky", "quick", "quiet", "rapid", "sharp",
        "sleek", "spry", "steady", "sunny", "swift", "tidy", "trusty", "vivid",
        "wary", "warm", "wild", "wise", "zesty", "zippy", "dusky", "sturdy",
    )
    username_nouns: tuple[str, ...] = (
        "finder", "longstepper", "forager", "spotter", "drone", "keeper", "scout", "worker",
        "nectar", "pollinator", "comber", "hiver", "swarmer", "waggler", "dancer", "buzzer",
        "clover", "heather", "bramble", "thistle", "lavender", "meadow", "orchard", "foxglove",
        "beekeeper", "smoker", "frame", "brood", "honeycomb", "propolis", "waxmaker", "seeker",
        "tracker", "watcher", "counter", "sorter", "glider", "hoverer", "rambler", "wanderer",
        "lookout", "pathfinder", "gatherer", "builder", "tender", "guard", "nurse", "sentry",
    )

    # MARK: Derived

    @property
    def is_production(self) -> bool:
        return self.environment == "prod"

    @property
    def is_test(self) -> bool:
        return self.environment == "test"

    @property
    def r2_endpoint_url(self) -> str:
        return f"https://{self.r2_account_id}.r2.cloudflarestorage.com"

    @property
    def cookie_secure(self) -> bool:
        return self.public_url.startswith("https://")

    @property
    def google_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    @property
    def google_redirect_uri(self) -> str:
        return f"{self.public_url}{self.api_prefix}/auth/google/callback"

    @property
    def alembic_ini(self) -> Path:
        return self.migrations_dir / "alembic.ini"

    @property
    def category_by_id(self) -> Mapping[int, Category]:
        return MappingProxyType({category.id: category for category in self.categories})

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"

    @property
    def datasets_dir(self) -> Path:
        return self.data_dir / "datasets"

    @property
    def images_dir(self) -> Path:
        return self.data_dir / "images"

    @property
    def originals_dir(self) -> Path:
        return self.data_dir / "originals"

    @property
    def pyramids_dir(self) -> Path:
        return self.data_dir / "pyramids"

    @property
    def thumbnails_dir(self) -> Path:
        return self.data_dir / "thumbnails"

    @property
    def data_dirs(self) -> tuple[Path, ...]:
        return (
            self.backups_dir,
            self.datasets_dir,
            self.images_dir,
            self.originals_dir,
            self.pyramids_dir,
            self.thumbnails_dir,
        )

    def create_data_dirs(self) -> None:
        for directory in self.data_dirs:
            directory.mkdir(parents=True, exist_ok=True)

    # MARK: Loading

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Config:
        env = os.environ if environ is None else environ

        environment = _env_choice(env, "MITESPOTTER_ENV", cls.ENVIRONMENTS, "dev")
        is_production = environment == "prod"
        debug = _env_bool(env, "MITESPOTTER_DEBUG", not is_production)

        secret_key = env.get("MITESPOTTER_SECRET_KEY", "").strip()
        if not secret_key:
            if is_production:
                raise RuntimeError("MITESPOTTER_SECRET_KEY must be set when MITESPOTTER_ENV=prod")
            secret_key = "dev-secret-key"

        storage = _env_choice(env, "MITESPOTTER_STORAGE", cls.STORAGE_BACKENDS, "local")
        r2 = {
            name: env.get(f"MITESPOTTER_{name.upper()}", "").strip() or None
            for name in ("r2_account_id", "r2_bucket", "r2_access_key_id", "r2_secret_access_key")
        }
        if storage == "r2":
            missing = [f"MITESPOTTER_{name.upper()}" for name, value in r2.items() if value is None]
            if missing:
                raise ValueError(f"{', '.join(missing)} must be set when MITESPOTTER_STORAGE=r2")

        mailer = _env_choice(env, "MITESPOTTER_MAILER", cls.MAILERS, "resend" if is_production else "outbox")
        resend_api_key = env.get("MITESPOTTER_RESEND_API_KEY", "").strip() or None
        if is_production and mailer != "resend":
            raise ValueError("MITESPOTTER_MAILER must be 'resend' when MITESPOTTER_ENV=prod")
        if mailer == "resend" and resend_api_key is None:
            raise ValueError("MITESPOTTER_RESEND_API_KEY must be set when MITESPOTTER_MAILER=resend")

        repo_root = Path(__file__).resolve().parent.parent.parent
        data_dir = Path(_env_str(env, "MITESPOTTER_DATA_DIR", str(repo_root / "data")))

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
            public_url=_env_str(env, "MITESPOTTER_PUBLIC_URL", "http://127.0.0.1:6776").rstrip("/"),
            mailer=mailer,
            resend_api_key=resend_api_key,
            email_from=_env_str(env, "MITESPOTTER_EMAIL_FROM", "Mitespotter <noreply@mitespotter.org>"),
            google_client_id=env.get("MITESPOTTER_GOOGLE_CLIENT_ID", "").strip() or None,
            google_client_secret=env.get("MITESPOTTER_GOOGLE_CLIENT_SECRET", "").strip() or None,
            **r2,
        )


config = Config.from_env()


# TODO (jobs): unused until jobs/nightly.py & jobs/weekly.py are implemented
