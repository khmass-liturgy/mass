// ── 전례력 공용 계산 라이브러리 (mass 프로젝트가 원본, liturgy 프로젝트가 함께 사용) ──
// 순수 날짜 계산만 담당하며 외부 데이터나 fetch에 의존하지 않는다.
// GitHub Pages가 정적 파일에 Access-Control-Allow-Origin: * 를 붙여주므로
// 다른 오리진(예: khmass-liturgy.github.io/liturgy/)에서도 <script src>로 그대로 불러 쓸 수 있다.
// 이 파일을 고치면 mass, liturgy 두 사이트 모두에 반영된다 — 한 곳만 고치면 된다.

// ── 한국 시간(KST)으로 '지금'을 읽는 공용 헬퍼 ──────────────────
// 날짜·요일 판단은 기기 시간대가 아니라 언제나 한국 시간을 기준으로 한다.
// 주의: 반환값 date 는 '실제 순간'이 아니라 한국 날짜를 로컬 성분으로 담은 자정 Date 다.
//       toLocaleDateString(..., {timeZone:'Asia/Seoul'}) 에 다시 넣으면 이중 변환이 된다.
window.kstNow = function (at) {
  const d = at || new Date();
  const k = new Date(d.getTime() + 9 * 3600000); // UTC+9 로 옮겨 UTC 게터로 읽는다
  return {
    year: k.getUTCFullYear(), month: k.getUTCMonth(), day: k.getUTCDate(),
    dow: k.getUTCDay(), hour: k.getUTCHours(), minute: k.getUTCMinutes(),
    date: new Date(k.getUTCFullYear(), k.getUTCMonth(), k.getUTCDate())
  };
};

// ── 전례력 공용 계산 (전례등급 배지 · 다가오는 대축일 카드가 함께 쓴다) ──
// 대축일 목록을 한 곳에만 두어 여러 사이트/기능이 서로 어긋나지 않게 한다.
window.Liturgy = (function () {
  const DAY = 86400000;
  const addDays = (d, n) => new Date(d.getTime() + n * DAY);
  const ymd = (y, m, d) => new Date(y, m - 1, d); // m: 1-12
  const sundayOnOrBefore = d => addDays(d, -d.getDay());

  // 그레고리력 부활 계산 (Anonymous/Meeus 알고리즘)
  function computeEaster(year) {
    const a = year % 19;
    const b = Math.floor(year / 100), c = year % 100;
    const d = Math.floor(b / 4), e = b % 4;
    const f = Math.floor((b + 8) / 25);
    const g = Math.floor((b - f + 1) / 3);
    const h = (19 * a + b - d - g + 15) % 30;
    const i = Math.floor(c / 4), k = c % 4;
    const l = (32 + 2 * e + 2 * i - h - k) % 7;
    const m = Math.floor((a + 11 * h + 22 * l) / 451);
    const month = Math.floor((h + l - 7 * m + 114) / 31);
    const day = ((h + l - 7 * m + 114) % 31) + 1;
    return new Date(year, month - 1, day);
  }

  // 고정 날짜 대축일 (한국 교회 전례력 포함)
  const FIXED_SOLEMNITIES = {
    '01-01': '천주의 성모 마리아 대축일',
    '03-19': '성 요셉 대축일',
    '03-25': '주님 탄생 예고 대축일',
    '06-24': '성 요한 세례자 탄생 대축일',
    '06-29': '성 베드로와 성 바오로 사도 대축일',
    '08-15': '성모 승천 대축일',
    '09-20': '성 김대건 안드레아 사제와 성 정하상 바오로와 동료 순교자 대축일',
    '11-01': '모든 성인 대축일',
    '12-08': '원죄 없이 잉태되신 성모 마리아 대축일',
    '12-25': '주님 성탄 대축일'
  };

  // 공현 대축일: 1월 2일~8일 사이의 주일 (한국 이동 규정)
  function epiphanySunday(y) {
    let d = ymd(y, 1, 2);
    while (d.getDay() !== 0) d = addDays(d, 1);
    return d;
  }

  /* 해당 연도의 대축일 전체를 날짜순으로 돌려준다. [{date, name}] */
  function solemnitiesOf(year) {
    const easter = computeEaster(year);
    const advent1 = addDays(sundayOnOrBefore(ymd(year, 12, 24)), -21);
    const list = [
      { date: epiphanySunday(year), name: '주님 공현 대축일' },
      { date: easter, name: '주님 부활 대축일' },
      { date: addDays(easter, 42), name: '주님 승천 대축일' }, // 한국: 부활 제7주일
      { date: addDays(easter, 49), name: '성령 강림 대축일' },
      { date: addDays(easter, 56), name: '삼위일체 대축일' },
      { date: addDays(easter, 63), name: '그리스도의 성체 성혈 대축일' }, // 한국: 삼위일체 다음 주일
      { date: addDays(easter, 68), name: '예수 성심 대축일' },
      { date: addDays(advent1, -7), name: '그리스도 왕 대축일' } // 연중 제34주일
    ];
    Object.keys(FIXED_SOLEMNITIES).forEach(function (k) {
      const p = k.split('-');
      list.push({ date: ymd(year, parseInt(p[0], 10), parseInt(p[1], 10)), name: FIXED_SOLEMNITIES[k] });
    });
    list.sort((a, b) => a.date - b.date);
    return list;
  }

  // ── 전례 시기(절기) ──
  // 한 전례주년은 대림 → 성탄 → 연중(전반) → 사순 → 파스카 성삼일 → 부활 → 연중(후반) 순으로 이어진다.
  const SEASON_INFO = {
    advent: { name: '대림 시기', color: '자주색', dot: 'purple' },
    christmas: { name: '성탄 시기', color: '백색', dot: 'white' },
    ordinary: { name: '연중 시기', color: '녹색', dot: 'green' },
    lent: { name: '사순 시기', color: '자주색', dot: 'purple' },
    triduum: { name: '파스카 성삼일', color: '백색·홍색', dot: 'red' },
    easter: { name: '부활 시기', color: '백색', dot: 'white' }
  };

  /* 주님 세례 축일: 공현 대축일이 1/7·1/8이면 그 다음 날, 아니면 공현 다음 주일 */
  function baptismOfLord(year) {
    const e = epiphanySunday(year);
    return (e.getDate() === 7 || e.getDate() === 8) ? addDays(e, 1) : addDays(e, 7);
  }

  /* 해당 연도에 시작하는 시기들의 시작일 목록 (날짜순) */
  function seasonStartsOf(year) {
    const easter = computeEaster(year);
    const advent1 = addDays(sundayOnOrBefore(ymd(year, 12, 24)), -21);
    return [
      { start: addDays(baptismOfLord(year), 1), key: 'ordinary' }, // 주님 세례 축일 다음 날
      { start: addDays(easter, -46), key: 'lent' }, // 재의 수요일
      { start: addDays(easter, -3), key: 'triduum' }, // 주님 만찬 성목요일
      { start: easter, key: 'easter' }, // 주님 부활 대축일
      { start: addDays(easter, 50), key: 'ordinary' }, // 성령 강림 대축일 다음 날
      { start: advent1, key: 'advent' }, // 대림 제1주일
      { start: ymd(year, 12, 25), key: 'christmas' } // 주님 성탄 대축일
    ];
  }

  /* 앞뒤 해까지 이어 붙인 시기 연표 — 시기의 시작일과 마지막 날을 함께 담는다 */
  function seasonTimeline(year) {
    const list = seasonStartsOf(year - 1)
      .concat(seasonStartsOf(year), seasonStartsOf(year + 1))
      .sort(function (a, b) { return a.start - b.start; });
    return list.map(function (it, i) {
      const info = SEASON_INFO[it.key];
      return {
        key: it.key, name: info.name, color: info.color, dot: info.dot,
        start: it.start,
        end: i + 1 < list.length ? addDays(list[i + 1].start, -1) : null
      };
    });
  }

  const midnight = d => new Date(d.getFullYear(), d.getMonth(), d.getDate());

  /* 그 날이 속한 전례 시기 */
  function seasonAt(date) {
    const day = midnight(date);
    const list = seasonTimeline(day.getFullYear());
    let cur = null;
    for (let i = 0; i < list.length; i++) {
      if (list[i].start <= day) cur = list[i]; else break;
    }
    return cur;
  }

  /* 그 날 다음에 시작하는 전례 시기 */
  function nextSeasonAfter(date) {
    const day = midnight(date);
    const list = seasonTimeline(day.getFullYear());
    for (let i = 0; i < list.length; i++) {
      if (list[i].start > day) return list[i];
    }
    return null;
  }

  return {
    computeEaster: computeEaster,
    FIXED_SOLEMNITIES: FIXED_SOLEMNITIES,
    solemnitiesOf: solemnitiesOf,
    seasonAt: seasonAt,
    nextSeasonAfter: nextSeasonAfter
  };
})();

// ── 24절기 계산 ──────────────────────────────────────────────
window.SolarTerms = (function () {
  const NAMES = ['입춘', '우수', '경칩', '춘분', '청명', '곡우', '입하', '소만', '망종', '하지', '소서', '대서',
    '입추', '처서', '백로', '추분', '한로', '상강', '입동', '소설', '대설', '동지', '소한', '대한'];
  const MEANINGS = {
    '입춘': ['立春', '봄이 시작되는 절기'],
    '우수': ['雨水', '눈이 녹아 비가 되고 초목이 싹트는 때'],
    '경칩': ['驚蟄', '겨울잠 자던 개구리와 벌레가 깨어나는 때'],
    '춘분': ['春分', '낮과 밤의 길이가 같아지는 날'],
    '청명': ['淸明', '하늘이 맑아지고 본격적으로 농사를 시작하는 때'],
    '곡우': ['穀雨', '곡식을 자라게 하는 봄비가 내리는 때'],
    '입하': ['立夏', '여름이 시작되는 절기'],
    '소만': ['小滿', '햇볕이 풍부해 만물이 자라 가득 차는 때'],
    '망종': ['芒種', '보리를 거두고 모를 심는 때'],
    '하지': ['夏至', '한 해 중 낮이 가장 긴 날'],
    '소서': ['小暑', '더위가 본격적으로 시작되는 때'],
    '대서': ['大暑', '한 해 중 가장 무더운 때'],
    '입추': ['立秋', '가을이 시작되는 절기'],
    '처서': ['處暑', '더위가 물러가고 아침저녁으로 선선해지는 때'],
    '백로': ['白露', '밤 기온이 내려가 이슬이 맺히기 시작하는 때'],
    '추분': ['秋分', '낮과 밤의 길이가 같아지고 가을이 깊어지는 날'],
    '한로': ['寒露', '찬 이슬이 맺히고 단풍이 짙어지는 때'],
    '상강': ['霜降', '서리가 내리기 시작하는 때'],
    '입동': ['立冬', '겨울이 시작되는 절기'],
    '소설': ['小雪', '첫눈이 내리기 시작하는 때'],
    '대설': ['大雪', '한 해 중 눈이 가장 많이 내린다는 때'],
    '동지': ['冬至', '한 해 중 밤이 가장 긴 날 · 팥죽을 먹는다'],
    '소한': ['小寒', '겨울 추위가 매서워지는 때'],
    '대한': ['大寒', '큰 추위라는 뜻으로 겨울의 마지막 절기']
  };
  const DEG_PER_DAY = 0.98565;
  const lonOf = i => (315 + 15 * i) % 360;
  const jdOf = d => d.getTime() / 86400000 + 2440587.5;
  const dateOf = jd => new Date((jd - 2440587.5) * 86400000);

  function sunLongitude(jd) {
    const T = (jd - 2451545.0) / 36525;
    const L0 = 280.46646 + 36000.76983 * T + 0.0003032 * T * T;
    const M = 357.52911 + 35999.05029 * T - 0.0001537 * T * T;
    const Mr = M * Math.PI / 180;
    const C = (1.914602 - 0.004817 * T - 0.000014 * T * T) * Math.sin(Mr)
      + (0.019993 - 0.000101 * T) * Math.sin(2 * Mr)
      + 0.000289 * Math.sin(3 * Mr);
    const omega = (125.04 - 1934.136 * T) * Math.PI / 180;
    const lam = L0 + C - 0.00569 - 0.00478 * Math.sin(omega);
    return ((lam % 360) + 360) % 360;
  }

  function refine(jd, target) {
    for (let i = 0; i < 8; i++) {
      const d = ((target - sunLongitude(jd) + 540) % 360) - 180;
      jd += d / DEG_PER_DAY;
      if (Math.abs(d) < 1e-6) break;
    }
    return dateOf(jd);
  }
  const indexAt = lon => Math.floor(((((lon - 315) % 360) + 360) % 360) / 15);

  function current(date) {
    const jd = jdOf(date), lon = sunLongitude(jd), i = indexAt(lon);
    const target = lonOf(i);
    const back = (((lon - target) % 360) + 360) % 360;
    return { name: NAMES[i], date: refine(jd - back / DEG_PER_DAY, target) };
  }

  function next(date) {
    const jd = jdOf(date), lon = sunLongitude(jd);
    const i = (indexAt(lon) + 1) % 24;
    const target = lonOf(i);
    let fwd = (((target - lon) % 360) + 360) % 360;
    if (fwd < 1e-9) fwd = 15;
    return { name: NAMES[i], date: refine(jd + fwd / DEG_PER_DAY, target) };
  }

  function meaningOf(name) {
    const m = MEANINGS[name];
    return m ? { hanja: m[0], text: m[1] } : null;
  }

  return { NAMES: NAMES, current: current, next: next, meaningOf: meaningOf, sunLongitude: sunLongitude };
})();
