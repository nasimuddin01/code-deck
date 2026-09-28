import pytest
from fastapi.testclient import TestClient
from PIL import Image

from code_deck.server import media
from code_deck.server.app import AppContext, create_app
from code_deck.server.layout import LayoutStore
from code_deck.state.store import StateStore


@pytest.fixture
def client(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / "pics").mkdir(parents=True)
    monkeypatch.setattr(media, "media_root", lambda: home.resolve())
    monkeypatch.setenv("HOME", str(home))      # "~" and Path.home()
    monkeypatch.setattr(media, "media_cache_dir", lambda: tmp_path / "cache")
    monkeypatch.setattr(media, "uploads_dir", lambda: tmp_path / "uploads")   # outside "home", like Docker
    media._geo_cache.clear()
    media._wx_cache.clear()
    ctx = AppContext(store=StateStore(), layouts=LayoutStore(tmp_path / "layout.json"))
    c = TestClient(create_app(ctx))
    c.home = home
    return c


def test_list_only_images_sorted(client):
    pics = client.home / "pics"
    for name in ("b.jpg", "A.png", "notes.txt", ".hidden.jpg"):
        (pics / name).write_bytes(b"x")
    r = client.get("/api/media/list", params={"dir": "~/pics"})
    assert r.status_code == 200
    assert [p.rsplit("/", 1)[1] for p in r.json()["files"]] == ["A.png", "b.jpg"]


def test_paths_outside_home_refused(client, tmp_path):
    outside = tmp_path / "secret.jpg"
    Image.new("RGB", (10, 10)).save(outside)
    assert client.get("/api/media/file", params={"path": str(outside)}).status_code == 403
    assert client.get("/api/media/list", params={"dir": "~/../"}).status_code == 403
    link = client.home / "pics" / "link.jpg"
    link.symlink_to(outside)
    assert client.get("/api/media/file", params={"path": str(link)}).status_code == 403


def test_file_is_downsized_and_upright(client):
    src = client.home / "pics" / "big.jpg"
    im = Image.new("RGB", (4000, 3000), (200, 30, 30))
    exif = im.getexif()
    exif[0x0112] = 6                      # "rotate 90 CW" as phones write it
    im.save(src, exif=exif)
    r = client.get("/api/media/file", params={"path": "~/pics/big.jpg", "w": 600, "h": 300})
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    out = Image.open(__import__("io").BytesIO(r.content))
    assert out.height > out.width         # rotated upright
    assert out.width >= 600 and out.height >= 300 and out.width < 1000   # covers the box, no bigger


def test_non_image_rejected(client):
    (client.home / "pics" / "a.txt").write_text("hi")
    assert client.get("/api/media/file", params={"path": "~/pics/a.txt"}).status_code == 404
    (client.home / "pics" / "broken.jpg").write_bytes(b"not an image")
    assert client.get("/api/media/file", params={"path": "~/pics/broken.jpg"}).status_code == 415


def _jpeg(w=3000, h=2000, gps=True) -> bytes:
    import io
    im = Image.new("RGB", (w, h), (10, 120, 200))
    exif = im.getexif()
    if gps:
        exif[0x8825] = {1: "N", 2: (23.0, 42.0, 0.0)}   # GPSInfo
    buf = io.BytesIO()
    im.save(buf, "JPEG", exif=exif)
    return buf.getvalue()


def test_upload_list_serve_delete(client):
    r = client.post("/api/media/albums/family", params={"name": "Beach Day!.jpeg"}, content=_jpeg())
    assert r.status_code == 200, r.text
    up = r.json()
    assert up["name"].startswith("Beach Day-") and up["name"].endswith(".jpg")
    stored = Image.open(up["path"])
    assert max(stored.size) == media.MAX_EDGE                # shrunk on the way in
    assert 0x8825 not in stored.getexif()                    # GPS location stripped
    # same bytes again -> same file, not a duplicate
    assert client.post("/api/media/albums/family", params={"name": "Beach Day!.jpeg"}, content=_jpeg()).json()["name"] == up["name"]

    files = client.get("/api/media/list", params={"album": "family"}).json()["files"]
    assert files == [up["path"]]
    assert client.get("/api/media/albums").json()["albums"] == [{"name": "family", "count": 1}]
    # served although the uploads folder is outside home
    assert client.get("/api/media/file", params={"path": up["path"]}).status_code == 200

    assert client.delete(f"/api/media/albums/family/{up['name']}").status_code == 200
    assert client.get("/api/media/list", params={"album": "family"}).json()["files"] == []


def test_upload_rejects_bad_input(client):
    assert client.post("/api/media/albums/family", content=b"not an image").status_code == 415
    assert client.post("/api/media/albums/family", content=b"").status_code == 400
    assert client.post("/api/media/albums/..%2Fescape", content=_jpeg(10, 10)).status_code // 100 == 4
    assert client.post("/api/media/albums/fam!ly", content=_jpeg(10, 10)).status_code == 400
    assert client.get("/api/media/list", params={"album": "empty"}).json()["files"] == []
    # the handler itself ignores path segments in a photo name
    outside = client.home / "keep.jpg"
    Image.new("RGB", (4, 4)).save(outside)
    (media.uploads_dir() / "family").mkdir(parents=True, exist_ok=True)
    with pytest.raises(media.HTTPException):
        media.delete_photo("family", f"../../home/{outside.name}")
    assert outside.exists()


def test_upload_refused_from_other_websites(client):
    r = client.post("/api/media/albums/family", content=_jpeg(10, 10), headers={"origin": "https://evil.example"})
    assert r.status_code == 403


def test_weather_geocodes_and_caches(client, monkeypatch):
    calls = []

    def fake(url, params):
        calls.append(url)
        if url == media.GEOCODE_URL:
            return {"results": [{"name": "Dhaka", "latitude": 23.7, "longitude": 90.4, "country": "Bangladesh"}]}
        return {"current": {"temperature_2m": 31.4, "apparent_temperature": 37.9, "relative_humidity_2m": 70,
                            "weather_code": 2, "wind_speed_10m": 9.1, "uv_index": 6.2, "is_day": 1},
                "daily": {"temperature_2m_max": [33.0], "temperature_2m_min": [26.1], "uv_index_max": [9.0]}}

    monkeypatch.setattr(media, "_get_json", fake)
    r = client.get("/api/weather", params={"city": "Dhaka, Bangladesh"})
    assert r.status_code == 200
    wx = r.json()
    assert wx["place"] == "Dhaka" and wx["temp"] == 31.4 and wx["uv"] == 6.2 and wx["high"] == 33.0
    client.get("/api/weather", params={"city": "Dhaka, Bangladesh"})
    assert calls == [media.GEOCODE_URL, media.FORECAST_URL]      # second call fully cached


def test_weather_needs_a_place(client):
    assert client.get("/api/weather").status_code == 400
