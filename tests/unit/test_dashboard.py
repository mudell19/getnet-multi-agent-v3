import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GRAFANA = ROOT / "ops" / "grafana"

PANEL_METRICS = {
    "Requests by route and status": "getnet_requests_total",
    "Latency p95": "getnet_request_latency_seconds_bucket",
    "LLM cost per hour by model": "getnet_llm_cost_usd_total",
    "Tokens by model": "getnet_llm_tokens_total",
    "Refusals by reason": "getnet_refusals_total",
    "Escalations": "getnet_escalations_total",
    "Replans": "getnet_replans_total",
    "Quality violations": "getnet_quality_violations_total",
    "Open tickets": "getnet_tickets_open",
    "Oldest ticket age": "getnet_ticket_oldest_age_seconds",
}


def _service_block(compose: str, name: str) -> str:
    m = re.search(rf"^  {name}:\n(.*?)(?=^  \S|^\S|\Z)", compose, flags=re.M | re.S)
    assert m, f"service {name} missing"
    return m.group(1)


def test_fr060_dashboard_json_has_panels():
    dash = json.loads((GRAFANA / "dashboards" / "getnet.json").read_text())
    panels = {p["title"]: p for p in dash["panels"]}
    for title, metric in PANEL_METRICS.items():
        assert title in panels, title
        exprs = " ".join(t["expr"] for t in panels[title]["targets"])
        assert metric in exprs, title
        assert panels[title]["datasource"]["uid"] == "prometheus"


def test_fr060_provisioning_points_at_prometheus_and_dashboards():
    ds = (GRAFANA / "provisioning" / "datasources" / "prometheus.yml").read_text()
    assert "url: http://prometheus:9090" in ds and "uid: prometheus" in ds
    assert "isDefault: true" in ds
    prov = (GRAFANA / "provisioning" / "dashboards" / "provider.yml").read_text()
    assert "path: /var/lib/grafana/dashboards" in prov


def test_fr060_compose_services_under_observability_profile():
    compose = (ROOT / "compose.yaml").read_text()
    assert "profiles" not in _service_block(compose, "api")
    prom = _service_block(compose, "prometheus")
    graf = _service_block(compose, "grafana")
    for block in (prom, graf):
        assert "profiles: [observability]" in block
        assert "@sha256:" in block
        assert 'max-size: "10m"' in block and 'max-file: "3"' in block
    assert "./ops/prometheus:/etc/prometheus:ro" in prom
    assert "./ops/grafana/provisioning:/etc/grafana/provisioning:ro" in graf
    assert "./ops/grafana/dashboards:/var/lib/grafana/dashboards:ro" in graf
