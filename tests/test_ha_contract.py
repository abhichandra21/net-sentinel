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
