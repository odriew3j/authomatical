from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_container_and_environment_templates_exist():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "FROM python:3.11-slim" in dockerfile
    assert "pip install --no-cache-dir -r requirements.txt" in dockerfile
    for service in ("postgres:", "redis:", "migrate:", "article-worker:"):
        assert service in compose
    assert 'profiles: ["telegram"]' in compose
    assert 'profiles: ["bale"]' in compose
    assert "condition: service_completed_successfully" in compose
    for variable in ("OPENROUTER_API_KEY", "SECRET_KEY", "POSTGRES_PASSWORD"):
        assert f"{variable}=" in env_example


def test_requirements_include_production_migration_dependencies():
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "alembic" in requirements
    assert "psycopg2-binary" in requirements


def test_optional_docker_desktop_dns_override_is_available_without_hardcoding_it():
    override = (ROOT / "docker-compose.dns.example.yml").read_text(encoding="utf-8")
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")

    for service in ("telegram-worker:", "bale-worker:", "article-worker:"):
        assert service in override
    assert "DOCKER_DNS_PRIMARY" in override
    assert "DOCKER_DNS_SECONDARY" in override
    assert "docker-compose.override.yml" in ignored
