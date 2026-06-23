"""Pure fault-attribution decisions. This module performs no network I/O."""


def outage_confidence(results):
    signals = [results.get("router") is None]
    if results.get("modem_configured", False):
        signals.append(results.get("modem") is None)
    if results.get("isp_gateway_configured", False):
        signals.append(results.get("isp_gateway") is None)
    signals.append(not results.get("dns", {}).get("all_succeeded", True))
    signals.append(not results.get("http", {}).get("all_succeeded", True))
    anchor = results.get("anchor")
    if anchor is not None:
        signals.append(anchor[0] is False)
    return round(sum(signals) / len(signals), 2) if signals else 0.0


def classify_connectivity(results, ingress_latency_ms=120):
    if results.get("router") is None:
        return (None, outage_confidence(results))
    dns_ok = results.get("dns", {}).get("all_succeeded", True)
    http_ok = results.get("http", {}).get("all_succeeded", True)
    internet_down = not dns_ok and not http_ok
    anchor = results.get("anchor")
    anchor_supports_outage = anchor is None or anchor[0] is False
    confidence = outage_confidence(results)

    if internet_down and anchor is not None and anchor[0] is True:
        return ("DEGRADED_INTERNET", max(0.6, confidence))
    if not results.get("isp_gateway_configured", False):
        return (None, confidence)

    gateway = results.get("isp_gateway")
    modem_down = (
        results.get("modem_configured", False)
        and results.get("modem") is None
    )

    if modem_down and gateway is None and internet_down and anchor_supports_outage:
        return ("MODEM_DOWN", max(0.9, confidence))
    if gateway is None and internet_down and anchor_supports_outage:
        return ("LASTMILE_RF_SUSPECT", max(0.7, confidence))
    if gateway is not None and gateway > ingress_latency_ms:
        return ("ISP_INGRESS_CONGEST", max(0.6, confidence))
    if gateway is not None and internet_down and anchor_supports_outage:
        return ("ISP_CORE_ROUTING", max(0.6, confidence))
    return (None, confidence)


def requires_diagnosis(results, ingress_latency_ms=120, jitter_ms=50):
    code, _ = classify_connectivity(results, ingress_latency_ms)
    router_health = results.get("router_health", {})
    health_score = router_health.get("health_score", 100)
    dns_ok = results.get("dns", {}).get("all_succeeded", True)
    http_ok = results.get("http", {}).get("all_succeeded", True)
    jitter = results.get("jitter")
    return any((
        results.get("router") is None,
        health_score < 60,
        not dns_ok,
        not http_ok,
        code is not None,
        jitter is not None and jitter > jitter_ms,
    ))


def classify_load(result, bloat_threshold_ms=50, loaded_loss_threshold_pct=5):
    if result is None:
        return (None, 0.0)
    bloat = result.get("bloat_ms")
    loss = result.get("loaded_loss_pct", 0.0)
    bloat_bad = bloat is not None and bloat >= bloat_threshold_ms
    loss_bad = loss >= loaded_loss_threshold_pct
    if bloat_bad or loss_bad:
        return ("DEGRADED_UNDER_LOAD", 0.8 if bloat_bad and loss_bad else 0.7)
    return (None, 0.0)
