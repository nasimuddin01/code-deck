"""Render the code-display dashboard to a PIL image.

Portrait 320x480 (panel native mode). Rendered at 2x and downscaled
for antialiasing. Palette: validated dark-mode reference (dataviz).

Layout: three account cards across the top — Claude Code on Vertex (est $),
Claude Max subscription (weekly quota %, "paused" while inactive), and Codex
(weekly quota %) — over a per-session list. One row per Claude Code session
written in the last 30 min (or with usage today) plus the most recent Codex
thread, colored by tool. "active" = a transcript touched within ACTIVE_WINDOW.
"""
from __future__ import annotations

import time

from PIL import Image, ImageDraw, ImageFont

from .stats import SessionInfo, ToolStats

W, H = 320, 480
S = 2  # supersample factor

SURFACE = "#1a1a19"
PANEL = "#242422"
TRACK = "#3a3a37"
DIVIDER = "#2c2c2a"
TEXT = "#ffffff"
TEXT_2 = "#c3c2b7"
TEXT_MUTED = "#84837a"
BLUE = "#3987e5"     # Codex
ORANGE = "#d95926"   # Claude Code (Vertex)
VIOLET = "#9a6ff0"   # Claude Max (subscription)
WARNING = "#fab219"
GOOD = "#0ca30c"
CRITICAL = "#e5484d"
ATTENTION = "#4aa3ff"  # blue "needs you" dot (session awaiting the user)

ACCENTS = {"Claude Code": ORANGE, "Claude Max": VIOLET, "Codex": BLUE}

_FONTS: dict = {}


def font(size: int, mono: bool = False, bold: bool = False) -> ImageFont.FreeTypeFont:
    key = (mono, bold, size)
    if key not in _FONTS:
        if mono:
            f = ImageFont.truetype("/System/Library/Fonts/SFNSMono.ttf", size * S)
        else:
            f = ImageFont.truetype("/System/Library/Fonts/SFNS.ttf", size * S)
            if bold:
                try:
                    f.set_variation_by_name("Bold")
                except OSError:
                    pass
        _FONTS[key] = f
    return _FONTS[key]


def fmt_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}K"
    return str(n)


def _reset_in(epoch: float) -> str:
    secs = max(0, int(epoch - time.time()))
    if secs >= 86400:
        return f"{secs // 86400}d"
    if secs >= 3600:
        return f"{secs // 3600}h"
    return f"{secs // 60}m"


def _ago(epoch: float) -> str:
    if not epoch:
        return ""
    s = int(time.time() - epoch)
    if s < 60:
        return "now"
    if s < 3600:
        return f"{s // 60}m"
    if s < 86400:
        return f"{s // 3600}h"
    return f"{s // 86400}d"


def _truncate(d, s: str, fnt, max_w: int) -> str:
    if d.textlength(s, font=fnt) <= max_w * S:
        return s
    while s and d.textlength(s + "…", font=fnt) > max_w * S:
        s = s[:-1]
    return s + "…"


def sparkline(d, xs, ys, w, h, values, color):
    xs, ys, w, h = xs * S, ys * S, w * S, h * S
    d.line([(xs, ys + h), (xs + w, ys + h)], fill=TRACK, width=S)
    if not values or max(values) <= 0:
        return
    top = max(values)
    n = len(values)
    pts = [(xs + i * w // (n - 1), ys + h - int((v / top) * (h - S * 2)))
           for i, v in enumerate(values)]
    d.line(pts, fill=color, width=S * 2, joint="curve")


def _quota_color(pct: float) -> str:
    return CRITICAL if pct >= 80 else WARNING if pct >= 75 else GOOD


def _bar(d, x, y, w, frac: float, color, h: int = 3):
    d.rounded_rectangle([x * S, y * S, (x + w) * S, (y + h) * S], radius=S, fill=TRACK)
    fw = int(w * max(0.0, min(1.0, frac)))
    if fw > 0:
        d.rounded_rectangle([x * S, y * S, (x + fw) * S, (y + h) * S], radius=S, fill=color)


def _tile(d, x, y, w, h, st: ToolStats, accent: str, label: str):
    """One full-width account row. Identity on the left; hero number + a
    sparkline (cost card) or quota bar (quota card) on the right."""
    d.rounded_rectangle([x * S, y * S, (x + w) * S, (y + h) * S], radius=8 * S, fill=PANEL)
    # left: accent dot + label (top) + sub (bottom)
    d.ellipse([(x + 13) * S, (y + 11) * S, (x + 21) * S, (y + 19) * S], fill=accent)
    d.text(((x + 28) * S, (y + 9) * S),
           _truncate(d, label, font(11, bold=True), w // 2),
           font=font(11, bold=True), fill=TEXT_2)

    # right column: hero (top) + decoration (bottom)
    rx = x + w - 14            # right edge for hero
    dw = 96                    # width of sparkline / quota bar
    dx = x + w - 14 - dw       # left edge of decoration
    hy, dy = y + 8, y + h - 17
    sub_y = y + h - 21

    if st.name == "Claude Code":  # cost card (Vertex, estimated $)
        live_n = sum(1 for s in st.sessions if s.live)
        cost_col = CRITICAL if st.cost_usd >= 200 else TEXT  # over $200/day => red
        d.text((rx * S, hy * S), f"${st.cost_usd:,.2f}",
               font=font(22, bold=True), fill=cost_col, anchor="ra")
        sub = f"{live_n} live · {st.sessions_today} today"
        if st.cost_estimated:
            sub += " · est"
        sparkline(d, dx, dy, dw, 11, st.activity_24h, accent)
    elif st.quota_pct is not None:  # quota card with a reading (Codex, live Max)
        qcol = _quota_color(st.quota_pct)
        d.text((rx * S, hy * S), f"{st.quota_pct:.0f}%",
               font=font(22, bold=True), fill=qcol, anchor="ra")
        reset = f" · {_reset_in(st.quota_resets_at)} left" if st.quota_resets_at else ""
        sub = f"weekly{reset}"
        _bar(d, dx, dy + 4, dw, st.quota_pct / 100.0, qcol, h=5)
    else:  # no metric yet — status note (e.g. "paused")
        d.text((rx * S, (hy + 4) * S), st.note or "—",
               font=font(15, bold=True), fill=TEXT_MUTED, anchor="ra")
        sub = "subscription"
        _bar(d, dx, dy + 4, dw, 0.0, accent, h=5)

    d.text(((x + 28) * S, sub_y * S),
           _truncate(d, sub, font(9), dx - (x + 28) - 8),
           font=font(9), fill=TEXT_MUTED)


def _session_row(d, x, y, w, rh, accent, sess: SessionInfo):
    # left: tool-identity dot (dim when idle)
    d.ellipse([(x + 2) * S, (y + rh // 2 - 4) * S, (x + 10) * S, (y + rh // 2 + 4) * S],
              fill=accent if sess.active else TRACK)
    # name text carries the tool color (orange/violet/blue); turns blue when
    # the session is waiting on the user
    name_col = ATTENTION if sess.needs_input else accent
    label = _truncate(d, sess.label or "session", font(13, bold=True), 150)
    d.text(((x + 18) * S, (y + 3) * S), label, font=font(13, bold=True), fill=name_col)
    model = sess.model.replace("claude-", "")
    if sess.id:
        model = f"{model} · {sess.id}"
    model = _truncate(d, model, font(9, mono=True), 150)
    d.text(((x + 18) * S, (y + 22) * S), model, font=font(9, mono=True), fill=TEXT_MUTED)

    toks = f"{fmt_tokens(sess.tokens_in)}/{fmt_tokens(sess.tokens_out)}"
    d.text(((x + w - 6) * S, (y + 4) * S), toks, font=font(12, mono=True),
           fill=TEXT_2, anchor="ra")
    # right: status — needs-you (blue) > working (green) > idle age (grey)
    if sess.needs_input:
        status = "turn ended" if sess.attention_kind == "idle" else "needs you"
        scol = ATTENTION
    elif sess.live:
        status, scol = "live", GOOD
    else:
        status, scol = _ago(sess.last_active), TEXT_MUTED
    if sess.needs_input or sess.live:
        dot_r = x + w - 6 - int(d.textlength(status, font=font(9)) / S) - 8
        d.ellipse([dot_r * S, (y + 25) * S, (dot_r + 5) * S, (y + 30) * S], fill=scol)
    d.text(((x + w - 6) * S, (y + 23) * S), status, font=font(9), fill=scol, anchor="ra")


def render(stats: list[ToolStats]) -> Image.Image:
    img = Image.new("RGB", (W * S, H * S), SURFACE)
    d = ImageDraw.Draw(img)
    by_name = {s.name: s for s in stats}

    # header
    d.text((10 * S, 8 * S), "CODE DECK", font=font(13, bold=True), fill=TEXT_2)
    src_live = bool(stats) and all(s.live for s in stats)
    d.ellipse([10 * S, 30 * S, 16 * S, 36 * S], fill=GOOD if src_live else WARNING)
    d.text((21 * S, 26 * S), "LIVE" if src_live else "DUMMY DATA",
           font=font(9), fill=TEXT_MUTED)
    now = time.localtime()
    d.text(((W - 10) * S, 6 * S), time.strftime("%H:%M", now),
           font=font(20, mono=True), fill=TEXT, anchor="ra")
    d.text(((W - 10) * S, 30 * S), time.strftime("%a %d %b", now),
           font=font(9), fill=TEXT_MUTED, anchor="ra")

    # summary cards: three full-width account rows
    ty, th, gap, px = 46, 50, 8, 8
    tw = W - 2 * px
    cards = [
        ("Claude Code", "CLAUDE · VTX", ORANGE),
        ("Claude Max", "CLAUDE · MAX", VIOLET),
        ("Codex", "CODEX", BLUE),
    ]
    for i, (name, label, accent) in enumerate(cards):
        if name in by_name:
            _tile(d, px, ty + i * (th + gap), tw, th, by_name[name], accent, label)

    # section label
    sec_y = ty + len(cards) * (th + gap) + 6
    d.text((10 * S, sec_y * S), "SESSIONS", font=font(9, bold=True), fill=TEXT_MUTED)

    # combined session list, active first then most-recent
    rows: list[tuple[str, SessionInfo]] = []
    for st in stats:
        accent = ACCENTS.get(st.name, BLUE)
        for sess in st.sessions:
            rows.append((accent, sess))
    rows.sort(key=lambda r: (r[1].live, r[1].needs_input, r[1].last_active), reverse=True)

    list_top, rh, rgap, footer_y = sec_y + 16, 40, 4, 462
    max_rows = min(5, (footer_y - list_top) // (rh + rgap))
    shown = rows[:max_rows]
    overflow = len(rows) - len(shown)
    if overflow > 0:
        shown = rows[:max_rows - 1]
    lx, lw = 10, W - 20
    for i, (accent, sess) in enumerate(shown):
        ry = list_top + i * (rh + rgap)
        _session_row(d, lx, ry, lw, rh, accent, sess)
        d.line([lx * S, (ry + rh) * S, (lx + lw) * S, (ry + rh) * S], fill=DIVIDER, width=S)
    if overflow > 0:
        ry = list_top + len(shown) * (rh + rgap)
        d.text((lx * S, (ry + 8) * S), f"+{overflow + 1} more sessions",
               font=font(10), fill=TEXT_MUTED)

    # footer
    total_cost = sum(s.cost_usd for s in stats)
    total_tok = sum(s.tokens_in + s.tokens_out for s in stats)
    d.text((10 * S, 466 * S), f"${total_cost:,.2f}", font=font(11, mono=True), fill=TEXT_2)
    d.text((92 * S, 466 * S), f"{fmt_tokens(total_tok)} tok",
           font=font(11, mono=True), fill=TEXT_2)
    d.text(((W - 10) * S, 466 * S), time.strftime("upd %H:%M:%S"),
           font=font(8), fill=TEXT_MUTED, anchor="ra")

    return img.resize((W, H), Image.LANCZOS)


def overlay_needs_you(base: Image.Image, label: str, alpha: float,
                      kind: str = "needs") -> Image.Image:
    """Composite a fading full-screen attention banner over a finished frame.

    alpha in [0,1] scales the whole overlay's opacity (1 = solid, 0 = gone), so
    the caller can push a short sequence of frames to fade it out. Drawn at 2x
    then downscaled for crisp text, composited onto the base with alpha.
    `kind` picks the title: "idle" -> "TURN ENDED", else "NEEDS YOU" (same card,
    same colors).
    """
    a = max(0.0, min(1.0, alpha))
    ov = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    # dim scrim over everything
    d.rectangle([0, 0, W * S, H * S], fill=(10, 10, 9, 165))
    # centered attention card
    cw, ch = 250, 128
    cx, cy = (W - cw) // 2, (H - ch) // 2
    d.rounded_rectangle([cx * S, cy * S, (cx + cw) * S, (cy + ch) * S],
                        radius=16 * S, fill=(36, 36, 34, 255),
                        outline=ATTENTION, width=3 * S)
    d.ellipse([(W // 2 - 5) * S, (cy + 26) * S, (W // 2 + 5) * S, (cy + 36) * S],
              fill=ATTENTION)
    title = "TURN ENDED" if kind == "idle" else "NEEDS YOU"
    d.text((W // 2 * S, (cy + 60) * S), title, font=font(24, bold=True),
           fill=ATTENTION, anchor="mm")
    d.text((W // 2 * S, (cy + 96) * S),
           _truncate(d, label or "session", font(15, bold=True), cw - 28),
           font=font(15, bold=True), fill=TEXT, anchor="mm")
    # fade: scale the whole overlay's alpha channel
    if a < 1.0:
        ov.putalpha(ov.split()[3].point(lambda p: int(p * a)))
    ov = ov.resize((W, H), Image.LANCZOS)
    return Image.alpha_composite(base.convert("RGBA"), ov).convert("RGB")
