from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_new_fault_codes_are_documented_and_alerted():
    readme = (ROOT / "README.md").read_text()
    ha = (ROOT / "ha_comprehensive_setup.yaml").read_text()
    dashboard = (ROOT / "ha_dashboard.yaml").read_text()
    for code in (
        "LASTMILE_RF_SUSPECT",
        "ISP_INGRESS_CONGEST",
        "ISP_CORE_ROUTING",
    ):
        assert code in readme
        assert code in ha
    assert "LASTMILE" in dashboard


def test_load_quality_topics_exist_in_manual_ha_config():
    ha = (ROOT / "ha_comprehensive_setup.yaml").read_text()
    for topic in (
        "bufferbloat_ms/state",
        "loaded_loss_pct/state",
        "load_quality_status/state",
        "load_fault_detail/state",
    ):
        assert topic in ha


def test_retired_isp_equipment_code_is_not_operator_facing():
    for name in (
        "README.md",
        "ha_comprehensive_setup.yaml",
        "ha_dashboard.yaml",
        "config/network_monitoring_dashboard.yaml",
    ):
        assert "ISP_EQUIPMENT" not in (ROOT / name).read_text()
