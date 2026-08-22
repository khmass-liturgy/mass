# -*- coding: utf-8 -*-
"""
가톨릭프레스 '가스펠툰'(만화로 보는 복음) 연재에서 가장 최근 편을 찾아
data/gospeltoon.json 으로 저장한다.

이 연재는 매일이 아니라 '주간'이다. 매주 그 주 주일 전례(제1독서·복음)를
만화로 풀어내고, 보통 토요일에 다음 날 주일 자로 올라온다.
따라서 항상 '가장 최근 편'을 가리키는 것이 곧 이번 주 편을 가리키는 것이 된다.

수집 방식
---------
1) 목록 페이지(mcode=m96sroz)에서 맨 위 항목의 idx·제목을 얻는다.
2) 그 기사 본문에서 'YYYY년 M월 D일 <전례일> 제1독서' 표기를 찾아
   날짜와 전례일 이름을 뽑는다.

GitHub Actions에서 주기적으로 실행됨.
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

BASE = "https://www.catholicpress.kr"
MCODE = "m96sroz"  # 연재 > 가스펠툰
LIST_URL = f"{BASE}/m/list.php?mcode={MCODE}"

KST = ZoneInfo("Asia/Seoul")
OUT = Path(__file__).resolve().parent.parent / "data" / "gospeltoon.json"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0 Safari/537.36"),
    "Accept-Language": "ko-KR,ko;q=0.9",
}

# 본문 예: '2026년 8월 23일 주일 (연중 제21주일)제1독서 (이사야서 22,19-23)'
#          '2026년 8월 16일 연중 제20주일제1독서 (이사야서 56,1...)'
BODY_DATE_RE = re.compile(
    r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일\s*(.{0,40}?)\s*제\s*1\s*독서"
)


def get(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    return r.text


def latest_from_list(html: str):
    """목록 페이지에서 맨 위(가장 최근) 항목의 (idx, 제목)을 반환한다."""
    start = html.find('class="skin13"')
    if start == -1:
        raise ValueError("목록 영역(skin13)을 찾지 못했습니다 (페이지 구조 변경 가능성)")
    body = html[start:html.find("</ul>", start)]
    for li in body.split("<li>")[1:]:
        m_idx = re.search(r"view\.php\?idx=(\d+)", li)
        if not m_idx:
            continue
        m_title = re.search(r"<strong>(.*?)</strong>", li, re.S)
        title = re.sub(r"<[^>]+>", "", m_title.group(1)).strip() if m_title else ""
        return m_idx.group(1), title
    raise ValueError("목록에서 기사를 찾지 못했습니다")


def date_from_article(html: str):
    """기사 본문에서 (날짜, 전례일 이름)을 뽑는다. 못 찾으면 (None, '')."""
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
    m = BODY_DATE_RE.search(text)
    if not m:
        return None, ""
    y, mo, da, label = m.groups()
    try:
        date_str = f"{int(y):04d}-{int(mo):02d}-{int(da):02d}"
    except ValueError:
        return None, ""
    # '주일 (연중 제21주일)' 처럼 괄호가 있으면 괄호 안쪽을 쓴다.
    inner = re.search(r"\(([^)]{2,40})\)", label)
    label = inner.group(1) if inner else label
    label = label.replace("주일", "주일").strip(" ·-—()")
    return date_str, label


def main():
    now = datetime.now(KST)

    try:
        idx, title = latest_from_list(get(LIST_URL))
    except Exception as e:
        print("목록 수집 실패:", e, file=sys.stderr)
        sys.exit(1)

    url = f"{BASE}/m/view.php?idx={idx}&mcode={MCODE}"
    date_str, label = None, ""
    try:
        date_str, label = date_from_article(get(url))
    except Exception as e:
        print("기사 본문 조회 실패(날짜 없이 진행):", e, file=sys.stderr)

    if not date_str:
        print("본문에서 날짜를 찾지 못했습니다 (제목만 사용)", file=sys.stderr)

    # 제목 앞의 '[가스펠:툰] ' 표지는 카드에서 중복이라 떼어 낸다.
    clean_title = re.sub(r"^\[[^\]]*\]\s*", "", title).strip()

    out = {
        "updated": now.strftime("%Y-%m-%d %H:%M"),
        "source": LIST_URL,
        "idx": idx,
        "date": date_str or "",
        "label": label,
        "title": clean_title or title,
        "url": url,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved -> {OUT}: {out['date']} {out['label']} / {out['title']}")


if __name__ == "__main__":
    main()
