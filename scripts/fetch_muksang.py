# -*- coding: utf-8 -*-
"""
1) 가톨릭굿뉴스 '우리들의 묵상/체험' 게시판(menu=4770)에서
   지정한 신부님들의 최근 3일간 글(제목 또는 작성자 기준)을 추출한다.
2) 다음 카페의 신부님별 게시판(DAUM_BOARDS)에서 최근 글을 추출한다.
   조명연·양승국·김경진 신부님은 '빠다킹신부와 새벽을 열며' 카페,
   전삼용 신부님은 '가톨릭 사랑방' 카페에 각자 게시판이 있다.
두 출처를 합쳐 data/muksang.json 으로 저장한다.

GitHub Actions에서 주기적으로 실행됨.
※ 저작권 보호: 본문 전체는 절대 저장/복제하지 않는다.
   제목/작성자/날짜/원문 링크 + 아주 짧은 한 문장 미리보기(최대 42자·15단어)만 저장한다.
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
from bs4 import BeautifulSoup

BASE = "https://maria.catholic.or.kr/mi_pr/missa/"
LIST_URL = BASE + "bbs_list.asp"
MENU = "4770"

# 실제로 공유/저장할 글 링크는 모바일 게시판(bbsm) 경로를 쓴다.
# 공지: 이 페이지는 열릴 때 'error' 알림창을 한 번 띄운다. 굿뉴스 쪽 버그다.
#   본문 스크립트가 댓글을 get_bbs_view_cmt.asp?id=... 로 불러오는데
#   서버는 seq 파라미터를 기대해서(seq=... 로 부르면 200) id 로 부르면
#   www.catholic.or.kr 로 302 보낸다. 그러면 ajax 가 실패하고
#   게시판 자체 스크립트(common_add.js)가 alert('error') 를 띄운다.
#   호출 주소를 그쪽에서 만드므로 우리가 고칠 수는 없다.
# 그래도 이 경로를 쓰는 이유는 모바일에서 글이 크게 보이는 유일한 경로이기 때문이다.
#   /bbs/bbs_view.asp 와 /bbs/bbs_print.asp 는 알림창은 없지만, 모바일로 부르면
#   서버가 viewport 를 initial-scale=0.1 로 내려줘서 글씨가 아주 작게 나온다.
#   maria.catholic.or.kr 도 initial-scale=0.3 이고 같은 알림창이 뜼다.
BBSM_VIEW_URL = "https://bbs.catholic.or.kr/bbsm/bbs_view.asp"

# 추출 대상 신부님 (이름만; '신부님' 유무와 무관하게 매칭)
NAMES = ["김건태", "조욱현", "한상우", "이영근"]

# 목록에서 빼기로 한 신부님. 이 이름이 제목·작성자에 들어 있으면 그 글은 통째로 건너뛴다.
# '이병우 신부님_조욱현 신부님_김건태 신부님 묵상' 처럼 여러 분이 묶인 글도 함께 빠진다.
EXCLUDE_NAMES = ["이병우", "송영진"]


# 다음 카페에서 가져오는 신부님들.
# 굿뉴스 게시판(menu=4770)이 아니라 각 신부님 전용 카페 게시판에서 직접 읽어 온다.
# 모바일 카페(m.cafe.daum.net)는 목록도 본문도 서버에서 만들어 내려주므로
# 로그인이나 자바스크립트 없이 읽을 수 있고, 목록 데이터는 페이지 안의
# articles.push({...}) 자바스크립트 배열에 그대로 들어 있다.
#   cafe  : 카페 주소 id            fldid : 게시판 id
#   priest: 목록에 표시할 신부님 이름  board : 사람이 알아보기 위한 게시판 이름
#   title_from_body: 제목이 인사말뿐이라 쓸모없는 게시판만 True
#                    (제목 자리에 본문 첫 문장 맛보기를 넣는다)
DAUM_BOARDS = [
    {"cafe": "bbadaking", "fldid": "LxKw", "priest": "김경진",
     "board": "김경진 신부 강론", "title_from_body": True},
    {"cafe": "bbadaking", "fldid": "4Zol", "priest": "조명연",
     "board": "새벽을 열며"},
    {"cafe": "bbadaking", "fldid": "LgBn", "priest": "양승국",
     "board": "양승국 신부 강론"},
    {"cafe": "catholicsb", "fldid": "Iir1", "priest": "전삼용",
     "board": "전삼용 요셉 신부님"},
]
DAUM_MAX_POSTS = 5   # 게시판마다 본문(미리보기)까지 확인할 최근 글 수

DAYS = 2          # 최근 3일
                  # 화면에는 index.html 에서 당일자만 골라 보여 준다.
                  # 여기서 여유분을 두는 것은 게시판 작성일과 미사 날짜가
                  # 하루 어긋나는 글을 놓치지 않기 위해서다.
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


DAUM_ARTICLE_RE = re.compile(r"articles\.push\(\{(.*?)\}\);", re.S)


def daum_field(block: str, key: str) -> str:
    """articles.push({...}) 한 덩어리에서 필드 하나를 꺼낸다."""
    m = re.search(key + r'\s*:\s*"([^"]*)"', block)
    if m:
        return m.group(1).strip()
    m = re.search(key + r"\s*:\s*(\d+)", block)
    return m.group(1) if m else ""


def parse_daum_date(elapsed: str, today_str: str) -> str:
    """카페 목록의 작성시간 표기를 YYYY-MM-DD 로 바꾼다.
    지난 글은 '26.08.30', 당일 글은 '2시간 36분 전' 또는 '06:09' 로 내려온다.
    """
    m = re.fullmatch(r"(\d{2})\.(\d{2})\.(\d{2})", (elapsed or "").strip())
    if m:
        yy, mm, dd = (int(x) for x in m.groups())
        return f"20{yy:02d}-{mm:02d}-{dd:02d}"
    return today_str   # '…분 전' / 'HH:MM' → 오늘 올라온 글


WEEKDAY_KO = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5, "일": 6}


def snap_to_weekday(title: str, date_str: str) -> str:
    """제목에 날짜 없이 '수요일'·'주일' 처럼 요일만 있는 게시판을 위한 보정.
    다음날 묵상을 전날 저녁에 올리는 게시판이 많아서, 작성일부터 이틀 안에서
    제목이 가리키는 요일에 해당하는 날짜로 맞춰 준다.
    예) 9월 1일(화)에 올라온 '연중 제22주간 수요일' → 9월 2일
    """
    m = re.search(r"([월화수목금토일])요일", title)
    if m:
        target = WEEKDAY_KO[m.group(1)]
    elif "주일" in title:
        target = 6            # 주일 = 일요일
    else:
        return date_str
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return date_str
    for delta in range(3):
        cand = d + timedelta(days=delta)
        if cand.weekday() == target:
            return cand.strftime("%Y-%m-%d")
    return date_str


def extract_daum_excerpt(html_text: str, skip_title: str = "") -> str:
    """카페 글 본문에서 한 문장 맛보기만 뽑는다. 본문 전체는 저장하지 않는다.
    본문 첫 줄이 제목을 그대로 되풀이하는 게시판이 있어, 그런 줄은 건너뛴다.
    """
    soup = BeautifulSoup(html_text, "html.parser")
    body = soup.find(id="article")
    if body is None:
        return ""

    def squeeze(t):
        return re.sub(r"\s+", "", t)

    skip = squeeze(skip_title)
    lines = [ln.strip() for ln in body.get_text("\n", strip=True).split("\n")]
    while lines and (not lines[0] or (skip and squeeze(lines[0]) and squeeze(lines[0]) in skip)):
        lines.pop(0)
    return truncate_to_excerpt("\n".join(lines))


def fetch_daum_board(session: requests.Session, board: dict, cutoff: str, today_str: str) -> list:
    """다음 카페 게시판 하나에서 최근 글을 가져온다."""
    posts = []
    list_url = f"https://m.cafe.daum.net/{board['cafe']}/{board['fldid']}"
    headers = dict(HEADERS)
    headers["Referer"] = list_url
    try:
        r = session.get(list_url, headers=headers, timeout=30)
        r.raise_for_status()
        r.encoding = "utf-8"      # 카페는 항상 UTF-8로 내려준다
        page = r.text
    except Exception as e:
        print(f"daum list fetch failed ({board['priest']}):", e, file=sys.stderr)
        return posts

    for block in DAUM_ARTICLE_RE.findall(page):
        # 이 게시판 글만 — 목록 위쪽에 붙는 카페 전체 공지는 fldid 가 다르다
        if daum_field(block, "fldid") != board["fldid"]:
            continue
        data_id = daum_field(block, "dataid")
        if not data_id:
            continue
        title = html.unescape(daum_field(block, "title"))
        date_str = parse_daum_date(daum_field(block, "articleElapsedTime"), today_str)
        # 다음날 묵상을 전날 저녁에 올리는 게시판이 많다 — 제목에 날짜가 있으면 그쪽을 쓴다
        mass_date = parse_title_date(title, date_str)
        if mass_date == date_str:
            mass_date = snap_to_weekday(title, date_str)
        if max(mass_date, date_str) < cutoff:
            continue
        posts.append({
            "id": f"daum_{board['cafe']}_{data_id}",
            "title": title,
            "author": daum_field(block, "writerNickname"),
            "date": date_str,
            "url": f"{list_url}/{data_id}",
            "mass_date": mass_date,
            "priest": board["priest"],
            "excerpt": "",
        })

    posts.sort(key=lambda p: (p["date"], p["id"]), reverse=True)
    posts = posts[:DAUM_MAX_POSTS]

    for post in posts:
        snippet = ""
        try:
            art = session.get(post["url"], headers=headers, timeout=20)
            art.raise_for_status()
            art.encoding = "utf-8"
            snippet = extract_daum_excerpt(art.text, post["title"])
        except Exception as e:
            print("daum article fetch failed for", post["url"], ":", e, file=sys.stderr)
        # 김경진 신부님 게시판은 제목이 늘 '김 베드로신부님 ~' 이라 목록에서 아무것도 알려주지
        # 못한다. 그런 게시판만 제목 자리에 첫 문장 맛보기를 넣고, 나머지는 제목을 그대로 두고
        # 미리보기 줄에 넣는다. 인용 분량은 어느 쪽이든 truncate_to_excerpt 한 문장이다.
        if board.get("title_from_body"):
            if snippet:
                post["title"] = snippet
        else:
            post["excerpt"] = snippet
        time.sleep(0.4)   # 카페 서버에 부담을 주지 않도록 간격을 둔다

    return posts


def fetch_daum_posts(session: requests.Session, cutoff: str, today_str: str) -> list:
    """DAUM_BOARDS 에 적힌 게시판을 차례로 돌며 글을 모은다."""
    posts = []
    for board in DAUM_BOARDS:
        posts.extend(fetch_daum_board(session, board, cutoff, today_str))
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

    def is_excluded(r):
        hay = r["title"] + " " + r["author"]
        return any(n in hay for n in EXCLUDE_NAMES)

    posts = []
    for r in all_rows.values():
        r["mass_date"] = parse_title_date(r["title"], r["date"])
        # 필터 기준은 실제 미사 날짜(mass_date)로 판단 — 게시판 작성일과 하루 어긋나는 경우 대응
        if max(r["mass_date"], r["date"]) < cutoff:
            continue
        if is_excluded(r):
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

    # 김경진 베드로 신부님 다음 카페 글을 같은 목록에 합친다.
    daum_posts = fetch_daum_posts(session, cutoff, today_str)
    posts.extend(daum_posts)

    # 정렬 기준(mass_date, id)이 서로 다른 두 소스(숫자 id / "daum_"+숫자)를 섞으므로
    # 문자열 id를 그대로 안전하게 비교할 수 있도록 정렬 키를 다시 통일한다.
    posts.sort(key=lambda r: (max(r["mass_date"], r["date"]), str(r["id"])), reverse=True)

    out = {
        "updated": now.strftime("%Y-%m-%d %H:%M"),
        "cutoff": cutoff,
        "days": DAYS,
        "names": NAMES + [b["priest"] for b in DAUM_BOARDS],
        "source": LIST_URL + "?menu=" + MENU,
        "daum_sources": [f"https://m.cafe.daum.net/{b['cafe']}/{b['fldid']}" for b in DAUM_BOARDS],
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
