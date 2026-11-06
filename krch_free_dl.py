#!/usr/bin/env python3
"""Koroche (krch.tv): скачивает ВСЕ серии всех сериалов из /v1/home в наивысшем качестве.
Файлы: <out>/<Название сериала>/<Название сериала> - S01E01.mp4
Нужно: Python 3.8+, ffmpeg в PATH. Без сторонних библиотек.
Примеры:
python3 krch_free_dl.py
python3 krch_free_dl.py -o D:/Video -n
python3 krch_free_dl.py -s XkwbZBQZ
"""

import argparse, json, os, re, subprocess, sys, time, uuid, urllib.request, urllib.error

API = "https://api.krch.tv/v1"
UA = ("Mozilla/5.0 (Linux; Android 9; SM-N975F Build/PI; wv) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Version/4.0 Chrome/138.0.7204.179 Mobile Safari/537.36")
TOKEN_FILE = os.path.join(os.path.expanduser("~"), ".krch_token")
DEVICE_FILE = os.path.join(os.path.expanduser("~"), ".krch_device")


def http(method, url, token=None, body=None, tries=4):
    hdr = {"accept": "application/json, text/plain, */*", "user-agent": UA}
    data = None
    if token:
        hdr["authorization"] = "Bearer " + token
    if body is not None:
        data = json.dumps(body).encode()
        hdr["Content-Type"] = "application/json"

    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers=hdr, method=method)
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            last = e
            if e.code == 401:
                raise
            if e.code not in (403, 429, 500, 502, 503, 504):
                raise
        except Exception as e:
            last = e
        time.sleep(1 + i)
    raise last


def get_device_id():
    if os.path.exists(DEVICE_FILE):
        did = open(DEVICE_FILE, "r", encoding="utf-8").read().strip()
        if did:
            return did
    did = str(uuid.uuid4())
    with open(DEVICE_FILE, "w", encoding="utf-8") as f:
        f.write(did)
    return did


def get_token(fresh=False):
    if not fresh and os.path.exists(TOKEN_FILE):
        t = open(TOKEN_FILE, "r", encoding="utf-8").read().strip()
        if t:
            return t
    body = {"deviceId": get_device_id()}
    data = json.loads(http("POST", API + "/auth/device", body=body))
    t = data["token"]
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        f.write(t)
    return t


class Api:
    def __init__(self):
        self.token = get_token()

    def get(self, path):
        try:
            return json.loads(http("GET", API + path, self.token))
        except urllib.error.HTTPError as e:
            if e.code != 401:
                raise
            self.token = get_token(fresh=True)
            return json.loads(http("GET", API + path, self.token))


def collect_series(home):
    """Все объекты series из /v1/home, без дублей."""
    out = {}

    def walk(o):
        if isinstance(o, dict):
            s = o.get("series")
            if isinstance(s, dict) and s.get("series_id"):
                out.setdefault(s["series_id"], s)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(home)
    return out


def safe(name):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", name)
    name = re.sub(r"\s+", " ", name).strip().rstrip(".")
    return name or "untitled"


def all_episodes(api, series, delay=1.0):
    sid = series["series_id"]
    total = int(series.get("total_episodes") or series.get("episodes_count") or 0)
    seen = {}

    def add(arr):
        new = 0
        for e in arr:
            eid = e.get("episode_id")
            if eid and eid not in seen:
                seen[eid] = e
                new += 1
        return new

    try:
        data = api.get(f"/series/{sid}/episodes")
    except Exception:
        return []

    add(data.get("episodes") or [])
    page = 2

    while True:
        if total and len(seen) >= total:
            break
        try:
            data = api.get(f"/series/{sid}/episodes?page={page}")
        except urllib.error.HTTPError:
            break
        except Exception:
            break

        arr = data.get("episodes") or []
        if not arr or add(arr) == 0:
            break

        page += 1
        time.sleep(delay)

    return sorted(seen.values(), key=lambda e: int(e.get("episode_number") or 0))


def download(m3u8, dst):
    tmp = dst + ".part.mp4"
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-stats", "-y",
           "-user_agent", UA, "-i", m3u8,
           "-c:v", "copy", "-c:a", "copy", "-c:s", "mov_text",
           "-movflags", "+faststart", tmp]

    r = subprocess.run(cmd)
    if r.returncode != 0:
        cmd2 = [c for c in cmd if c not in ("-c:s", "mov_text") and c != tmp] + ["-sn", tmp]
        r = subprocess.run(cmd2)

    if r.returncode == 0 and os.path.exists(tmp) and os.path.getsize(tmp) > 0:
        os.replace(tmp, dst)
        return True

    if os.path.exists(tmp):
        os.remove(tmp)
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", default="Koroche")
    ap.add_argument("-s", "--series", nargs="*", help="series_id (по умолчанию все)")
    ap.add_argument("-n", "--dry-run", action="store_true")
    ap.add_argument("--delay", type=float, default=1.0, help="пауза между запросами, c")
    a = ap.parse_args()

    if not a.dry_run and subprocess.run(["ffmpeg", "-version"], capture_output=True).returncode:
        sys.exit("ffmpeg не найден в PATH")

    api = Api()
    home = api.get("/home")
    series = collect_series(home)

    if a.series:
        want = set(a.series)
        series = {k: v for k, v in series.items() if k in want}

    ok = skip = fail = 0

    for sid, s in series.items():
        title = safe(s.get("title") or sid)
        folder = os.path.join(a.out, title)

        eps = all_episodes(api, s, a.delay)
        eps = [e for e in eps if e.get("video", {}).get("url")]
        if not eps:
            continue

        width = len(str(max(int(e.get("episode_number") or 0) for e in eps)))
        print(f"{title}: {len(eps)}")

        for e in sorted(eps, key=lambda e: int(e.get("episode_number") or 0)):
            n = int(e.get("episode_number") or 0)
            fn = os.path.join(folder, f"{title} - S01E{n:0{width}d}.mp4")

            if os.path.exists(fn):
                skip += 1
                continue

            print(f" E{n:0{width}d} -> {fn}")
            if a.dry_run:
                continue

            os.makedirs(folder, exist_ok=True)
            if download(e["video"]["url"], fn):
                ok += 1
            else:
                fail += 1
                print(f" !! ошибка: {e['video']['url']}")

            time.sleep(a.delay)

    print(f"Готово: скачано {ok}, пропущено (уже есть) {skip}, ошибок {fail}")


if __name__ == "__main__":
    main()