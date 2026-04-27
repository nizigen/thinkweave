"""Deployment configuration contracts for production safety."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DOCKERFILE = REPO_ROOT / "backend" / "Dockerfile"
BACKEND_ENV_EXAMPLE = REPO_ROOT / "backend" / ".env.example"
PROD_COMPOSE = REPO_ROOT / "docker-compose.prod.yml"
DEPLOYMENT_DOC = REPO_ROOT / "docs" / "DEPLOYMENT.md"
BACKEND_DOCKERIGNORE = REPO_ROOT / "backend" / ".dockerignore"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def render_production_compose(*profiles: str) -> str:
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("docker CLI is required for compose contract rendering")

    with tempfile.TemporaryDirectory() as tmpdir:
        sandbox = Path(tmpdir)
        (sandbox / "backend").mkdir()
        shutil.copy(REPO_ROOT / "docker-compose.yml", sandbox / "docker-compose.yml")
        shutil.copy(PROD_COMPOSE, sandbox / "docker-compose.prod.yml")
        (sandbox / "backend" / ".env").write_text(
            "\n".join(
                [
                    "POSTGRES_URL=postgresql+asyncpg://agent_user:agent_pass@postgres:5432/agent_db",
                    "REDIS_URL=redis://redis:6379/0",
                    "OPENAI_API_KEY=test-key",
                    "DEBUG=false",
                    "DISABLE_RATE_LIMIT=false",
                    "TASK_AUTH_TOKENS=test-token:test-user",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        command = [
            docker,
            "compose",
            "-f",
            "docker-compose.yml",
            "-f",
            "docker-compose.prod.yml",
        ]
        for profile in profiles:
            command.extend(["--profile", profile])
        command.append("config")

        result = subprocess.run(
            command,
            cwd=sandbox,
            capture_output=True,
            text=True,
            check=True,
        )
    return result.stdout


def service_block(content: str, service_name: str) -> str:
    marker = f"  {service_name}:\n"
    if marker not in content:
        return ""
    start = content.index(marker)
    remainder = content[start:]
    next_service = remainder.find("\n  ", len(marker))
    if next_service == -1:
        return remainder
    return remainder[:next_service + 1]


def test_production_compose_does_not_publish_internal_service_ports():
    content = render_production_compose()

    for service_name in ("postgres", "redis", "backend"):
        assert "ports:" not in service_block(content, service_name)


def test_memory_legacy_profile_does_not_publish_internal_service_ports():
    content = render_production_compose("memory-legacy")

    for service_name in ("neo4j", "qdrant"):
        assert "ports:" not in service_block(content, service_name)


def test_production_compose_preserves_hardened_runtime_env():
    content = render_production_compose()

    assert 'DEBUG: "false"' in content
    assert 'DISABLE_RATE_LIMIT: "false"' in content
    assert "TASK_AUTH_TOKENS: test-token:test-user" in content


def test_backend_env_example_uses_safe_production_defaults():
    content = read_text(BACKEND_ENV_EXAMPLE)

    assert "TASK_AUTH_TOKENS=" in content
    assert "TASK_AUTH_TOKENS=dev-token:dev-user" not in content
    assert "DEBUG=false" in content
    assert "DEBUG=true" not in content
    assert "DISABLE_RATE_LIMIT=false" in content
    assert "CORS_ALLOW_ORIGINS=https://your-domain.example" in content


def test_backend_image_does_not_run_migrations_automatically_on_start():
    content = read_text(BACKEND_DOCKERFILE)

    assert "alembic upgrade head" not in content
    assert 'CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]' in content


def test_backend_dockerignore_excludes_sensitive_env_files():
    content = read_text(BACKEND_DOCKERIGNORE)

    assert ".env" in content
    assert ".env.*" in content


def test_deployment_guide_avoids_copying_runtime_secrets_into_build_context():
    content = read_text(DEPLOYMENT_DOC)

    assert "cp backend/.env.example backend/.env" not in content
    assert "docker compose --env-file backend/.env" in content


def test_deployment_guide_requires_compose_version_that_supports_reset_override():
    content = read_text(DEPLOYMENT_DOC)

    assert "Docker Compose >= 2.24.4" in content


def test_development_quickstart_mentions_local_tooling_and_auth_setup():
    content = read_text(DEPLOYMENT_DOC)

    assert "开发环境额外需要" in content
    assert "Python 3.12" in content
    assert "Node.js 20" in content
    assert "uv" in content
    assert "TASK_AUTH_TOKENS" in content
    assert "CORS_ALLOW_ORIGINS=http://localhost:5173" in content


def test_production_guide_runs_migrations_before_starting_public_services():
    content = read_text(DEPLOYMENT_DOC)

    migrate_step = "run --rm backend alembic upgrade head"
    up_step = "up -d --build backend frontend"

    assert migrate_step in content
    assert up_step in content
    assert content.index(migrate_step) < content.index(up_step)


def test_deployment_guide_explains_runtime_cors_fallback():
    content = read_text(DEPLOYMENT_DOC)

    assert "运行时回退默认值为 `http://localhost:5173`" in content
