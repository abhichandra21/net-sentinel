from pathlib import Path
import re

import yaml


ROOT = Path(__file__).resolve().parent.parent


def test_compose_requires_mqtt_password():
    compose_path = ROOT / "docker-compose.yml"
    compose = yaml.safe_load(compose_path.read_text())
    environment = compose["services"]["net-sentinel"]["environment"]

    assert "version" not in compose
    assert "MQTT_PASSWORD=${MQTT_PASSWORD:?MQTT_PASSWORD must be set}" in environment


def test_operator_docs_use_environment_password_and_migration_steps():
    for name in ("README.md", "DEPLOYMENT.md"):
        text = (ROOT / name).read_text()
        assert 'password: "${MQTT_PASSWORD}"' in text
        assert "cp config/config.example.yaml config/config.yaml" in text
        assert "MQTT_PASSWORD=replace-with-your-broker-password" in text
        assert not re.search(r"\s-P\s+['\"](?!\$)", text)


def test_dotenv_is_ignored():
    ignored = (ROOT / ".gitignore").read_text().splitlines()
    assert ".env" in ignored


def test_deployment_log_commands_name_the_real_compose_service():
    deployment = (ROOT / "DEPLOYMENT.md").read_text()
    assert "docker-compose logs -f net-sentinel" in deployment
    assert "docker-compose logs -f sentinel" not in deployment
