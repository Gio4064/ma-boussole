const C='boussole-v3',F=['./','index.html','manifest.webmanifest','icons/logo.svg','icons/icon-192.png','icons/icon-512.png','img/fond-clair.svg','img/fond-sombre.svg'];
self.addEventListener('install',e=>{self.skipWaiting();e.waitUntil(caches.open(C).then(c=>c.addAll(F)))});
self.addEventListener('activate',e=>{e.waitUntil(Promise.all([caches.keys().then(k=>Promise.all(k.filter(x=>x!==C).map(x=>caches.delete(x)))),self.clients.claim()]))});
self.addEventListener('fetch',e=>{if(e.request.method!=='GET')return;
const isHtml=e.request.mode==='navigate'||(e.request.headers.get('accept')||'').includes('text/html');
if(isHtml){e.respondWith(fetch(e.request).then(r=>{const rc=r.clone();caches.open(C).then(c=>c.put(e.request,rc));return r}).catch(()=>caches.match(e.request)));return}
e.respondWith(caches.match(e.request).then(r=>r||fetch(e.request)))});
