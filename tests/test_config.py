import os
import pathlib
import textwrap
import pytest
import monitor
import yaml


def _write(tmp_path, body):
    p = tmp_path / "config.yaml"
    p.write_text(textwrap.dedent(body))
    return str(p)


def test_load_config_expands_env_vars(tmp_path, monkeypatch):
    monkeypatch.setenv("CONFIG_PATH", _write(tmp_path, """
        mqtt:
          broker: "192.168.1.50"
          password: "${MQTT_PASSWORD}"
    """))
    monkeypatch.setenv("MQTT_PASSWORD", "s3cret")
    cfg = monitor.load_config()
    assert cfg["mqtt"]["password"] == "s3cret"


def test_load_config_missing_env_var_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("CONFIG_PATH", _write(tmp_path, """
        mqtt:
          password: "${MQTT_PASSWORD}"
    """))
    monkeypatch.delenv("MQTT_PASSWORD", raising=False)
    with pytest.raises(ValueError, match="MQTT_PASSWORD"):
        monitor.load_config()


def test_load_config_empty_env_var_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("CONFIG_PATH", _write(tmp_path, """
        mqtt:
          password: "${MQTT_PASSWORD}"
    """))
    monkeypatch.setenv("MQTT_PASSWORD", "")
    with pytest.raises(ValueError, match="MQTT_PASSWORD"):
        monitor.load_config()


def test_example_config_exposes_load_quality_thresholds():
    config_path = pathlib.Path(__file__).resolve().parent.parent / "config" / "config.example.yaml"
    config = yaml.safe_load(config_path.read_text())
    thresholds = config["monitoring"]["thresholds"]

    assert thresholds["bufferbloat_ms"] == 50
    assert thresholds["loaded_loss_pct"] == 5
