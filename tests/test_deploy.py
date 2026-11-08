"""
tests/test_deploy.py
Tests:
    deploy/ (systemd units, dev.env.example, cloudflared config, install.sh)

Static checks that keep the deployment files in step with the code they run.

Created: 2026-11-08
Authors: Maxence Morel Dierckx
"""
from __future__ import annotations

import configparser
import os
import re
import shutil
import stat
import subprocess
import tomllib
from collections.abc import Mapping
from pathlib import Path

import pytest

from mitespotter_api.config import Config
from mitespotter_api.jobs.__main__ import JOBS


REPO = Path(__file__).resolve().parent.parent
DEPLOY = REPO / "deploy"
INSTALL = DEPLOY / "install.sh"
UNITS = ("mitespotter-api.service", "mitespotter-cleanup.service", "mitespotter-cleanup.timer")
PLACEHOLDER = re.compile(r"@([A-Z_]+)@")
SECRETS = ("MITESPOTTER_SECRET_KEY", "MITESPOTTER_RESEND_API_KEY", "MITESPOTTER_GOOGLE_CLIENT_SECRET")


def read_unit(name: str) -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None, strict=True)
    parser.optionxform = str  # systemd keys are case-sensitive
    parser.read_string((DEPLOY / name).read_text())
    return parser


def dev_env() -> dict[str, str]:
    """Every KEY=value in dev.env.example, commented-out ones included"""
    lines = (DEPLOY / "dev.env.example").read_text().splitlines()
    return dict(m.groups() for line in lines if (m := re.match(r"^#? ?([A-Z][A-Z0-9_]*)=(.*)$", line)))


class Recorder(Mapping[str, str]):
    """An environment that records every variable read from it"""

    def __init__(self, values: Mapping[str, str]):
        self.values, self.read = dict(values), set()

    def get(self, key, default=None):
        self.read.add(key)
        return self.values.get(key, default)

    def __getitem__(self, key):
        self.read.add(key)
        return self.values[key]

    def __iter__(self):
        return iter(self.values)

    def __len__(self):
        return len(self.values)


def filled_dev_env(tmp_path: Path) -> dict[str, str]:
    env = {key: value for key, value in dev_env().items() if value}
    env.update({name: "filled-in" for name in SECRETS}, MITESPOTTER_DATA_DIR=str(tmp_path / "data"))
    return env


# MARK: systemd units

@pytest.mark.parametrize("name", UNITS)
def test_units_parse(name):
    assert read_unit(name).has_section("Unit")


def test_api_service_runs_the_entry_point():
    service = read_unit("mitespotter-api.service")["Service"]
    scripts = tomllib.loads((REPO / "pyproject.toml").read_text())["project"]["scripts"]
    assert service["ExecStart"] == "@UV@ run --frozen mitespotter-api"
    assert "mitespotter-api" in scripts
    assert service["Restart"] == "on-failure"


def test_cleanup_service_runs_the_job():
    service = read_unit("mitespotter-cleanup.service")["Service"]
    *command, job = service["ExecStart"].split()
    assert command == ["@UV@", "run", "--frozen", "python", "-m", "mitespotter_api.jobs"]
    assert job in JOBS
    assert service["Type"] == "oneshot"


def test_timer_is_nightly_and_persistent():
    timer = read_unit("mitespotter-cleanup.timer")["Timer"]
    assert timer["OnCalendar"].startswith("*-*-* ")
    assert timer["Persistent"] == "true"


@pytest.mark.parametrize("name", ["mitespotter-api.service", "mitespotter-cleanup.service"])
def test_services_share_env_file_and_hardening(name):
    service = read_unit(name)["Service"]
    assert service["EnvironmentFile"] == "@ENV_FILE@"
    assert service["User"] == "@USER@"
    assert service["NoNewPrivileges"] == "yes"
    assert service["ProtectSystem"] == "strict"


def test_install_renders_every_placeholder():
    used = {match for name in UNITS for match in PLACEHOLDER.findall((DEPLOY / name).read_text())}
    rendered = set(re.findall(r"s\|@([A-Z_]+)@\|", INSTALL.read_text()))
    assert used <= rendered


@pytest.mark.skipif(not shutil.which("systemd-analyze"), reason="systemd-analyze is not installed")
def test_units_verify(tmp_path):
    values = {
        "USER": os.environ.get("USER") or "root", "GROUP": "root", "REPO_DIR": str(REPO),
        "ENV_FILE": str(tmp_path / "dev.env"), "UV": shutil.which("uv") or "/bin/true",
        "UV_CACHE_DIR": str(tmp_path / "cache"),
    }
    (tmp_path / "dev.env").write_text("")
    for name in UNITS:
        text = PLACEHOLDER.sub(lambda m: values[m.group(1)], (DEPLOY / name).read_text())
        (tmp_path / name).write_text(text)
    result = subprocess.run(
        ["systemd-analyze", "verify", *(str(tmp_path / name) for name in UNITS)],
        capture_output=True, text=True,
    )
    # Only complaints about our own units count; the host may have broken units of its own
    ours = [line for line in result.stderr.splitlines() if "mitespotter" in line]
    assert ours == []


# MARK: dev.env.example

def test_dev_env_only_names_settings_config_reads(tmp_path):
    recorder = Recorder(filled_dev_env(tmp_path))
    Config.from_env(recorder)
    names = {name for name in dev_env() if name.startswith("MITESPOTTER_")}
    assert names <= recorder.read


def test_dev_env_is_a_valid_public_config(tmp_path):
    config = Config.from_env(filled_dev_env(tmp_path))
    assert config.is_production and not config.debug
    assert config.host == "127.0.0.1"
    assert config.cookie_secure
    assert config.mailer == "resend"
    assert config.storage == "local"
    assert config.email_from == "onboarding@resend.dev"


def test_dev_env_has_no_secrets_and_no_quotes():
    env = dev_env()
    for name in SECRETS:
        assert env[name] == ""
    for value in env.values():
        assert not value.startswith(("'", '"')), "systemd and uv must read the file alike"


def test_dev_env_is_gitignored():
    assert "deploy/dev.env" in (REPO / ".gitignore").read_text().splitlines()


def test_tunnel_matches_dev_env():
    tunnel = (DEPLOY / "cloudflared.example.yml").read_text()
    env = dev_env()
    assert f"hostname: {env['MITESPOTTER_PUBLIC_URL'].removeprefix('https://')}" in tunnel
    assert f"service: http://{env['MITESPOTTER_HOST']}:{env['MITESPOTTER_PORT']}" in tunnel
    assert "path: ^/api/" in tunnel
    assert tunnel.rstrip().endswith("- service: http_status:404")


# MARK: install.sh

def test_install_is_valid_bash():
    subprocess.run(["bash", "-n", str(INSTALL)], check=True)
    assert os.access(INSTALL, os.X_OK)


@pytest.mark.skipif(not shutil.which("shellcheck"), reason="shellcheck is not installed")
def test_install_passes_shellcheck():
    subprocess.run(["shellcheck", str(INSTALL)], check=True)


def dry_run(tmp_path: Path, env_file: Path) -> subprocess.CompletedProcess[str]:
    # Stand-ins for tools a test machine may lack; a dry run only looks them up
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for tool in ("cloudflared", "psql"):
        (bin_dir / tool).write_text("#!/bin/sh\nexit 0\n")
        (bin_dir / tool).chmod(0o755)
    return subprocess.run(
        [str(INSTALL), "--dry-run", "--env-file", str(env_file)],
        capture_output=True, text=True, cwd=tmp_path,
        env={**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"},
    )


@pytest.mark.skipif(not shutil.which("uv"), reason="uv is not installed")
def test_install_dry_run(tmp_path):
    env_file = tmp_path / "dev.env"
    shutil.copy(DEPLOY / "dev.env.example", env_file)
    env_file.chmod(0o644)

    result = dry_run(tmp_path, env_file)
    assert result.returncode == 0, result.stderr
    assert "+ uv sync --frozen" in result.stdout
    assert "database upgrade --no-prompt" in result.stdout
    assert f"WorkingDirectory={REPO}" in result.stdout
    assert f"EnvironmentFile={env_file}" in result.stdout
    assert "+ sudo systemctl restart mitespotter-api.service" in result.stdout
    assert not PLACEHOLDER.search(result.stdout)
    assert stat.S_IMODE(env_file.stat().st_mode) == 0o644  # nothing was done


@pytest.mark.skipif(not shutil.which("uv"), reason="uv is not installed")
def test_install_requires_the_env_file(tmp_path):
    result = dry_run(tmp_path, tmp_path / "missing.env")
    assert result.returncode == 1
    assert "missing.env not found" in result.stderr
