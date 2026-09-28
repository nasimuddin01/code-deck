"""Photos and weather for the Photo / Slideshow / Weather widgets.

Photos come from two places:
  - albums uploaded through the builder, kept in CODE_DECK_HOME/media/<album>/.
    Each upload is turned upright, shrunk to MAX_EDGE and re-saved as JPEG,
    which also drops its EXIF (GPS location included);
  - a file or folder the user names, which must be inside their home folder.
Either way each image is downsized again for its widget before it reaches
headless Chromium, so a 12 MP phone photo costs a few KB and never a full
decode in the page. Resized copies are cached under CODE_DECK_HOME/cache/media.

Weather: fetched server-side from Open-Meteo (free, no API key) so every page
showing the widget shares one cached reading. This is the only outbound
request CODE DECK makes, and only when a Weather widget is on the layout.
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import re
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, Response

from .. import config

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
UNSUPPORTED_EXTS = {".heic", ".heif"}   # iPhone default; Pillow can't read it without pillow-heif
UNSUPPORTED_HINT = "cannot read this image (HEIC? export it as JPEG)"
MAX_LIST = 2000
MAX_EDGE = 1280           # never serve (or store) more than this
MAX_UPLOAD_BYTES = 40 * 1024 * 1024
ALBUM_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _-]{0,39}$")


def media_root() -> Path:
    """Photos the user names must live under here (their home folder)."""
    return Path.home().resolve()


def uploads_dir() -> Path:
    return config.HOME / "media"


def media_cache_dir() -> Path:
    return config.CACHE_DIR / "media"


def _album_dir(album: str) -> Path:
    if not ALBUM_RE.match(album):
        raise HTTPException(400, "album names are letters, digits, spaces, - and _ (max 40)")
    return uploads_dir() / album


def _resolve(path: str) -> Path:
    """Expand ~, resolve symlinks, and refuse anything outside media_root()."""
    if not path.strip():
        raise HTTPException(400, "no path given")
    p = Path(path.strip()).expanduser()
    if not p.is_absolute():
        p = Path.home() / p
    p = p.resolve()
    for root in (media_root(), uploads_dir().resolve()):
        if p == root or root in p.parents:
            return p
    raise HTTPException(403, "only files inside your home folder can be shown")


def _is_image(p: Path) -> bool:
    return p.suffix.lower() in IMAGE_EXTS and not p.name.startswith(".")


def _save_jpeg(im, out: Path) -> None:
    """Write `out` atomically. The temp file gets a unique name, so two
    requests producing the same file at once can't corrupt each other."""
    out.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=out.parent, prefix=".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            im.save(f, "JPEG", quality=90)          # no exif= -> metadata dropped
        os.replace(tmp, out)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


@router.get("/media/list")
def media_list(dir: str = Query("", max_length=1024), album: str = Query("", max_length=40)) -> dict:
    """Image files directly inside `dir` (or uploaded `album`), sorted by name."""
    if album:
        d = _album_dir(album)
        if not d.is_dir():
            return {"dir": str(d), "files": []}
    else:
        d = _resolve(dir)
    if not d.is_dir():
        raise HTTPException(404, "folder not found")
    files = sorted((f for f in d.iterdir() if f.is_file() and _is_image(f)), key=lambda f: f.name.lower())
    return {"dir": str(d), "files": [str(f) for f in files[:MAX_LIST]]}


def _thumb(src: Path, w: int, h: int) -> tuple[Path, str]:
    """A JPEG at least w x h (aspect kept, so object-fit cover still works),
    and its cache key, which changes whenever the source file does."""
    from PIL import Image, ImageOps

    st = src.stat()
    key = hashlib.sha1(f"{src}|{st.st_mtime_ns}|{st.st_size}|{w}x{h}".encode()).hexdigest()
    out = media_cache_dir() / f"{key}.jpg"
    if out.exists():
        return out, key
    with Image.open(src) as im:
        im.seek(0)                                  # first frame of a GIF
        im = ImageOps.exif_transpose(im)            # phone photos: upright
        scale = min(1.0, max(w / im.width, h / im.height))
        if scale < 1.0:
            im = im.resize((max(1, round(im.width * scale)), max(1, round(im.height * scale))),
                           Image.Resampling.LANCZOS)
        _save_jpeg(im.convert("RGB"), out)
    return out, key


@router.get("/media/file")
def media_file(request: Request, path: str = Query(..., max_length=1024),
               w: int = Query(640, ge=16, le=MAX_EDGE),
               h: int = Query(640, ge=16, le=MAX_EDGE)) -> Response:
    p = _resolve(path)
    if p.is_file() and p.suffix.lower() in UNSUPPORTED_EXTS:
        raise HTTPException(415, UNSUPPORTED_HINT)
    if not p.is_file() or not _is_image(p):
        raise HTTPException(404, "image not found")
    try:
        out, key = _thumb(p, w, h)
    except Exception as e:
        log.warning("cannot read image %s: %s", p, e)
        raise HTTPException(415, UNSUPPORTED_HINT) from e
    # the URL doesn't change when the file does, so let the browser revalidate:
    # an unchanged photo costs a 304, a replaced one shows up at once
    etag = f'"{key}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag, "Cache-Control": "no-cache"})
    return FileResponse(out, media_type="image/jpeg", headers={"ETag": etag, "Cache-Control": "no-cache"})


# -- uploads ------------------------------------------------------------------
def _store_upload(album_dir: Path, name: str, data: bytes) -> Path:
    """Validate, orient, shrink and save one uploaded image as JPEG."""
    from PIL import Image, ImageOps
    try:
        with Image.open(io.BytesIO(data)) as im:
            im.seek(0)
            im = ImageOps.exif_transpose(im)
            im.thumbnail((MAX_EDGE, MAX_EDGE), Image.Resampling.LANCZOS)
            im = im.convert("RGB")
    except Exception as e:
        raise HTTPException(415, "not an image this server can read (HEIC? export it as JPEG)") from e
    stem = re.sub(r"[^A-Za-z0-9 _-]+", "", Path(name).stem).strip()[:60] or "photo"
    tag = hashlib.sha1(data).hexdigest()[:8]            # same photo twice = same file
    out = album_dir / f"{stem}-{tag}.jpg"
    _save_jpeg(im, out)
    return out


@router.post("/media/albums/{album}")
async def upload_photo(request: Request, album: str, name: str = Query("photo.jpg", max_length=200)) -> dict:
    """Body = the raw image bytes (one file per request)."""
    d = _album_dir(album)
    try:
        declared = int(request.headers.get("content-length") or 0)
    except ValueError:
        raise HTTPException(400, "bad Content-Length") from None
    if declared > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "photo too large (40 MB max)")
    data = await request.body()
    if not data:
        raise HTTPException(400, "empty upload")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "photo too large (40 MB max)")
    out = await run_in_threadpool(_store_upload, d, name, data)
    return {"album": album, "path": str(out), "name": out.name}


@router.get("/media/albums")
def list_albums() -> dict:
    root = uploads_dir()
    albums = []
    if root.is_dir():
        for d in sorted(root.iterdir(), key=lambda p: p.name.lower()):
            if d.is_dir() and ALBUM_RE.match(d.name):
                albums.append({"name": d.name, "count": sum(1 for f in d.iterdir() if f.is_file() and _is_image(f))})
    return {"albums": albums}


@router.delete("/media/albums/{album}/{name}")
def delete_photo(album: str, name: str) -> dict:
    d = _album_dir(album)
    f = d / Path(name).name                             # no path segments
    if not f.is_file() or not _is_image(f):
        raise HTTPException(404, "photo not found")
    f.unlink()
    return {"deleted": f.name}


# -- weather ------------------------------------------------------------------
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
WEATHER_TTL_S = 600
HTTP_TIMEOUT_S = 8

_lock = threading.Lock()
_geo_cache: dict[str, dict] = {}
_wx_cache: dict[str, tuple[float, dict]] = {}


def _get_json(url: str, params: dict) -> dict:
    req = urllib.request.Request(f"{url}?{urllib.parse.urlencode(params)}",
                                 headers={"User-Agent": "code-deck"})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as r:
        return json.loads(r.read().decode("utf-8"))


def _geocode(city: str) -> dict:
    key = city.strip().lower()
    with _lock:
        if key in _geo_cache:
            return _geo_cache[key]
    # "Dhaka, Bangladesh" -> search "Dhaka", prefer a result matching the rest
    name, _, hint = city.partition(",")
    res = _get_json(GEOCODE_URL, {"name": name.strip(), "count": 10, "language": "en", "format": "json"})
    results = res.get("results") or []
    if not results:
        raise HTTPException(404, f"city not found: {city}")
    hint = hint.strip().lower()
    pick = next((r for r in results if hint and hint in " ".join(
        str(r.get(k, "")) for k in ("country", "country_code", "admin1")).lower()), results[0])
    geo = {"lat": pick["latitude"], "lon": pick["longitude"], "place": pick.get("name", name.strip())}
    with _lock:
        _geo_cache[key] = geo
    return geo


@router.get("/weather")
def weather(city: str = Query("", max_length=120),
            lat: float | None = Query(None, ge=-90, le=90),
            lon: float | None = Query(None, ge=-180, le=180),
            units: str = Query("celsius", pattern="^(celsius|fahrenheit)$")) -> dict:
    if lat is None or lon is None:
        if not city.strip():
            raise HTTPException(400, "set a city or latitude/longitude")
        geo = _geocode(city)
    else:
        geo = {"lat": lat, "lon": lon, "place": city.strip()}
    key = f"{geo['lat']:.3f},{geo['lon']:.3f},{units}"
    now = time.time()
    with _lock:
        hit = _wx_cache.get(key)
        if hit and now - hit[0] < WEATHER_TTL_S:
            return hit[1]
    try:
        raw = _get_json(FORECAST_URL, {
            "latitude": geo["lat"], "longitude": geo["lon"], "timezone": "auto", "forecast_days": 1,
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,"
                       "wind_speed_10m,uv_index,is_day",
            "daily": "temperature_2m_max,temperature_2m_min,uv_index_max",
            "temperature_unit": units,
            "wind_speed_unit": "mph" if units == "fahrenheit" else "kmh",
        })
    except HTTPException:
        raise
    except Exception as e:
        if hit:                      # stale beats blank when offline
            return hit[1]
        raise HTTPException(502, f"weather service unavailable: {e}") from e
    cur, daily = raw.get("current", {}), raw.get("daily", {})

    def first(k: str):
        v = daily.get(k) or [None]
        return v[0]

    out = {
        "place": geo["place"],
        "units": units,
        "temp": cur.get("temperature_2m"),
        "feels_like": cur.get("apparent_temperature"),
        "humidity": cur.get("relative_humidity_2m"),
        "wind": cur.get("wind_speed_10m"),
        "wind_unit": "mph" if units == "fahrenheit" else "km/h",
        "uv": cur.get("uv_index"),
        "uv_max": first("uv_index_max"),
        "code": cur.get("weather_code"),
        "is_day": bool(cur.get("is_day", 1)),
        "high": first("temperature_2m_max"),
        "low": first("temperature_2m_min"),
        "fetched_at": now,
    }
    with _lock:
        _wx_cache[key] = (now, out)
    return out
