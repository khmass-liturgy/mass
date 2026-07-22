# -*- coding: utf-8 -*-
"""
1) 가톨릭굿뉴스 '우리들의 묵상/체험' 게시판(menu=4770)에서
   지정한 신부님들의 최근 3일간 글(제목 또는 작성자 기준)을 추출한다.
2) 송영진 신부님의 네이버 블로그 RSS에서 최근 글을 추출한다.
두 출처를 합쳐 data/muksang.json 으로 저장한다.

GitHub Actions에서 주기적으로 실행됨.
※ 저작권 보호: 본문 전체는 절대 저장/복제하지 않는다.
   제목/작성자/날짜/원문 링크 + 아주 짧은 한 문장 미리보기(최대 42자·15단어)만 저장한다.
"""

import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

BASE = "https://maria.catholic.or.kr/mi_pr/missa/"
LIST_URL = BASE + "bbs_list.asp"
MENU = "4770"

# 실제로 공유/저장할 글 링크는 bbsm 경로를 쓴다.
# (같은 글이라도 bbsm 경로로 들어가면 글씨가 크게 나와 가독성이 더 좋다)
BBSM_VIEW_URL = "https://bbs.catholic.or.kr/bbsm/bbs_view.asp"

# 추출 대상 신부님 (이름만; '신부님' 유무와 무관하게 매칭)
NAMES = ["조명연", "이병우", "김건태", "조욱현", "한상우", "양승국", "이영근", "전삼용"]

# 송영진 신부님 네이버 블로그
NAVER_BLOG_ID = "syj1212ad"
NAVER_RSS_URL = f"https://rss.blog.naver.com/{NAVER_BLOG_ID}.xml"
NAVER_PRIEST_NAME = "송영진"

DAYS = 2          # 최근 3일
MAX_PAGES = 8     # 안전 상한 (페이지당 약 30여 건)

# 미리보기(스니펫) 길이 제한 — 저작권 보호를 위해 아주 짧게만 노출한다.
# 본문 전체나 문단 단위가 아니라 '한 문장 정도의 맛보기'만 허용.
EXCERPT_MAX_CHARS = 42
EXCERPT_MAX_WORDS = 15

KST = ZoneInfo("Asia/Seoul")
OUT = Path(__file__).resolve().parent.parent / "data" / "muksang.json"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0 Safari/537.36"),
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": LIST_URL + "?menu=" + MENU,
}


def get_html(session: requests.Session, url: str, params: dict) -> str:
    r = session.get(url, params=params, headers=HEADERS, timeout=30)
    r.raise_for_status()
    if not r.encoding or r.encoding.lower() in ("iso-8859-1",):
        r.encoding = r.apparent_encoding or "utf-8"
    return r.text


def truncate_to_excerpt(text: str) -> str:
    """긴 텍스트에서 아주 짧은 '한 문장 맛보기'만 남긴다.
    저작권 보호를 위해 글자 수/단어 수 상한을 강하게 건다.
    """
    text = (text or "").strip()
    if not text:
        return ""

    # 첫 문단, 첫 문장 정도만 취함
    first_chunk = re.split(r"\n\s*\n", text)[0]
    # 문장 끝(. ! ? 또는 한글 종결) 기준으로 첫 문장만
    m = re.search(r"^(.{5,}?[\.!\?])(\s|$)", first_chunk)
    sentence = m.group(1) if m else first_chunk

    words = sentence.split()
    truncated = False
    if len(words) > EXCERPT_MAX_WORDS:
        sentence = " ".join(words[:EXCERPT_MAX_WORDS])
        truncated = True
    if len(sentence) > EXCERPT_MAX_CHARS:
        sentence = sentence[:EXCERPT_MAX_CHARS]
        truncated = True

    sentence = sentence.strip()
    if truncated or not sentence.endswith((".", "!", "?")):
        sentence = sentence.rstrip(".!?") + "…"
    return sentence


def extract_excerpt(html: str) -> str:
    """게시글 본문에서 아주 짧은 미리보기 한 조각만 뽑아낸다.
    저작권 보호를 위해 절대 문단 전체를 옮기지 않고,
    truncate_to_excerpt()로 '한 문장 맛보기' 수준으로만 반환한다.
    """
    soup = BeautifulSoup(html, "html.parser")

    # 후보 텍스트 블록: td 중 텍스트가 충분히 길고, 메뉴성 링크가 적은 곳
    candidates = []
    for td in soup.find_all("td"):
        text = td.get_text("\n", strip=True)
        if len(text) < 80:
            continue
        link_count = len(td.find_all("a"))
        if link_count > 5:
            continue
        candidates.append(text)

    if not candidates:
        # td 구조가 아니면 div/p에서도 시도
        for tag in soup.find_all(["div", "p"]):
            text = tag.get_text("\n", strip=True)
            if len(text) >= 80:
                candidates.append(text)

    if not candidates:
        return ""

    # 가장 긴 텍스트 블록을 본문으로 간주
    body = max(candidates, key=len)
    return truncate_to_excerpt(body)


def fetch_excerpt_safely(session: requests.Session, url: str) -> str:
    try:
        html = session.get(url, headers=HEADERS, timeout=20).text
        return extract_excerpt(html)
    except Exception as e:
        print("excerpt fetch failed for", url, ":", e, file=sys.stderr)
        return ""


def fetch_naver_posts(session: requests.Session, cutoff: str, today_str: str) -> list:
    """송영진 신부님 네이버 블로그 RSS에서 최근 글을 가져온다.
    본문 전체는 절대 가져오지 않고, RSS description에서 짧은 미리보기만 추출한다.
    """
    posts = []
    try:
        r = session.get(NAVER_RSS_URL, headers=HEADERS, timeout=20)
        r.raise_for_status()
        root = ET.fromstring(r.content)
    except Exception as e:
        print("naver rss fetch failed:", e, file=sys.stderr)
        return posts

    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date_raw = (item.findtext("pubDate") or "").strip()
        desc_raw = item.findtext("description") or ""
        if not title or not link:
            continue

        # pubDate 예: "Wed, 22 Jul 2026 07:00:00 +0900"
        dt = None
        try:
            dt = datetime.strptime(pub_date_raw[:25].strip(), "%a, %d %b %Y %H:%M:%S")
        except Exception:
            pass
        date_str = dt.strftime("%Y-%m-%d") if dt else today_str

        mass_date = parse_title_date(title, date_str)
        if max(mass_date, date_str) < cutoff:
            continue

        # description은 HTML 미리보기인 경우가 많음 — 태그 제거 후 아주 짧게만 사용
        desc_text = BeautifulSoup(desc_raw, "html.parser").get_text(" ", strip=True)
        excerpt = truncate_to_excerpt(desc_text)

        m_id = re.search(r"/(\d+)\s*$", link)
        post_id = "naver_" + (m_id.group(1) if m_id else str(abs(hash(link))))

        posts.append({
            "id": post_id,
            "title": title,
            "author": "",
            "date": date_str,
            "url": link,
            "mass_date": mass_date,
            "priest": NAVER_PRIEST_NAME,
            "excerpt": excerpt,
        })

    return posts


def parse_title_date(title: str, fallback_date: str) -> str:
    """제목에 적힌 '7월 7일' 같은 실제 미사 날짜를 뽑아 YYYY-MM-DD로 반환.
    이 게시판은 다음날 묵상을 전날 저녁에 미리 올리는 경우가 많아서,
    게시판 '작성일'과 실제 미사 날짜가 하루 어긋나는 일이 흔하다.
    제목에서 날짜를 못 찾으면 작성일(fallback_date)을 그대로 쓴다.
    """
    year = fallback_date.split("-")[0] if fallback_date else str(datetime.now().year)
    patterns = [
        r"(\d{1,2})\s*월\s*(\d{1,2})\s*일",   # 7월 7일
        r"\((\d{1,2})\s*/\s*(\d{1,2})\)",       # (7/6)
        r"\b(\d{1,2})\.(\d{1,2})\b(?!\d)",       # 07.06 / 7.6
        r"\b(\d{1,2})/(\d{1,2})\b(?!\d)",        # 07/06 / 7/6 (괄호 없이)
    ]
    for pat in patterns:
        m = re.search(pat, title)
        if m:
            mo, da = int(m.group(1)), int(m.group(2))
            if 1 <= mo <= 12 and 1 <= da <= 31:
                try:
                    datetime(int(year), mo, da)  # 유효한 날짜인지 검증
                except ValueError:
                    continue
                return f"{year}-{mo:02d}-{da:02d}"
    return fallback_date


def parse_rows(html: str, today_str: str):
    """목록 페이지에서 (num, id, title, date, author) 행을 추출.
    오늘 올라온 글은 게시판에 날짜(YYYY-MM-DD) 대신 '13:22' 같은 시간만
    표시되는 경우가 많아서, 그 경우 today_str(오늘 날짜)로 채워준다.
    """
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for a in soup.select('a[href*="bbs_view.asp"]'):
        href = a.get("href", "")
        m_id = re.search(r"[?&]id=(\d+)", href)
        if not m_id:
            continue
        tr = a.find_parent("tr")
        if tr is None:
            continue
        tds = tr.find_all("td")
        if len(tds) < 4:
            continue
        texts = [td.get_text(" ", strip=True) for td in tds]
        # 날짜 셀 찾기: 'YYYY-MM-DD' 형식, 또는 오늘 글이면 'HH:MM' 시간 형식
        date_str = None
        date_idx = None
        for i, t in enumerate(texts):
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", t):
                date_str = t
                date_idx = i
                break
            if re.fullmatch(r"\d{1,2}:\d{2}", t):
                date_str = today_str
                date_idx = i
                break
        if date_str is None:
            continue
        title = a.get_text(" ", strip=True)
        # 작성자: 날짜 바로 다음 셀
        author = texts[date_idx + 1] if date_idx + 1 < len(texts) else ""
        # 공개 링크는 bbsm 경로(글씨 크게 보이는 버전)로 구성한다. id·menu만 있으면 충분하다.
        url = f"{BBSM_VIEW_URL}?id={m_id.group(1)}&menu={MENU}"
        rows.append({
            "id": m_id.group(1),
            "title": title,
            "author": author,
            "date": date_str,
            "url": url,
        })
    return rows


def main():
    now = datetime.now(KST)
    today_str = now.strftime("%Y-%m-%d")
    cutoff = (now - timedelta(days=DAYS - 1)).strftime("%Y-%m-%d")  # 오늘 포함 3일

    session = requests.Session()
    # 세션 확립: 파라미터 없이 기본 목록을 먼저 요청 (세션 없이는 옛 페이지로 리다이렉트되는 경우가 있음)
    all_rows = {}
    try:
        first = get_html(session, LIST_URL, {"menu": MENU})
        for r in parse_rows(first, today_str):
            all_rows[r["id"]] = r
    except Exception as e:
        print("first page fetch failed:", e, file=sys.stderr)

    stop = False
    for page in range(1, MAX_PAGES + 1):
        if stop:
            break
        try:
            html = get_html(session, LIST_URL, {"menu": MENU, "Page": str(page), "SORT": "W"})
        except Exception as e:
            print(f"page {page} fetch failed:", e, file=sys.stderr)
            continue
        rows = parse_rows(html, today_str)
        if not rows:
            continue
        dates = [r["date"] for r in rows]
        # 이 페이지 전체가 기준일보다 오래됐으면 이후 페이지는 볼 필요 없음
        if max(dates) < cutoff:
            stop = True
        for r in rows:
            all_rows[r["id"]] = r

    # 최근 3일 + 이름 필터 (제목 또는 작성자에 이름 포함)
    def matched_names(r):
        hay = r["title"] + " " + r["author"]
        return [n for n in NAMES if n in hay]

    posts = []
    for r in all_rows.values():
        r["mass_date"] = parse_title_date(r["title"], r["date"])
        # 필터 기준은 실제 미사 날짜(mass_date)로 판단 — 게시판 작성일과 하루 어긋나는 경우 대응
        if max(r["mass_date"], r["date"]) < cutoff:
            continue
        names = matched_names(r)
        if not names:
            continue
        r["priest"] = names[0]
        posts.append(r)

    posts.sort(key=lambda r: (max(r["mass_date"], r["date"]), int(r["id"])), reverse=True)

    # 짧은 미리보기(스니펫)만 가져온다 — 본문 전체를 저장/복제하지 않는다.
    for r in posts:
        r["excerpt"] = fetch_excerpt_safely(session, r["url"])
        time.sleep(0.4)  # 대상 서버에 부담을 주지 않도록 살짝 간격을 둠

    # 송영진 신부님 네이버 블로그 글을 같은 목록에 합친다.
    naver_posts = fetch_naver_posts(session, cutoff, today_str)
    posts.extend(naver_posts)

    # 정렬 기준(mass_date, id)이 서로 다른 두 소스(숫자 id / "naver_"+숫자)를 섞으므로
    # 문자열 id를 그대로 안전하게 비교할 수 있도록 정렬 키를 다시 통일한다.
    posts.sort(key=lambda r: (max(r["mass_date"], r["date"]), str(r["id"])), reverse=True)

    out = {
        "updated": now.strftime("%Y-%m-%d %H:%M"),
        "cutoff": cutoff,
        "days": DAYS,
        "names": NAMES + [NAVER_PRIEST_NAME],
        "source": LIST_URL + "?menu=" + MENU,
        "naver_source": NAVER_RSS_URL,
        "count": len(posts),
        "posts": posts,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved {len(posts)} posts (cutoff {cutoff}) -> {OUT}")

    # 수집 자체가 실패한 경우(행이 하나도 없음) 워크플로우가 알 수 있게 실패 처리
    if not all_rows:
        sys.exit(1)


if __name__ == "__main__":
    main()
