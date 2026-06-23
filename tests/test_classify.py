from classify import classify_connectivity, outage_confidence, requires_diagnosis


def _results(router=1.0, gw=9.0, gw_configured=True,
             dns_ok=True, http_ok=True, anchor=(True, 40.0),
             health_score=100, jitter=1.0, modem=None,
             modem_configured=False):
    return {
        "router": router,
        "router_health": {"health_score": health_score},
        "isp_gateway_configured": gw_configured,
        "isp_gateway": gw,
        "modem_configured": modem_configured,
        "modem": modem,
        "dns": {"all_succeeded": dns_ok},
        "http": {"all_succeeded": http_ok},
        "anchor": anchor,
        "jitter": jitter,
    }


def test_unobserved_gateway_is_not_lastmile_failure():
    code, _ = classify_connectivity(_results(
        gw=None, gw_configured=False, dns_ok=False, http_ok=False,
        anchor=(False, None),
    ))
    assert code is None


def test_gateway_down_with_corroborating_failures_is_lastmile_suspect():
    results = _results(
        gw=None, dns_ok=False, http_ok=False, anchor=(False, None),
    )
    code, confidence = classify_connectivity(results)
    assert code == "LASTMILE_RF_SUSPECT"
    assert confidence >= 0.7


def test_slow_gateway_requires_diagnosis_even_when_public_checks_pass():
    results = _results(gw=180.0)
    assert classify_connectivity(results)[0] == "ISP_INGRESS_CONGEST"
    assert requires_diagnosis(results) is True


def test_healthy_gateway_and_failed_anchor_is_core_routing():
    code, _ = classify_connectivity(_results(
        gw=9.0, dns_ok=False, http_ok=False, anchor=(False, None),
    ))
    assert code == "ISP_CORE_ROUTING"


def test_healthy_anchor_becomes_specific_path_degradation():
    code, _ = classify_connectivity(_results(
        gw=9.0, dns_ok=False, http_ok=False, anchor=(True, 20.0),
    ))
    assert code == "DEGRADED_INTERNET"


def test_router_degradation_and_high_jitter_require_diagnosis():
    assert requires_diagnosis(_results(health_score=40)) is True
    assert requires_diagnosis(_results(jitter=80.0)) is True


def test_single_failed_signal_has_low_confidence():
    assert outage_confidence(_results(dns_ok=False)) < 0.5


def test_corroborated_modem_failure_is_high_confidence_modem_down():
    results = _results(
        modem=None,
        modem_configured=True,
        gw=None,
        dns_ok=False,
        http_ok=False,
        anchor=(False, None),
    )

    code, confidence = classify_connectivity(results)

    assert code == "MODEM_DOWN"
    assert confidence >= 0.9
    assert requires_diagnosis(results) is True


def test_modem_icmp_failure_does_not_create_outage_when_internet_is_healthy():
    results = _results(
        modem=None,
        modem_configured=True,
        gw=9.0,
        dns_ok=True,
        http_ok=True,
    )

    assert classify_connectivity(results)[0] is None
    assert requires_diagnosis(results) is False


def test_reachable_modem_and_failed_gateway_remains_lastmile_suspect():
    code, _ = classify_connectivity(_results(
        modem=1.5,
        modem_configured=True,
        gw=None,
        dns_ok=False,
        http_ok=False,
        anchor=(False, None),
    ))

    assert code == "LASTMILE_RF_SUSPECT"


def test_healthy_anchor_prevents_modem_down_attribution():
    code, _ = classify_connectivity(_results(
        modem=None,
        modem_configured=True,
        gw=None,
        dns_ok=False,
        http_ok=False,
        anchor=(True, 20.0),
    ))

    assert code == "DEGRADED_INTERNET"
