const C='boussole-v2',F=['./','index.html','manifest.webmanifest','icons/logo.svg','icons/icon-192.png','icons/icon-512.png','img/fond-clair.svg','img/fond-sombre.svg'];
self.addEventListener('install',e=>e.waitUntil(caches.open(C).then(c=>c.addAll(F))));
self.addEventListener('activate',e=>e.waitUntil(caches.keys().then(k=>Promise.all(k.filter(x=>x!==C).map(x=>caches.delete(x))))));
self.addEventListener('fetch',e=>{if(e.request.method!=='GET')return;e.respondWith(caches.match(e.request).then(r=>r||fetch(e.request)))});
