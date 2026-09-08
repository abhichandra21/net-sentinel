from unittest.mock import MagicMock, patch

import pytest

from modem_probe import probe_bgw620


HOME_HTML = """
<html><body>
<form method="post" action="/cgi-bin/sysinfo.ha">
<input type="hidden" name="nonce" value="deadbeefcafef00d1234567890abcdef" />
<input type="submit" name="Sysinfo" class="cssbtn" value="More Info" />
</form>
</body></html>
"""

BBSTATS_HTML = """
<html><body>
<table class="table75">
<tr><th scope="row" width="47%">Broadband Connection Source</th><td class="col2">
FIBER
</td></tr>
<tr><th scope="row" width="47%">Broadband Connection</th>
<td class="col2">
Up
</td></tr>
<tr><th scope="row">Broadband IPv4 Address</th>
<td class="col2">104.181.122.68</td></tr>
</table>
</body></html>
"""

FIBERSTAT_HTML = """
<html><body>
<table class="table75">
<tr><th scope="row" width="47%">Optical WAN Operational Status</th>
<td class="col2">Up                 </td></tr>
<tr><th scope="row">Last Change</th>
<td class="col2">1788819872                 </td></tr>
</table>
<h1>Temperature&nbsp;&nbsp;Currently 38.110</h1>
<h1>Tx Power&nbsp;&nbsp;Currently 39.630</h1>
<h1>Rx Power&nbsp;&nbsp;Currently 0.177</h1>
</body></html>
"""

FIBERSTAT_DOWN_HTML = FIBERSTAT_HTML.replace(
    ">Up                 <", ">Down                 <"
)


def _make_response(text, status=200):
    resp = MagicMock()
    resp.text = text
    resp.status_code = status
    if status >= 400:
        resp.raise_for_status = MagicMock(
            side_effect=Exception(f"HTTP {status}")
        )
    else:
        resp.raise_for_status = MagicMock()
    return resp


def _session_with(get_response, post_map):
    """Build a fake requests.Session where get() and post() return canned data.
    post_map is {path_suffix: response_or_exception}."""
    session = MagicMock()
    session.get = MagicMock(return_value=get_response)

    def fake_post(url, **kwargs):
        for suffix, value in post_map.items():
            if url.endswith(suffix):
                if isinstance(value, Exception):
                    raise value
                return value
        raise AssertionError(f"unexpected POST to {url}")

    session.post = MagicMock(side_effect=fake_post)
    session.close = MagicMock()
    return session


@patch("modem_probe.requests.Session")
def test_happy_path_returns_all_fields(session_cls):
    session_cls.return_value = _session_with(
        _make_response(HOME_HTML),
        {
            "broadbandstatistics.ha": _make_response(BBSTATS_HTML),
            "fiberstat.ha": _make_response(FIBERSTAT_HTML),
        },
    )

    result = probe_bgw620("192.168.10.254")

    assert result["success"] is True
    assert result["broadband_valid"] is True
    assert result["fiber_valid"] is True
    assert result["error"] is None
    assert result["wan_state"] == "up"
    assert result["fiber_state"] == "up"
    assert result["wan_ip"] == "104.181.122.68"
    assert result["last_change_timestamp"] == 1788819872
    # 0.177 * 0.1 = 0.0177 uW
    assert result["rx_power_uw"] == pytest.approx(0.0177, abs=1e-4)
    assert result["tx_power_uw"] == pytest.approx(3.963, abs=1e-3)
    assert result["temp_c"] == pytest.approx(38.11, abs=1e-2)


@patch("modem_probe.requests.Session")
def test_fiber_down_state_is_captured(session_cls):
    session_cls.return_value = _session_with(
        _make_response(HOME_HTML),
        {
            "broadbandstatistics.ha": _make_response(BBSTATS_HTML),
            "fiberstat.ha": _make_response(FIBERSTAT_DOWN_HTML),
        },
    )

    result = probe_bgw620("192.168.10.254")

    assert result["success"] is True
    assert result["fiber_state"] == "down"
    assert result["wan_state"] == "up"


@patch("modem_probe.requests.Session")
def test_fiberstat_timeout_leaves_wan_populated(session_cls):
    session_cls.return_value = _session_with(
        _make_response(HOME_HTML),
        {
            "broadbandstatistics.ha": _make_response(BBSTATS_HTML),
            "fiberstat.ha": TimeoutError("read timed out"),
        },
    )

    result = probe_bgw620("192.168.10.254")

    assert result["success"] is False
    assert result["broadband_valid"] is True
    assert result["fiber_valid"] is False
    assert result["wan_state"] == "up"
    assert result["wan_ip"] == "104.181.122.68"
    assert result["fiber_state"] is None
    assert result["rx_power_uw"] is None
    assert result["tx_power_uw"] is None
    assert result["temp_c"] is None
    assert result["last_change_timestamp"] is None
    assert "fiberstat" in result["error"]


@patch("modem_probe.requests.Session")
def test_http_500_on_bbstats_returns_failure(session_cls):
    session_cls.return_value = _session_with(
        _make_response(HOME_HTML),
        {
            "broadbandstatistics.ha": _make_response("", status=500),
            "fiberstat.ha": _make_response(FIBERSTAT_HTML),
        },
    )

    result = probe_bgw620("192.168.10.254")

    assert result["success"] is False
    assert result["broadband_valid"] is False
    assert result["fiber_valid"] is True
    assert result["wan_state"] is None
    assert result["wan_ip"] is None
    assert "broadbandstatistics" in result["error"]
    # Fiberstat still parsed successfully.
    assert result["fiber_state"] == "up"


@patch("modem_probe.requests.Session")
def test_http_200_with_unrecognized_pages_returns_failure(session_cls):
    session_cls.return_value = _session_with(
        _make_response(HOME_HTML),
        {
            "broadbandstatistics.ha": _make_response("<html>changed</html>"),
            "fiberstat.ha": _make_response("<html>changed</html>"),
        },
    )

    result = probe_bgw620("192.168.10.254")

    assert result["success"] is False
    assert result["broadband_valid"] is False
    assert result["fiber_valid"] is False
    assert result["error"] is not None


@patch("modem_probe.requests.Session")
def test_home_page_failure_returns_all_none(session_cls):
    home_error = MagicMock()
    home_error.raise_for_status = MagicMock(
        side_effect=Exception("connection refused")
    )
    session_cls.return_value = _session_with(home_error, {})

    result = probe_bgw620("192.168.10.254")

    assert result["success"] is False
    assert result["wan_state"] is None
    assert result["fiber_state"] is None
    assert result["error"] is not None


@patch("modem_probe.requests.Session")
def test_missing_nonce_short_circuits(session_cls):
    session_cls.return_value = _session_with(
        _make_response("<html>no nonce here</html>"),
        {},
    )

    result = probe_bgw620("192.168.10.254")

    assert result["success"] is False
    assert result["error"] == "nonce not found on home.ha"
