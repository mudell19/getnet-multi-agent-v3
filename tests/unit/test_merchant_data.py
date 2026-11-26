import json

from getnet_multi_agent.core.settings import MERCHANTS_FILE


def _data():
    return json.loads(MERCHANTS_FILE.read_text())


def test_fr023_cliente1988_has_offline_and_declined_terminals():
    t = {x["status"]: x for x in _data()["cliente1988"]["terminals"]}
    assert t["offline"]["last_errors"][0]["type"] == "connectivity"
    decline = t["online"]["last_errors"][0]
    assert decline["type"] == "decline" and decline["reason"]["en"] and decline["reason"]["pt"]
    assert t["online"]["suggested_actions"]["en"]


def test_fr023_sales_relative_dates_and_second_merchant():
    d = _data()
    assert any(s["days_ago"] == 1 for s in d["cliente1988"]["sales"])
    assert all(isinstance(s["amount_cents"], int) for s in d["cliente1988"]["sales"])
    assert d["cliente2000"]["sales"] != d["cliente1988"]["sales"]
    assert "IGNORE PREVIOUS INSTRUCTIONS" in d["cliente2000"]["terminals"][0]["label"]
