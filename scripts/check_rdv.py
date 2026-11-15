"""Vérifie une fois par mois que les liens de RDV de rdv_links.json répondent encore.
Une seule requête par lien. Un lien n'est retiré que si le site répond clairement
« page introuvable » (404/410) ; en cas de blocage ou d'erreur réseau, on le garde."""
import json, time, urllib.request, urllib.error, datetime
P = 'rdv_links.json'
d = json.load(open(P, encoding='utf-8'))
def gone(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'MaBoussole-linkcheck/1.0 (+https://gio4064.github.io/ma-boussole/)'})
    try:
        urllib.request.urlopen(req, timeout=20); return False
    except urllib.error.HTTPError as e:
        return e.code in (404, 410)
    except Exception:
        return False
kept, dropped = [], []
for l in d['links']:
    (dropped if gone(l['url']) else kept).append(l); time.sleep(2)
for k, u in list(d.get('manual', {}).items()):
    if gone(u): dropped.append({'url': u}); del d['manual'][k]
    time.sleep(2)
d['links'] = kept
d['checked'] = datetime.date.today().isoformat()
json.dump(d, open(P, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('gardés', len(kept), 'retirés', len(dropped)); [print(' -', x['url']) for x in dropped]
