from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_new_fault_codes_are_documented_and_alerted():
    readme = (ROOT / "README.md").read_text()
    ha = (ROOT / "ha_comprehensive_setup.yaml").read_text()
    dashboard = (ROOT / "ha_dashboard.yaml").read_text()
    for code in (
        "MODEM_DOWN",
        "LASTMILE_RF_SUSPECT",
        "ISP_INGRESS_CONGEST",
        "ISP_CORE_ROUTING",
    ):
        assert code in readme
        assert code in ha
    assert "LASTMILE" in dashboard


def test_modem_observability_is_documented_across_ha_surfaces():
    readme = (ROOT / "README.md").read_text()
    ha = (ROOT / "ha_comprehensive_setup.yaml").read_text()
    dashboard = (ROOT / "ha_dashboard.yaml").read_text()
    detailed_dashboard = (
        ROOT / "config" / "network_monitoring_dashboard.yaml"
    ).read_text()
    alerts = (ROOT / "ha_automation_alerts.yaml").read_text()

    for text in (readme, ha, dashboard, detailed_dashboard, alerts):
        assert "MODEM_DOWN" in text
    for topic in (
        "modem_status/state",
        "modem_latency/state",
        "modem_latency/availability",
    ):
        assert topic in ha
    assert "OUTAGE_MODEM_DOWN" in alerts


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
        "ha_dashboard.yaml",
        "config/network_monitoring_dashboard.yaml",
        "ha_automation_alerts.yaml",
    ):
        assert "ISP_EQUIPMENT" not in (ROOT / name).read_text()
