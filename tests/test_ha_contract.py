from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent

# The dashboard and its theme are owned by this repo. Home Assistant does not
# read the dashboard YAML (it is a storage-mode dashboard); it is deployed with
# homeassistant/deploy_dashboard.py. Owning it here is what lets these tests
# check that a new fault code actually reaches an operator-facing surface.
DASHBOARD = ROOT / "homeassistant" / "dashboards" / "net_sentinel.yaml"
THEME = ROOT / "homeassistant" / "themes" / "net-sentinel.yaml"
DEPLOY = ROOT / "homeassistant" / "deploy_dashboard.py"


def test_new_fault_codes_are_documented_and_alerted():
    readme = (ROOT / "README.md").read_text()
    ha = (ROOT / "ha_comprehensive_setup.yaml").read_text()
    dashboard = DASHBOARD.read_text()
    for code in (
        "MODEM_DOWN",
        "LASTMILE_FIBER_SUSPECT",
        "ISP_INGRESS_CONGEST",
        "ISP_CORE_ROUTING",
    ):
        assert code in readme
        assert code in ha
        # The dashboard maps each code to a remedy line. A code missing here
        # renders as generic "watch and wait" advice during a real outage.
        assert code in dashboard, f"{code} has no remedy in the dashboard"


def test_modem_observability_is_documented_across_ha_surfaces():
    readme = (ROOT / "README.md").read_text()
    ha = (ROOT / "ha_comprehensive_setup.yaml").read_text()
    alerts = (ROOT / "ha_automation_alerts.yaml").read_text()
    dashboard = DASHBOARD.read_text()

    for text in (readme, ha, alerts, dashboard):
        assert "MODEM_DOWN" in text
    for topic in (
        "modem_status/state",
        "modem_latency/state",
        "modem_latency/availability",
    ):
        assert topic in ha
    assert "OUTAGE_MODEM_DOWN" in alerts


def test_setup_points_modem_target_at_the_bgw620():
    for name in (
        "config/config.example.yaml",
        "README.md",
        "DEPLOYMENT.md",
    ):
        text = (ROOT / name).read_text()
        assert "BGW620" in text
        assert "192.168.10.254" in text
        assert "192.168.1.254" not in text
        assert "192.168.100.1" not in text


def test_manual_gateway_last_change_sensor_is_a_timestamp():
    ha = (ROOT / "ha_comprehensive_setup.yaml").read_text()

    assert "modem_last_change/state" in ha
    assert "device_class: timestamp" in ha
    assert "modem_last_change_seconds" not in ha
    assert "gateway_last_change_seconds" not in DASHBOARD.read_text()


def test_load_quality_topics_exist_in_manual_ha_config():
    ha = (ROOT / "ha_comprehensive_setup.yaml").read_text()
    for topic in (
        "bufferbloat_ms/state",
        "loaded_loss_pct/state",
        "load_quality_status/state",
        "load_fault_detail/state",
    ):
        assert topic in ha


def test_deployment_manual_topics_match_notifier_state_topics():
    deployment = (ROOT / "DEPLOYMENT.md").read_text()
    for key in (
        "status",
        "blame",
        "fault_detail",
        "router_latency",
        "dns_latency",
        "http_latency",
        "jitter",
        "download_speed",
    ):
        assert f"home/network/sentinel/{key}/state" in deployment


def test_readme_references_existing_ha_setup_file():
    readme = (ROOT / "README.md").read_text()
    for name in ("ha_comprehensive_setup.yaml", "ha_complete_setup.yaml"):
        assert name in readme
        assert (ROOT / name).exists()


def test_retired_isp_equipment_code_is_not_operator_facing():
    for name in (
        "README.md",
        "ha_comprehensive_setup.yaml",
        "ha_automation_alerts.yaml",
        "homeassistant/dashboards/net_sentinel.yaml",
    ):
        assert "ISP_EQUIPMENT" not in (ROOT / name).read_text()


def test_dashboard_package_is_complete():
    """The dashboard is only deployable as a set: the YAML, the theme it reads
    its colours from, and the script that pushes both."""
    assert DASHBOARD.exists()
    assert THEME.exists()
    assert DEPLOY.exists()


def test_only_one_dashboard_copy_exists():
    """Two stale copies used to sit in this repo, neither of them authoritative,
    and both drifted from the live dashboard for months. One source only."""
    for name in ("ha_dashboard.yaml", "config/network_monitoring_dashboard.yaml"):
        assert not (ROOT / name).exists(), (
            f"{name} is back. homeassistant/dashboards/net_sentinel.yaml is the "
            "only dashboard source; deploy it with homeassistant/deploy_dashboard.py."
        )


def test_dashboard_uses_discovery_entities_not_manual_duplicates():
    """Every metric exists twice in Home Assistant: once from the sentinel's own
    MQTT discovery, once from hand-written mqtt.yaml sensors reading the same
    topics. The discovery set is the single source of truth per notifier.py, and
    it is the only set carrying the gateway, load-quality and last-outage
    sensors. Mixing the two is what made the old dashboard incoherent."""
    dashboard = DASHBOARD.read_text()
    for legacy in (
        "sensor.internet_router_latency",
        "sensor.internet_dns_latency",
        "sensor.internet_http_latency",
        "sensor.internet_status",
        "sensor.internet_fault_blame",
        "sensor.modem_latency",
        "sensor.isp_gateway_latency",
        "sensor.router_jitter_internal",
    ):
        assert legacy not in dashboard, (
            f"{legacy} is a hand-written mqtt.yaml duplicate. Use the "
            "sensor.network_sentinel_netsentinel_* discovery entity instead."
        )
    assert "sensor.network_sentinel_netsentinel_" in dashboard


def test_dashboard_theme_defines_every_variable_the_dashboard_uses():
    """The dashboard styles itself entirely through --ns-* theme variables. A
    variable used but not defined fails silently: the colour just does not
    apply, which is exactly the bug class this dashboard is meant to avoid."""
    import re

    dashboard = DASHBOARD.read_text()
    theme = THEME.read_text()
    used = set(re.findall(r"var\(--(ns-[a-z-]+)\)", dashboard))
    defined = set(re.findall(r"^\s{2}(ns-[a-z-]+):", theme, re.MULTILINE))
    missing = used - defined
    assert not missing, f"dashboard uses undefined theme variables: {sorted(missing)}"


def test_dashboard_carries_no_cable_era_wording():
    """This uplink is AT&T fiber on a BGW620. Cable, CMTS and RF wording is
    stale by definition and misleads whoever reads the dashboard at 2am."""
    dashboard = DASHBOARD.read_text().lower()
    for stale in ("cmts", "coax", "lastmile_rf", "cable modem"):
        assert stale not in dashboard, f"stale cable-era wording in dashboard: {stale}"
