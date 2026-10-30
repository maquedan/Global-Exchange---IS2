import os
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_ENV = {
    "POSTGRES_DB": "exchange",
    "POSTGRES_USER": "exchange",
    "POSTGRES_PASSWORD": "test-db-password",
    "DATABASE_URL": "postgres://exchange:test-db-password@db:5432/exchange",
    "KEYCLOAK_DB_NAME": "keycloak",
    "KEYCLOAK_DB_USER": "keycloak",
    "KEYCLOAK_DB_PASSWORD": "test-keycloak-password",
    "KC_ADMIN_USER": "admin",
    "KC_ADMIN_PASSWORD": "test-admin-password",
    "SECRET_KEY": "test-django-secret",
    "DJANGO_ALLOWED_HOSTS": "exchange.example.org",
    "APP_PUBLIC_URL": "https://exchange.example.org",
    "SITE_BASE_URL": "https://exchange.example.org",
    "KEYCLOAK_PUBLIC_URL": "https://auth.example.org",
    "KEYCLOAK_SERVER_URL": "https://auth.example.org",
    "KEYCLOAK_INTERNAL_URL": "http://keycloak:8080",
    "INITIAL_USD_PYG_BUY_RATE": "7000.00",
    "INITIAL_USD_PYG_SELL_RATE": "7100.00",
    "INITIAL_COMMISSION_MINORISTA": "2.50",
    "INITIAL_COMMISSION_CORPORATIVO": "2.00",
    "INITIAL_COMMISSION_VIP": "1.50",
}


@pytest.fixture
def deployment_workspace(tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    script = scripts / "deploy.sh"
    shutil.copy(ROOT / "scripts" / "deploy.sh", script)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    docker_log = tmp_path / "docker.log"
    curl_log = tmp_path / "curl.log"
    docker = fake_bin / "docker"
    docker.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$DEPLOY_DOCKER_LOG"\n')
    docker.chmod(0o755)
    curl = fake_bin / "curl"
    curl.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$DEPLOY_CURL_LOG"\nexit 0\n')
    curl.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    env["DEPLOY_DOCKER_LOG"] = str(docker_log)
    env["DEPLOY_CURL_LOG"] = str(curl_log)
    return tmp_path, script, env, docker_log, curl_log


def test_deploy_dev_runs_migrations_demo_seed_and_web(deployment_workspace):
    workspace, script, env, docker_log, _ = deployment_workspace
    shutil.copy(ROOT / ".env.example", workspace / ".env.example")

    result = subprocess.run(
        [str(script), "dev"],
        cwd=workspace,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    commands = docker_log.read_text()
    assert "up -d --wait db keycloak-db" in commands
    assert "python manage.py migrate --noinput && python manage.py collectstatic --noinput" in commands
    assert "cargar_datos_iniciales --profile demo" in commands
    assert "up -d --wait web" in commands


def test_deploy_prod_runs_preflight_minimal_seed_and_services(deployment_workspace):
    workspace, script, env, docker_log, _ = deployment_workspace
    (workspace / ".env.prod").write_text(
        "\n".join(f"{key}={value}" for key, value in PRODUCTION_ENV.items()) + "\n"
    )

    result = subprocess.run(
        [str(script), "prod"],
        cwd=workspace,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    commands = docker_log.read_text()
    assert "-f docker-compose.prod.yml config --quiet" in commands
    assert "python manage.py migrate --noinput && python manage.py collectstatic --noinput" in commands
    assert "cargar_datos_iniciales --profile minimal" in commands
    assert "up -d --wait web nginx" in commands


def test_deploy_prod_rejects_missing_financial_values_before_docker(deployment_workspace):
    workspace, script, env, docker_log, _ = deployment_workspace
    incomplete = {key: value for key, value in PRODUCTION_ENV.items() if not key.startswith("INITIAL_")}
    (workspace / ".env.prod").write_text(
        "\n".join(f"{key}={value}" for key, value in incomplete.items()) + "\n"
    )

    result = subprocess.run(
        [str(script), "prod"],
        cwd=workspace,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "INITIAL_USD_PYG_BUY_RATE" in result.stderr
    assert not docker_log.exists()
