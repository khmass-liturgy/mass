// 교하성당 가톨릭 뉴스 포털 — 서비스 워커
// 네트워크 우선(신선한 콘텐츠 우선) + 실패 시 캐시로 대체하는 전략
// 매일미사·묵상글·축일 등 자주 바뀌는 콘텐츠 특성에 맞춤

const CACHE_NAME = 'khmass-liturgy-v1';

// 설치 시 미리 담아둘 핵심 파일 (오프라인 최소 보장)
const PRECACHE_URLS = [
  './',
  './index.html',
  './feastday.html',
  './feast_days.json',
  './manifest.json'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(PRECACHE_URLS))
      .catch(() => {}) // 프리캐시 실패해도 설치는 계속 진행
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const req = event.request;

  // GET 요청만 처리 (POST 등은 그대로 통과)
  if (req.method !== 'GET') return;

  // 외부 도메인(구글 캘린더, 가톨릭굿뉴스 등)은 서비스 워커가 관여하지 않고 그대로 통과
  if (new URL(req.url).origin !== self.location.origin) return;

  event.respondWith(
    fetch(req)
      .then((response) => {
        // 성공하면 최신 응답을 캐시에 갱신 저장
        const resClone = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(req, resClone));
        return response;
      })
      .catch(() =>
        // 네트워크 실패(오프라인) 시 캐시에서 대체
        caches.match(req).then((cached) => cached || caches.match('./index.html'))
      )
  );
});
