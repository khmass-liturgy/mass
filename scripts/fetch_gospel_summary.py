# -*- coding: utf-8 -*-
"""
한국천주교주교회의 '매일미사' 페이지(missa.cbck.or.kr)에서 그날 복음의 대표 말씀을 모아
data/gospel_summary.json 으로 저장한다 (초기화면 매일미사 카드의 한 줄 글귀용).

복음 제목 바로 아래에는 그날 복음을 한 줄로 줄인 말씀이 꺾쇠(< >)에 담겨 있다.
  복음
  <주 너의 하느님을 사랑해야 한다. 네 이웃을 너 자신처럼 사랑해야 한다.>
  ✠ 마태오가 전한 거룩한 복음입니다.  22,34-40
이 글귀와 복음서 이름·장절만 가져오고, 복음 본문은 가져오지 않는다.

오늘부터 10일 앞까지 한꺼번에 받아 둔다. 워크플로가 3일에 한 번만 돌기 때문이고,
토요일 오후에는 카드가 주일로 넘어가므로 미리 있어야 하기도 하다. 한 번 실패해도 다음 실행 때까지 남아 있게 하는 여유이기도 하다.

GitHub Actions에서 주기적으로 실행됨.
"""

import html
import json
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

KST = ZoneInfo("Asia/Seoul")
OUT = Path(__file__).resolve().parent.parent / "data" / "gospel_summary.json"
URL = "https://missa.cbck.or.kr/DailyMissa/{}"
DAYS_AHEAD = 10   # 워크플로가 3일에 한 번 돌아도 한 번 건너뛸 여유가 남는 길이

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0 Safari/537.36"),
    "Accept-Language": "ko-KR,ko;q=0.9",
}

SUMMARY_RE = re.compile(r"<h4>\s*복음\s*</h4>\s*<span>(.*?)</span>", re.S)
BOOK_RE = re.compile(r"✠\s*([^<]*?)(?:가|이)\s*전한\s*거룩한\s*복음")
REF_RE = re.compile(r'✠[^<]*복음입니다\.?\s*<h5[^>]*>\s*<span>(.*?)</span>', re.S)
TITLE_RE = re.compile(r"<h2[^>]*>\s*\[[^\]]*\]\s*([^<]+?)\s*</h2>")


def clean(text: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", "", text)).replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def fetch_day(day) -> dict | None:
    r = requests.get(URL.format(day.strftime("%Y%m%d")), headers=HEADERS, timeout=30)
    r.raise_for_status()
    m = SUMMARY_RE.search(r.text)
    if not m:
        return None
    verse = clean(m.group(1)).strip("<>＜＞ ")
    if not verse:
        return None
    book = BOOK_RE.search(r.text)
    ref = REF_RE.search(r.text)
    entry = {"verse": verse}
    if book and ref:
        entry["ref"] = f"{clean(book.group(1))} 복음 {clean(ref.group(1))}"
    return entry


def main() -> int:
    today = datetime.now(KST).date()
    try:
        old = json.loads(OUT.read_text(encoding="utf-8")).get("days", {})
    except (OSError, ValueError):
        old = {}
    days = {k: v for k, v in old.items() if k >= today.isoformat()}

    ok = 0
    for i in range(DAYS_AHEAD + 1):
        day = today + timedelta(days=i)
        try:
            entry = fetch_day(day)
        except Exception as e:
            print(f"  {day} 실패: {e}", file=sys.stderr)
            continue
        if entry:
            days[day.isoformat()] = entry
            ok += 1
        time.sleep(0.5)

    if not days:
        print("gospel summary: 하나도 못 받았습니다", file=sys.stderr)
        return 1

    data = {
        "updated": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "source": "https://missa.cbck.or.kr/DailyMissa",
        "days": dict(sorted(days.items())),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"saved: {OUT} ({ok}일 새로 받음, 총 {len(days)}일)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
