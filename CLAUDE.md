# CLAUDE.md

Guidance for Claude Code (claude.ai/code) when working in this repository.

## What this is

Net Sentinel watches a home internet connection and answers one question when it breaks: whose fault is it?
It distinguishes your router, your fiber gateway, the ISP last mile, ISP core routing, and plain degradation, and publishes a fault code with a confidence score.

The uplink is AT&T fiber terminated on a BGW620-700 residential gateway.
Earlier versions of this project assumed a cable modem plus CMTS; that is gone.
If you see the words "cable", "CMTS", or "RF" anywhere outside git history, it is stale and should be fixed.

Three pieces:

1. **Local sentinel** - Python in Docker on the home LAN. Probes the path outward hop by hop, classifies faults, publishes to MQTT.
2. **Cloud probe** - Python on an external VPS. Probes the home from outside and POSTs to a Home Assistant webhook. Answers "is the house reachable from the internet", which the local sentinel structurally cannot.
3. **Home Assistant** - MQTT broker, webhook receiver, dashboards, alert automations.

## Commands

### Local sentinel

```bash
# MQTT_PASSWORD is mandatory; compose fails fast without it
export MQTT_PASSWORD=...

docker-compose up -d --build
docker logs -f net-sentinel
docker-compose down
docker-compose up -d --build --force-recreate   # after code changes
```

### Tests

There are 76 tests and they run in about five seconds with no network access.
Run them before and after any change to `sentinel/src/`.

```bash
.venv/bin/pytest -q                    # whole suite
.venv/bin/pytest -q tests/test_classify.py
.venv/bin/pytest -q -k modem
```

`pytest.ini` puts `sentinel/src` on `pythonpath`, so tests import `classify`, `monitor`, etc. as top-level modules.
A `.venv` already exists in the repo root; use it rather than the system Python.

### Running the sentinel outside Docker

```bash
cp config/config.example.yaml config/config.yaml   # then edit
export MQTT_PASSWORD=...
CONFIG_PATH=config/config.yaml .venv/bin/python sentinel/src/monitor.py
```

Ping needs raw sockets, so ICMP checks return `None` unless you run as root.
The sentinel degrades gracefully rather than crashing, which makes a non-root local run useful for testing MQTT and classification but not reachability.

### Cloud probe

```bash
./deploy_cloud_probe.sh <home-ddns-or-public-ip>

ssh -i ~/.ssh/aws.pub ubuntu@ssh-day1.abhichandra.com 'sudo journalctl -u cloud-probe -f'
ssh -i ~/.ssh/aws.pub ubuntu@ssh-day1.abhichandra.com 'sudo systemctl restart cloud-probe'
```

The deploy script scp's a single file, writes `/etc/systemd/system/cloud-probe.service`, and restarts it.
The webhook URL is hardcoded in that script, not read from config.

## Architecture

```
Local sentinel: sentinel/src/monitor.py
  |
  |- every interval_seconds (30): perform_health_check()
  |    router_health   check_router_health()  5 pings -> loss, latency, jitter, 0-100 score
  |    router          check_ping()
  |    modem           check_ping() -> smoothed_reachability()
  |    isp_gateway     check_ping() -> smoothed_reachability()
  |    dns             check_multi_dns()   4 domains x configured resolvers
  |    http            check_multi_http()  4 public endpoints, hard deadline
  |    jitter          calculate_jitter()  stdev of last 10 router ICMP RTTs
  |    anchor          check_http() against our own VPS
  |    modem_probe     probe_bgw620()      cached, refreshed every 60s
  |
  |- classify.requires_diagnosis(results) -> healthy or not
  |- on Nth consecutive failure: diagnose_issue() -> fault code
  |- publish via notifier.py -> MQTT
  |
  '- every speedtest.interval_hours (6): perform_speedtest()
       throughput, then measure_bufferbloat() and classify_load()

Cloud probe: cloud_probe/main.py
  every --interval (60): check_home_connectivity()
  debounce 3 consecutive same-direction reads
  POST {source, status, latency} -> HA webhook

Home Assistant
  MQTT broker, webhook, dashboards, alert automations
```

### The layered probe idea

Each probe isolates one segment of the path, so a failure pattern across them localizes the fault.
Router up but gateway unreachable means the last mile.
Gateway reachable but nothing public resolves means ISP core.
Everything public failing while our own VPS anchor still answers means the problem is not our uplink at all.
The classifier encodes exactly this reasoning and nothing more.

### Fault attribution

Two layers make the decision, and the split matters.

**`classify.py` is pure.** No network I/O, no MQTT, no logging.
It takes a results dict and returns `(code, confidence)`.
This is why fault logic is cheap to test, and it is where new attribution rules belong.

**`monitor.py:diagnose_issue`** wraps it with the side effects: traceroute capture, CSV events, MQTT state, log lines.
It also owns the router-health codes that run before the classifier and the DNS/HTTP/jitter fallbacks that run after.

Order inside `diagnose_issue`:

| Order | Source | Codes |
|---|---|---|
| 1 | `monitor.py` | `ROUTER_DOWN` - router does not answer ping. Authoritative, checked first so a failing router-health probe cannot mask it. |
| 2 | `monitor.py` | `ROUTER_CRITICAL` (score < 30), `ROUTER_DEGRADED` (score < 60 and public checks are fine) |
| 3 | `classify.py` | `FIBER_LINK_DOWN`, `MODEM_DOWN`, `LASTMILE_FIBER_SUSPECT`, `ISP_INGRESS_CONGEST`, `ISP_CORE_ROUTING`, `DEGRADED_INTERNET` |
| 4 | `monitor.py` | `ISP_ROUTING` (DNS and HTTP both fully failed), `ISP_DNS` (all DNS only), `DEGRADED_DNS` (partial) |
| 5 | `monitor.py` | `ISP_ROUTING` (all HTTP failed), `DEGRADED_INTERNET` (partial) |
| 6 | `monitor.py` | `DEGRADED_QUALITY` - jitter over threshold |
| 7 | `monitor.py` | `TRANSIENT` - nothing reproduced |

`classify.classify_load` runs on the speedtest schedule, separately from all of the above, and yields `DEGRADED_UNDER_LOAD`.

Inside `classify_connectivity`, two rules are worth knowing:

- A valid BGW620 fiber page reporting `fiber_state == "down"` short-circuits everything at confidence 0.95, even if the broadband page failed. Direct observation from the gateway beats inference from probes.
- Every other code requires `isp_gateway_configured`. Without a known first hop there is no way to separate last mile from core, so the classifier returns `None` and lets the DNS/HTTP fallbacks handle it.

`outage_confidence` is just the fraction of independent signals that agree something is down.
Individual rules floor it (`max(0.9, confidence)` and similar) so a high-certainty pattern is not diluted by signals that happen to look fine.

### Status vs blame

Two separate MQTT sensors, easy to conflate:

- `blame` is the raw fault code, or `NONE` when healthy.
- `status` is derived in the main loop: `HEALTHY`, `DIAGNOSING`, `TRANSIENT`, `DEGRADED_*`, or `OUTAGE_<code>`.

The `OUTAGE_` prefix is added in `main()`, not by the classifier.
Home Assistant automations trigger on `status`, so changing that mapping breaks alerts.

## Configuration

`config/config.yaml` is gitignored and never committed.
`config/config.example.yaml` is the tracked template; keep it in sync when you add a key.

Path resolution: `CONFIG_PATH` env var, else `config/config.yaml`, else `../../config/config.yaml`, else exit 1.

```yaml
monitoring:
  interval_seconds: 30
  consecutive_failures_threshold: 2

  targets:
    router: "192.168.1.1"
    modem: null          # BGW620 LAN address 192.168.10.254; enables ping + HTML probe
    isp_gateway: null    # auto-detected at startup when null
    cloud_anchor: null   # our own VPS URL
    public_dns_1: "8.8.8.8"
    public_dns_2: "1.1.1.1"

  timeouts:
    dns_seconds: 2.0
    http_seconds: 10.0
    ping_seconds: 2.0

  thresholds:
    ingress_latency_ms: 120
    jitter_ms: 50
    bufferbloat_ms: 50
    loaded_loss_pct: 5

  speedtest:
    use_cloudflare: true
    interval_hours: 6

mqtt:
  broker: "192.168.1.50"
  port: 1883
  username: "mqtt_user"
  password: "${MQTT_PASSWORD}"
  topic_prefix: "home/network/sentinel"

logging:
  file_path: "/data/network_events.csv"
```

### Secrets

Any `${VAR}` in a string value is expanded from the environment by `monitor.py:_expand_env`, recursively through dicts and lists.
An unset or empty variable raises rather than silently resolving to nothing.
`docker-compose.yml` uses `${MQTT_PASSWORD:?...}` so the container refuses to start without it.

Never put a literal secret in `config.example.yaml` or in a committed file.

### Targets that auto-configure

`isp_gateway` left as `null` triggers `detect_isp_gateway()` once at startup, which traceroutes to 8.8.8.8 and takes the first responding hop that is not the router.
On failure it logs a warning and the entire ISP-attribution layer is disabled for that process lifetime.
There is no re-detection, so a gateway change needs a restart.

## Modules

**`sentinel/src/monitor.py`** (637 lines) - config loading and env expansion, the health-check orchestrator, modem-probe caching, reachability smoothing, `diagnose_issue`, path-metric publication, the main loop.

**`sentinel/src/classify.py`** (82 lines) - pure fault decisions. `classify_connectivity`, `requires_diagnosis`, `classify_load`, `outage_confidence`. No I/O, no imports beyond the stdlib. Keep it that way.

**`sentinel/src/diagnostics.py`** (406 lines) - all network I/O. Ping, DNS, HTTP, traceroute, gateway detection, router health and scoring, jitter, bufferbloat under verified load, Cloudflare and speedtest-cli throughput.

**`sentinel/src/modem_probe.py`** (124 lines) - BGW620-700 scraper. Three requests per probe: `home.ha` for a session cookie and form nonce, then POSTs to `broadbandstatistics.ha` and `fiberstat.ha`. Regex parsing, deliberately no BeautifulSoup dependency. Never logs; the caller decides. Tracks `broadband_valid` and `fiber_valid` separately, sets aggregate `success` only when both pages contain recognized fields, and retains valid partial results.

**`sentinel/src/notifier.py`** (219 lines) - MQTT client, HA auto-discovery, availability topics, CSV event log.

**`cloud_probe/main.py`** (119 lines) - external reachability probe with debounce. Standalone, argparse-driven, no config file.

## Home Assistant integration

Discovery is automatic. `notifier.py:DISCOVERY_SENSORS` is the single source of truth for every sensor: key, friendly name, unit, icon, state class, and whether it has an availability topic.

Topics:

```
homeassistant/sensor/netsentinel_<key>/config    retained discovery payload
<topic_prefix>/<key>/state                       retained state
<topic_prefix>/<key>/availability                retained "online" / "offline"
```

`update_state` warns once per unknown key if you publish something with no discovery entry, which is how you catch a typo or a forgotten `DISCOVERY_SENSORS` addition.

Sensors marked `"availability": True` are values that can legitimately be unavailable, including the gateway timestamp.
When a BGW620 page fails, `_publish_modem_probe_metrics` flips only its dependent sensors offline while publishing valid data from the other page.
When the target is disabled, it publishes `disabled`, clears the retained text states, and marks all gateway measurements unavailable.
That distinction matters: a hidden sensor and a sensor reporting last hour's optical power are very different during an outage.

`RETIRED_DISCOVERY_KEYS` holds sensors that once existed. An empty retained payload is published to their config topic to delete them from HA. Add to this set when you remove a sensor; do not just delete the entry.

YAML files in the repo are reference copies of what lives in Home Assistant, not something the sentinel reads:

- `ha_comprehensive_setup.yaml` - MQTT sensor definitions
- `ha_dashboard.yaml`, `config/network_monitoring_dashboard.yaml` - Lovelace cards
- `ha_automation_alerts.yaml` - alert automations
- `ha_complete_setup.yaml` - helpers, webhook automation, dashboard in one file

`tests/test_ha_contract.py` and `tests/test_discovery.py` check that published keys and these YAML files agree. If you add a sensor and those fail, the YAML is what is out of date.

## Implementation details worth knowing

### Reachability smoothing

A single `ping3` sample from the privileged container is noisy enough to flap attribution between `MODEM_DOWN`, `LASTMILE_FIBER_SUSPECT`, and `ISP_CORE_ROUTING` during one outage.
`smoothed_reachability` keeps a 5-sample window per target and reports the majority state, returning the mean latency of responding samples when reachable and `None` otherwise.

Consequence: the modem and gateway signals lag reality by up to three samples.
Do not add a rule that assumes those two values are instantaneous.

### Modem probe cadence

Each probe is three HTTP requests against a consumer gateway, so it runs at most once every `MODEM_PROBE_INTERVAL_S` (60) regardless of loop interval.
`_maybe_probe_modem` returns the cached dict in between, and `None` until the first probe completes.
Publication is suppressed entirely while it is `None`, so a healthy gateway does not show a minute of `UNAVAILABLE` at startup.

### HTTP checks have a hard deadline

`requests`' own timeout does not cover DNS resolution, so during an outage an uncached lookup can block 20 seconds or more and stretch the whole cycle.
`check_multi_http` uses one process-wide four-worker executor, bounds `as_completed` at `timeout + 1`, and marks every future not yielded by the deadline as failed.
If any worker from the previous batch is still blocked, the next cycle reports the endpoints failed without submitting another batch.

This is why detection latency stays bounded during exactly the event the system exists to catch.

### Adaptive loop cadence

The loop sleeps `interval_seconds` while healthy and `failure_interval_seconds` (default 5) once `consecutive_failures > 0`.
Detection latency during a failing streak is therefore a few seconds rather than several full intervals.

Note: `failure_interval_seconds` is read by `monitor.py` but is absent from `config.example.yaml`.
Add it there if you touch that area.

### Jitter comes from ICMP, not HTTP

`latency_history` only ever receives router ping RTT.
HTTP latency includes DNS, TCP, TLS, and server think time, none of which say anything about path stability.
Do not feed HTTP timings into jitter.

### Speedtest latency is a real RTT

`run_cloudflare_speedtest` downloads 25 MB for throughput and separately pings `speed.cloudflare.com` for `latency_ms`.
The download duration is not latency. This was a real bug once; do not reintroduce it.

### Bufferbloat requires verified load

`measure_bufferbloat` pings idle, starts a background 100 MB Cloudflare download, and waits for `ready_event` confirming bytes actually arrived before sampling loaded RTT.
If the load generator fails or never delivers within 5 seconds, it returns `None` rather than reporting a meaningless zero-bloat result.

### Cloud probe debounce

Status flips only after 3 consecutive same-direction reads, so one dropped packet is not an outage.
`update_debounce` is pure and tested; the loop around it is the only stateful part.

### Docker requirements

`network_mode: "host"` and `privileged: true` are both needed: host networking for ping and traceroute from the host's perspective and for reaching 192.168.1.x, privileged for ICMP raw sockets.
The container runs as root for the same reason.
`./config` mounts to `/app/config`, `./data` to `/data`.

## Known environment

**Home network**

| Thing | Address |
|---|---|
| Router | 192.168.1.1 |
| BGW620-700 gateway | configured as `targets.modem` |
| Home Assistant | 192.168.1.50 |
| Docker host | 192.168.1.3 |
| MQTT | 192.168.1.50:1883 |

**VPS** - `ssh-day1.abhichandra.com`, user `ubuntu`, key `~/.ssh/aws.pub`, unit `cloud-probe.service`, working dir `/home/ubuntu/cloud-probe`.

**HA webhook** - id `net-sentinel-cloud-probe-2025` at `http://192.168.1.50:8123/api/webhook/net-sentinel-cloud-probe-2025`. Hardcoded in `deploy_cloud_probe.sh`.

## Rough edges

Real, known, and not worth fixing as a drive-by:

- `diagnostics.py` defines `check_interface_status` twice, at lines 14 and 173. The second wins, so the `eth0` operstate version is dead code. `monitor.py` imports the name but never calls it.
- `check_ping` accepts a `count` parameter it ignores.
- `notifier.py` uses the paho-mqtt 1.x `mqtt.Client("NetSentinel")` signature, pinned at 1.6.1. Upgrading to 2.x requires a callback-API change.
- `_setup_mqtt` skips setup when the broker is falsy or literally `192.168.1.10`, a leftover placeholder sentinel.
- `DEGRADED_INTERNET` is produced by both `classify.py` and the HTTP fallback in `diagnose_issue`, from different conditions.

## Making changes

### A new diagnostic check

1. Add the probe to `diagnostics.py`. Network I/O lives there and nowhere else.
2. Call it from `perform_health_check` and put the result in the `results` dict.
3. If it should influence attribution, read it in `classify.py`. Do not add I/O there.
4. Add a `DISCOVERY_SENSORS` entry in `notifier.py` and publish with `update_state`.
5. Test the classifier logic against a synthetic `results` dict; no network needed.

### A new fault code

1. Add the rule to `classify.classify_connectivity`, positioned deliberately. Order is significance: earlier rules are more specific.
2. Add a human-readable line to the `details` dict in `diagnose_issue`.
3. Decide severity. Membership in `degraded_codes` selects `WARNING`/`DEGRADED` over `CRITICAL`/`OUTAGE`.
4. Extend `tests/test_classify.py`, including a case proving the new rule does not steal from an existing one.
5. Update `ha_dashboard.yaml` and `ha_automation_alerts.yaml` if it needs to be visible or alertable.
6. Update the table in this file and in `README.md`.

### Changing intervals or thresholds

Everything lives under `monitoring` in `config.yaml`, with a code default behind each `.get()`.
Change both the example config and the default when you change intent, otherwise the two disagree and the example stops being a description of the system.
