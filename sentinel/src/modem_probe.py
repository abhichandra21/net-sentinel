"""BGW620-700 fiber gateway status scraper.

The gateway UI is HTML-only (no JSON API), so we scrape three pages per probe:
  - home.ha to obtain a session cookie and a form nonce
  - broadbandstatistics.ha for WAN connection state and public IPv4
  - fiberstat.ha for optical link state and transceiver readings

All parsing is regex-based to avoid adding a BeautifulSoup dependency.
"""

import re
import requests

# Raw h1 values on fiberstat.ha are reported in units of W/10,000,000
# (i.e. 10^-7 W). Multiplying by 0.1 yields microwatts (10^-6 W).
_OPTICAL_TO_UW = 0.1

_NONCE_RE = re.compile(r'name="nonce"\s+value="([0-9a-fA-F]+)"')
_WAN_STATE_RE = re.compile(
    r'Broadband Connection</th>\s*<td[^>]*>\s*([A-Za-z]+)', re.DOTALL)
_WAN_IP_RE = re.compile(
    r'Broadband IPv4 Address</th>\s*<td[^>]*>\s*([0-9.]+)', re.DOTALL)
_FIBER_STATE_RE = re.compile(
    r'Optical WAN Operational Status</th>\s*<td[^>]*>\s*([A-Za-z]+)', re.DOTALL)
_LAST_CHANGE_RE = re.compile(
    r'Last Change</th>\s*<td[^>]*>\s*(\d+)', re.DOTALL)
_RX_POWER_RE = re.compile(r'<h1>Rx Power[^<]*Currently\s+([0-9.]+)\s*</h1>')
_TX_POWER_RE = re.compile(r'<h1>Tx Power[^<]*Currently\s+([0-9.]+)\s*</h1>')
_TEMP_RE = re.compile(r'<h1>Temperature[^<]*Currently\s+([0-9.]+)\s*</h1>')


def _empty_result():
    return {
        "success": False, "wan_state": None, "fiber_state": None,
        "wan_ip": None, "last_change_seconds": None,
        "rx_power_uw": None, "tx_power_uw": None, "temp_c": None,
        "error": None,
    }


def _normalize_state(raw):
    if not raw:
        return None
    value = raw.strip().lower()
    return value if value in ("up", "down") else None


def _search(pattern, text, cast=None):
    if not text:
        return None
    m = pattern.search(text)
    if not m:
        return None
    value = m.group(1)
    if cast is None:
        return value
    try:
        return cast(value)
    except (TypeError, ValueError):
        return None


def probe_bgw620(host, timeout=5):
    """Scrape a BGW620-700 for WAN and optical status.

    Returns a dict; on any failure success=False and error carries the reason.
    The caller is responsible for logging; this module intentionally does not.
    """
    result = _empty_result()
    session = requests.Session()
    try:
        home = session.get(f"http://{host}/cgi-bin/home.ha", timeout=timeout)
        home.raise_for_status()
        nonce = _search(_NONCE_RE, home.text)
        if not nonce:
            result["error"] = "nonce not found on home.ha"
            return result

        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        data = {"nonce": nonce}

        bb_ok = False
        try:
            bb = session.post(
                f"http://{host}/cgi-bin/broadbandstatistics.ha",
                data=data, headers=headers, timeout=timeout)
            bb.raise_for_status()
            result["wan_state"] = _normalize_state(
                _search(_WAN_STATE_RE, bb.text))
            result["wan_ip"] = _search(_WAN_IP_RE, bb.text)
            bb_ok = True
        except Exception as e:
            result["error"] = f"broadbandstatistics: {e}"

        fiber_ok = False
        try:
            fs = session.post(
                f"http://{host}/cgi-bin/fiberstat.ha",
                data=data, headers=headers, timeout=timeout)
            fs.raise_for_status()
            result["fiber_state"] = _normalize_state(
                _search(_FIBER_STATE_RE, fs.text))
            result["last_change_seconds"] = _search(
                _LAST_CHANGE_RE, fs.text, cast=int)
            rx = _search(_RX_POWER_RE, fs.text, cast=float)
            tx = _search(_TX_POWER_RE, fs.text, cast=float)
            result["rx_power_uw"] = (
                round(rx * _OPTICAL_TO_UW, 4) if rx is not None else None)
            result["tx_power_uw"] = (
                round(tx * _OPTICAL_TO_UW, 4) if tx is not None else None)
            result["temp_c"] = _search(_TEMP_RE, fs.text, cast=float)
            fiber_ok = True
        except Exception as e:
            msg = f"fiberstat: {e}"
            result["error"] = (
                f"{result['error']}; {msg}" if result["error"] else msg)

        result["success"] = bb_ok and fiber_ok
        return result
    except Exception as e:
        result["error"] = str(e)
        return result
    finally:
        session.close()
