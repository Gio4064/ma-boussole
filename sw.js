const C='boussole-v4',F=['./','index.html','manifest.webmanifest','icons/logo.svg','icons/icon-192.png','icons/icon-512.png','img/fond-clair.svg','img/fond-sombre.svg'];
self.addEventListener('install',e=>{self.skipWaiting();e.waitUntil(caches.open(C).then(c=>c.addAll(F)))});
self.addEventListener('activate',e=>{e.waitUntil(Promise.all([caches.keys().then(k=>Promise.all(k.filter(x=>x!==C).map(x=>caches.delete(x)))),self.clients.claim()]))});
self.addEventListener('fetch',e=>{const req=e.request;if(req.method!=='GET')return;const url=new URL(req.url);
if(url.origin!==self.location.origin)return; // les requêtes externes (API, annuaires) ne passent jamais par le cache
const isHtml=req.mode==='navigate'||(req.headers.get('accept')||'').includes('text/html');
if(isHtml){e.respondWith(fetch(req).then(r=>{if(r.ok&&r.type==='basic'){const rc=r.clone();caches.open(C).then(c=>c.put(req,rc))}return r}).catch(()=>caches.match(req).then(r=>r||caches.match('index.html'))));return}
e.respondWith(caches.match(req).then(r=>r||fetch(req)))});
