import re
from pathlib import Path

PROM = Path(__file__).resolve().parents[2] / "ops" / "prometheus"
ALERTS = ("GetnetHighErrorRate", "GetnetHighLatencyP95", "GetnetHighCostPerHour", "GetnetTicketWaiting")


def _rules() -> dict[str, str]:
    """alert name -> its rule block text."""
    text = (PROM / "alerts.yml").read_text()
    parts = re.split(r"^\s*- alert:\s*", text, flags=re.M)[1:]
    return {p.split("\n", 1)[0].strip(): p for p in parts}


def test_fr059_four_alerts_present():
    assert set(_rules()) == set(ALERTS)


def test_fr059_alert_expressions_and_windows():
    r = _rules()
    assert 'code=~"5.."' in r["GetnetHighErrorRate"] and "> 0.05" in r["GetnetHighErrorRate"]
    assert "for: 5m" in r["GetnetHighErrorRate"]
    assert "histogram_quantile(0.95" in r["GetnetHighLatencyP95"]
    assert "> 20" in r["GetnetHighLatencyP95"] and "for: 10m" in r["GetnetHighLatencyP95"]
    assert "increase(getnet_llm_cost_usd_total[1h])" in r["GetnetHighCostPerHour"]
    assert "> 1" in r["GetnetHighCostPerHour"]
    assert "getnet_ticket_oldest_age_seconds > 1800" in r["GetnetTicketWaiting"]
    for name, block in r.items():
        assert "severity:" in block and "summary:" in block, name


def test_fr059_each_alert_has_firing_unit_test():
    text = (PROM / "alerts.test.yml").read_text()
    assert re.search(r"^rule_files:\s*\n\s*- alerts\.yml", text, flags=re.M)
    for name in ALERTS:
        blocks = re.findall(rf"alertname: {name}\n\s*exp_alerts:(.*?)(?=\n\s*- eval_time|\n  #|\Z)",
                            text, flags=re.S)
        assert any("exp_labels" in b for b in blocks), f"no firing test for {name}"


def test_fr059_prometheus_scrapes_api_and_loads_rules():
    text = (PROM / "prometheus.yml").read_text()
    assert "job_name: getnet-api" in text
    assert '"api:8000"' in text and "metrics_path: /metrics" in text
    assert "/etc/prometheus/alerts.yml" in text
