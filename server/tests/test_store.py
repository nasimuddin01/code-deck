import threading

from code_deck.state.store import StateStore


def test_publish_bumps_rev_only_on_change():
    s = StateStore()
    r0 = s.rev
    assert s.publish("system", {"cpu_pct": 1}) and s.rev == r0 + 1
    assert not s.publish("system", {"cpu_pct": 1}) and s.rev == r0 + 1
    assert s.publish("system", {"cpu_pct": 2}) and s.rev == r0 + 2


def test_snapshot_is_a_copy():
    s = StateStore()
    s.publish("tools", [{"name": "x"}])
    snap = s.snapshot()
    snap["tools"][0]["name"] = "mutated"
    assert s.get("tools")[0]["name"] == "x"
    assert "rev" in snap and "ts" in snap


def test_update_device_merges():
    s = StateStore()
    s.update_device(brightness=10)
    s.update_device(connected=True)
    d = s.get("device")
    assert d["brightness"] == 10 and d["connected"] is True


def test_wait_for_change_wakes_on_publish():
    s = StateStore()
    rev = s.rev
    woke = []

    def waiter():
        woke.append(s.wait_for_change(rev, timeout=2.0))

    t = threading.Thread(target=waiter)
    t.start()
    s.publish("system", {"cpu_pct": 5})
    t.join(2.5)
    assert woke == [True]


def test_wait_for_change_times_out():
    s = StateStore()
    assert s.wait_for_change(s.rev, timeout=0.05) is False
