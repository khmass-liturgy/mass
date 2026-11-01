# -*- coding: utf-8 -*-
"""
마리아사랑넷 '가톨릭 성가집' 전체 목록(번호·구분·제목·음원·악보 그림)을 읽어
data/holy_songs.json 으로 저장한다.

앱의 성가집 화면(holy_songs.html)은 이 목록을 보여 주고, 사용자가 재생 버튼을
누를 때만 음원을 튼다. 마리아사랑넷의 곡 화면은 열리자마자 음악을 자동 재생해서
(일부 폰에서는 목록을 다시 열 때도 그 곡이 다시 나온다) 앱 안에서 듣게 했다.

성가집 목록은 거의 바뀌지 않으므로 필요할 때 손으로 한 번 실행한다.
"""

import html
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests

BASE = "https://www.mariasarang.net"
LIST_URL = BASE + "/page/catholic.asp"
OUT = Path(__file__).resolve().parent.parent / "data" / "holy_songs.json"

# 데스크톱 화면이라야 한 쪽에 전곡이 다 나온다.
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0 Safari/537.36"),
    "Accept-Language": "ko-KR,ko;q=0.9",
}

ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
CELL_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
MP3_RE = re.compile(r'href="([^"]*/music_catholic/mp3/[^"]+\.mp3)"')
JPG_RE = re.compile(r"DirectJpgView\('([^']+/jpg/[^']+)'")
JPG_M_RE = re.compile(r"DirectJpgView\('([^']+/jpg_m/[^']+)'")


def text(raw: str) -> str:
    t = html.unescape(re.sub(r"<[^>]+>", "", raw))
    return re.sub(r"\s+", " ", t).strip()


def main() -> int:
    try:
        r = requests.get(LIST_URL, headers=HEADERS, timeout=60)
        r.raise_for_status()
        r.encoding = "utf-8"
    except Exception as e:
        print("holy songs fetch failed:", e, file=sys.stderr)
        return 1

    songs, seen = [], set()
    for row in ROW_RE.findall(r.text):
        cells = CELL_RE.findall(row)
        if len(cells) < 3:
            continue
        num = text(cells[0])
        if not num.isdigit() or num in seen:
            continue
        title = text(cells[2])
        if not title:
            continue
        seen.add(num)
        song = {"n": int(num), "k": text(cells[1]), "t": title}
        mp3 = MP3_RE.search(row)
        if mp3:
            song["mp3"] = urljoin(BASE, mp3.group(1))
        j = JPG_RE.search(row)
        jm = JPG_M_RE.search(row)
        if j:
            song["jpg"] = urljoin(BASE, j.group(1))
        if jm:
            song["jpg_m"] = urljoin(BASE, jm.group(1))
        songs.append(song)

    if len(songs) < 100:
        print("too few songs parsed:", len(songs), file=sys.stderr)
        return 1
    songs.sort(key=lambda s: s["n"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="\n") as f:
        json.dump({"source": LIST_URL, "count": len(songs), "songs": songs},
                  f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")
    print("saved:", OUT, len(songs), "songs; first:", songs[0], "last:", songs[-1]["n"], songs[-1]["t"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
