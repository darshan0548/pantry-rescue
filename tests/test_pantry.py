from datetime import date, timedelta

import pytest

from pantry import server


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("PANTRY_DB", str(tmp_path / "t.db"))


def test_add_uses_shelf_life_and_normalises_plurals():
    r = server.add_items(["Tomatoes", "spinach"])
    assert {a["name"]: a["days_left"] for a in r["added"]} == {"tomato": 6, "spinach": 4}
    assert "Spinach will go off first" in r["speech"]


def test_list_expiring_orders_by_urgency():
    server.add_items(["spinach", "rice"])
    r = server.list_expiring(4)
    assert [i["name"] for i in r["items"]] == ["spinach"]
    assert server.list_expiring(2)["items"] == []


def test_suggest_meal_prefers_expiring_items():
    server.add_items(["spinach", "paneer", "onion", "tomato"])
    r = server.suggest_meal()
    assert r["options"][0]["recipe"] == "Palak paneer"
    assert r["options"][0]["missing"] == []


def test_mark_used_and_summary():
    server.add_items(["milk"])
    assert server.mark_used("milk")["ok"]
    assert not server.mark_used("milk")["ok"]
    s = server.weekly_summary()
    assert (s["saved"], s["wasted"], s["rescue_rate"]) == (1, 0, 100)


def test_expired_items_count_as_wasted(monkeypatch):
    server.add_items(["bread"])
    monkeypatch.setattr(server, "today", lambda: date.today() + timedelta(days=10))
    assert server.weekly_summary()["wasted"] == 1
    assert server.active() == []


def test_board_payload_and_widget_registered():
    server.add_items(["curd"])
    assert server.show_pantry_board()["items"][0]["name"] == "curd"
    assert "<html" in server.board_ui()
