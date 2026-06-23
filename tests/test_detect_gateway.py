import diagnostics


SAMPLE_TRACE = """\
 1  192.168.1.1  1.234 ms
 2  100.64.0.1  9.100 ms
 3  24.30.200.1  12.0 ms
"""


def test_detect_isp_gateway_returns_hop_beyond_router(monkeypatch):
    monkeypatch.setattr(diagnostics, "run_traceroute", lambda target="8.8.8.8": SAMPLE_TRACE)
    assert diagnostics.detect_isp_gateway("192.168.1.1") == "100.64.0.1"


def test_detect_isp_gateway_ignores_traceroute_destination_header(monkeypatch):
    trace = """\
traceroute to 8.8.8.8 (8.8.8.8), 10 hops max, 60 byte packets
 1  192.168.1.1  1.234 ms
 2  100.64.0.1  9.100 ms
"""
    monkeypatch.setattr(diagnostics, "run_traceroute", lambda target="8.8.8.8": trace)
    assert diagnostics.detect_isp_gateway("192.168.1.1") == "100.64.0.1"


def test_detect_isp_gateway_none_when_only_router(monkeypatch):
    monkeypatch.setattr(diagnostics, "run_traceroute", lambda target="8.8.8.8": " 1  192.168.1.1  1.2 ms\n")
    assert diagnostics.detect_isp_gateway("192.168.1.1") is None


def test_detect_isp_gateway_skips_unresponsive_hops(monkeypatch):
    trace = " 1  192.168.1.1  1.2 ms\n 2  * * *\n 3  100.64.0.1  9.1 ms\n"
    monkeypatch.setattr(diagnostics, "run_traceroute", lambda target="8.8.8.8": trace)
    assert diagnostics.detect_isp_gateway("192.168.1.1") == "100.64.0.1"
