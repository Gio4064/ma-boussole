"""Liste des structures publiques à contacter autour d'un point (open data officiel)."""
import json, math, os, re, sys, tarfile, io, urllib.request, collections
LAT, LON, KM = 43.752, -1.327, 25
def get(u, t=300):
    return urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'ma-boussole'}), timeout=t).read()
def km(a, b, c, d):
    r = math.radians; x = r(d - b) * math.cos(r((a + c) / 2)); y = r(c - a); return 6371 * math.hypot(x, y)
out = []
# --- Annuaire de l'administration (service-public.fr)
d = json.loads(get('https://www.data.gouv.fr/api/1/datasets/service-public-fr-annuaire-de-l-administration-base-de-donnees-locales/'))
for r in d['resources']:
    print('RES', r['title'], r['format'], r.get('filesize'), r['url'])
res = sorted([r for r in d['resources'] if (r.get('format') or '').lower() in ('json', 'bz2', 'tar.bz2', 'zip', 'gz') or r['url'].endswith(('.json', '.bz2', '.zip', '.gz'))],
             key=lambda r: r.get('last_modified') or '', reverse=True)
raw = get(res[0]['url'])
print('downloaded', res[0]['url'], len(raw))
data = None
if raw[:3] == b'BZh':
    tf = tarfile.open(fileobj=io.BytesIO(raw), mode='r:bz2')
    for m in tf.getmembers():
        print('member', m.name, m.size)
        if m.name.endswith('.json') and m.size > 1_000_000:
            data = json.load(tf.extractfile(m)); break
elif raw[:2] == b'PK':
    import zipfile
    z = zipfile.ZipFile(io.BytesIO(raw))
    for n in z.namelist():
        print('member', n)
        if n.endswith('.json'):
            data = json.loads(z.read(n)); break
else:
    data = json.loads(raw)
items = data.get('service') if isinstance(data, dict) else data
print('services', len(items)); print('SAMPLE', json.dumps(items[0], ensure_ascii=False)[:1500])
types = collections.Counter()
for s in items:
    piv = [p.get('type_service_local') for p in (s.get('pivot') or [])]
    ad = (s.get('adresse') or [{}])[0]
    try:
        la, lo = float(ad.get('latitude')), float(ad.get('longitude'))
    except (TypeError, ValueError):
        continue
    dist = km(LAT, LON, la, lo)
    if dist > KM:
        continue
    for p in piv: types[p] += 1
    out.append({'src': 'service-public', 'type': ','.join(x for x in piv if x) or '?', 'nom': s.get('nom'),
                'commune': ad.get('nom_commune'), 'adresse': ' '.join(x for x in [ad.get('numero_voie'), ad.get('complement1')] if x),
                'cp': ad.get('code_postal'), 'email': [e.get('valeur') if isinstance(e, dict) else e for e in (s.get('adresse_courriel') or [])],
                'tel': [t.get('valeur') for t in (s.get('telephone') or [])], 'site': [w.get('valeur') for w in (s.get('site_internet') or [])],
                'km': round(dist, 1)})
print('TYPES', types.most_common(60))
# --- Annuaire de l'éducation
try:
    u = ('https://data.education.gouv.fr/api/explore/v2.1/catalog/datasets/fr-en-annuaire-education/records?limit=100'
         '&where=' + urllib.parse.quote("within_distance(position, geom'POINT(%s %s)', %dkm) and type_etablissement in ('Collège','Lycée')" % (LON, LAT, KM)))
    import urllib.parse
except Exception:
    pass
import urllib.parse
u = ('https://data.education.gouv.fr/api/explore/v2.1/catalog/datasets/fr-en-annuaire-education/records?limit=100&where=' +
     urllib.parse.quote("within_distance(position, geom'POINT(%s %s)', %dkm) and (type_etablissement='Collège' or type_etablissement='Lycée')" % (LON, LAT, KM)))
try:
    j = json.loads(get(u))
    print('EDU total', j.get('total_count'))
    for r in j.get('results', []):
        out.append({'src': 'education', 'type': r.get('type_etablissement'), 'nom': r.get('nom_etablissement'), 'commune': r.get('nom_commune'),
                    'adresse': r.get('adresse_1'), 'cp': r.get('code_postal'), 'email': [r.get('mail')] if r.get('mail') else [],
                    'tel': [r.get('telephone')] if r.get('telephone') else [], 'site': [r.get('web')] if r.get('web') else [],
                    'statut': r.get('statut_public_prive'),
                    'km': round(km(LAT, LON, r['position']['lat'], r['position']['lon']), 1) if r.get('position') else None})
except Exception as e:
    print('EDU error', e)
print('OUT_JSON_START')
print(json.dumps(out, ensure_ascii=False))
print('OUT_JSON_END')
