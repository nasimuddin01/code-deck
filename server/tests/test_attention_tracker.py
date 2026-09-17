from code_deck.providers.stats import SessionInfo, ToolStats
from code_deck.state.attention import AttentionTracker


def tools(*sessions: SessionInfo) -> list[ToolStats]:
    return [ToolStats(name="Claude Code", model="", sessions_today=0, tokens_in=0,
                      tokens_out=0, cost_usd=0.0, sessions=list(sessions))]


def sess(sid: str, needs: bool, kind: str = "") -> SessionInfo:
    return SessionInfo(id=sid, label=f"proj-{sid}", needs_input=needs, attention_kind=kind)


def test_needs_starts_overlay_once():
    t = AttentionTracker(seconds=10)
    started = t.update(tools(sess("a", True, "needs")), now=100.0)
    assert [o.session_id for o in started] == ["a"]
    assert t.current and t.current.label == "proj-a" and t.current.kind == "needs"
    # same key on the next poll: no re-announce
    assert t.update(tools(sess("a", True, "needs")), now=101.0) == []
    assert t.current is not None


def test_idle_never_starts_overlay():
    t = AttentionTracker()
    assert t.update(tools(sess("a", True, "idle")), now=0.0) == []
    assert t.current is None


def test_idle_then_needs_reannounces():
    t = AttentionTracker()
    t.update(tools(sess("a", True, "idle")), now=0.0)
    started = t.update(tools(sess("a", True, "needs")), now=1.0)
    assert len(started) == 1 and started[0].kind == "needs"


def test_cleared_then_needs_again_reannounces():
    t = AttentionTracker()
    t.update(tools(sess("a", True, "needs")), now=0.0)
    t.update(tools(sess("a", False)), now=20.0)  # user replied
    assert t.update(tools(sess("a", True, "needs")), now=30.0)


def test_overlay_expires():
    t = AttentionTracker(seconds=5)
    t.update(tools(sess("a", True, "needs")), now=0.0)
    t.update(tools(sess("a", True, "needs")), now=4.9)
    assert t.current is not None
    t.update(tools(sess("a", True, "needs")), now=5.0)
    assert t.current is None


def test_disabled_tracks_but_never_starts():
    t = AttentionTracker(enabled=False)
    assert t.update(tools(sess("a", True, "needs")), now=0.0) == []
    assert t.current is None


def test_missing_kind_defaults_to_needs():
    t = AttentionTracker()
    started = t.update(tools(sess("a", True, "")), now=0.0)
    assert started and started[0].kind == "needs"
