#!/usr/bin/env python3
"""Construit les fichiers de données de « Trouver de l'aide » à partir de l'open data officiel.

Sources (toutes en Licence Ouverte, sur data.gouv.fr) :
  - RPPS « Annuaire Santé – extractions en libre accès » (Agence du Numérique en Santé) :
    psychologues, psychothérapeutes, psychiatres, médecins généralistes, diététiciens,
    addictologues, assistants de service social.
  - FINESS établissements géolocalisés (ministère de la Santé) :
    CMP/CMPP, CSAPA/CAARUD, CHRS et centres d'accueil, centres de santé sexuelle.
  - Annuaire des avocats de France (Conseil national des barreaux).
  - Communes (geo.api.gouv.fr) pour positionner chaque adresse au centre de sa commune.

Sortie : out/<categorie>/<departement>.json (tableaux compacts) + out/index.json.
Champs d'une ligne : [nom, profession, adresse, cp, ville, lat, lon, tel, email, mode, structure]
"""
import csv, io, json, os, re, sys, time, unicodedata, urllib.request, collections

OUT = sys.argv[1] if len(sys.argv) > 1 else 'out'
WORK = os.environ.get('WORK', 'work')
os.makedirs(WORK, exist_ok=True)


def log(*a):
    print(*a, flush=True)


FIX = os.environ.get('FIXTURES')


def fetch(url, dest=None, tries=6):
    if FIX:
        import shutil
        for key, fn in json.load(open(os.path.join(FIX, 'map.json'))).items():
            if key in url:
                src = os.path.join(FIX, fn)
                if dest is None:
                    return open(src, 'rb').read()
                shutil.copy(src, dest)
                return dest
        raise RuntimeError('no fixture for ' + url)
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'ma-boussole-data/1.0'})
            with urllib.request.urlopen(req, timeout=300) as r:
                if dest is None:
                    return r.read()
                with open(dest, 'wb') as f:
                    while True:
                        b = r.read(1 << 20)
                        if not b:
                            break
                        f.write(b)
                return dest
        except Exception as e:
            log('  retry', k + 1, url, e)
            time.sleep(10 * (k + 1))
    raise RuntimeError('download failed: ' + url)


def dataset_resource(slug, pred):
    d = json.loads(fetch('https://www.data.gouv.fr/api/1/datasets/%s/' % slug))
    res = [r for r in d['resources'] if pred(r)]
    res.sort(key=lambda r: r.get('last_modified') or r.get('created_at') or '', reverse=True)
    if not res:
        raise RuntimeError('no resource for ' + slug)
    log('  source', slug, '->', res[0]['title'], res[0]['url'])
    return res[0]['url']


def norm(s):
    s = unicodedata.normalize('NFD', s or '').encode('ascii', 'ignore').decode().upper()
    s = re.sub(r'\bSAINTE?\b', lambda m: 'STE' if m.group(0) == 'SAINTE' else 'ST', s)
    return re.sub(r'[^A-Z0-9]+', '', s)


KEEP_UP = {'CH', 'CHU', 'CHS', 'CMP', 'CMPP', 'CSAPA', 'CAARUD', 'CHRS', 'EVARS', 'BAPU', 'SAS', 'SARL', 'SCP', 'SELARL', 'SELAS', 'SCM', 'EHPAD', 'ARS', 'CCAS', 'II', 'III'}


def title(s):
    s = (s or '').strip()
    if not s or not s.isupper():
        return s
    return re.sub(r"[A-ZÀ-ÖØ-Ý]+", lambda m: m.group(0) if m.group(0) in KEEP_UP else m.group(0).capitalize(), s)


def tel(s):
    d = re.sub(r'\D', '', s or '')
    if d.startswith('33') and len(d) == 11:
        d = '0' + d[2:]
    if len(d) == 10:
        return ' '.join(d[i:i + 2] for i in range(0, 10, 2))
    return (s or '').strip()


# ---------------------------------------------------------------- communes
log('== communes')
COM = {}            # INSEE -> (lat, lon, dep, nom)
BY_CP = collections.defaultdict(list)  # cp -> [(normnom, insee)]
for typ in ('commune-actuelle', 'arrondissement-municipal', 'commune-deleguee', 'commune-associee'):
    try:
        data = json.loads(fetch('https://geo.api.gouv.fr/communes?type=%s&fields=nom,code,codesPostaux,centre,codeDepartement,chefLieu&format=json' % typ))
    except Exception as e:
        log('  skip', typ, e)
        continue
    for c in data:
        ce = c.get('centre')
        dep = c.get('codeDepartement')
        if not ce and c.get('chefLieu') and c['chefLieu'] in COM:
            la, lo, dep2, _ = COM[c['chefLieu']]
            ce = {'coordinates': [lo, la]}
            dep = dep or dep2
        if not ce:
            continue
        if not dep:
            dep = c['code'][:3] if c['code'].startswith('97') else c['code'][:2]
        lo, la = ce['coordinates']
        if c['code'] not in COM:
            COM[c['code']] = (round(la, 5), round(lo, 5), dep, c['nom'])
        for cp in c.get('codesPostaux') or []:
            BY_CP[cp].append((norm(c['nom']), c['code']))
    log('  ', typ, len(data))
log('  communes total', len(COM))


def locate(insee=None, cp=None, ville=None):
    if insee and insee in COM:
        return COM[insee]
    cands = BY_CP.get(cp or '', [])
    if cands:
        nv = norm(ville)
        for n, code in cands:
            if nv and (n == nv or nv.startswith(n) or n.startswith(nv)):
                return COM[code]
        return COM[cands[0][1]]
    if cp and len(cp) == 5:  # CEDEX, etc. : on tente la ville seule dans le département
        nv = norm(ville)
        for k, v in COM.items():
            if nv and norm(v[3]) == nv and k[:2] == cp[:2]:
                return v
    return None


OUTD = collections.defaultdict(lambda: collections.defaultdict(list))  # cat -> dep -> rows
SEEN = collections.defaultdict(dict)
STATS = collections.Counter()
MISS = collections.Counter()


def add(cat, key, row, loc):
    prev = SEEN[cat].get(key) if isinstance(SEEN[cat], dict) else None
    if prev is not None:
        for i in (7, 8, 10):  # complète téléphone, e-mail, structure manquants
            if not prev[i] and row[i]:
                prev[i] = row[i]
        return
    SEEN[cat][key] = row
    la, lo, dep, _ = loc
    row[5], row[6] = la, lo
    OUTD[cat][dep].append(row)
    STATS[cat] += 1


# ---------------------------------------------------------------- Ameli (téléphones des libéraux conventionnés)
log('== Ameli (téléphones)')
AMELI_TEL = {}
try:
    am_url = dataset_resource('annuaire-sante-ameli', lambda r: (r.get('format') or '').lower() == 'csv' and (r.get('filesize') or 0) > 50_000_000)
    am = fetch(am_url, os.path.join(WORK, 'ameli.csv'))
    with open(am, encoding='utf-8-sig', errors='replace') as f:
        for r in csv.DictReader(f, delimiter=';'):
            t = (r.get('coordonnees_num_tel') or '').strip()
            if not t:
                continue
            k = (norm(r.get('ps_activite_nom')), norm(r.get('ps_activite_prenom')), (r.get('coordonnees_code_postal') or '').strip())
            AMELI_TEL.setdefault(k, tel(t))
    log('  téléphones Ameli', len(AMELI_TEL))
except Exception as e:
    log('  Ameli indisponible', e)

# ---------------------------------------------------------------- RPPS
log('== RPPS')
rpps_url = dataset_resource(
    'annuaire-sante-extractions-des-donnees-en-libre-acces-des-professionnels-intervenant-dans-le-systeme-de-sante-rpps',
    lambda r: 'personne-activite' in (r.get('title') or '').lower() or 'personne_activite' in (r.get('title') or '').lower())
rpps = fetch(rpps_url, os.path.join(WORK, 'rpps.txt'))
MODE = {'L': 'L', 'S': 'S', 'B': 'B'}
SF = collections.Counter()
with open(rpps, encoding='utf-8', errors='replace') as f:
    h = f.readline().rstrip('\n').split('|')
    ix = {name: i for i, name in enumerate(h)}

    def col(p, name):
        i = ix.get(name)
        return p[i].strip() if i is not None and i < len(p) else ''

    for line in f:
        p = line.rstrip('\n').split('|')
        prof = col(p, 'Libellé profession')
        sf = col(p, 'Libellé savoir-faire')
        cats = []
        if prof == 'Psychologue':
            cats.append(('psy', 'Psychologue'))
        elif prof == 'Psychothérapeute':
            cats.append(('psyth', 'Psychothérapeute'))
        elif prof == 'Diététicien':
            cats.append(('diet', 'Diététicien·ne'))
        elif prof == 'Assistant de service social':
            cats.append(('ass', 'Assistant·e de service social'))
        elif prof == 'Médecin':
            SF[sf] += 1
            if re.search(r'sychiatr', sf):
                cats.append(('psychiatre', sf or 'Psychiatre'))
            if re.search(r'[Mm][ée]decine [Gg][ée]n[ée]rale', sf):
                cats.append(('mg', 'Médecin généraliste'))
            if re.search(r'ddictolog', sf):
                cats.append(('addicto', 'Médecin addictologue'))
        if not cats:
            continue
        cp = col(p, 'Code postal (coord. structure)')
        insee = col(p, 'Code commune (coord. structure)')
        ville = col(p, 'Libellé commune (coord. structure)')
        if not cp and not insee:
            continue
        loc = locate(insee, cp, ville)
        if not loc:
            MISS['rpps'] += 1
            continue
        voie = ' '.join(x for x in [col(p, 'Numéro Voie (coord. structure)') + col(p, 'Indice répétition voie (coord. structure)'),
                                    col(p, 'Libellé type de voie (coord. structure)'), col(p, 'Libellé Voie (coord. structure)')] if x)
        comp = col(p, 'Complément point géographique (coord. structure)') or col(p, 'Mention distribution (coord. structure)')
        adr = ', '.join(x for x in [voie, comp] if x)
        civ = col(p, "Libellé civilité d'exercice") or ''
        nom = ' '.join(x for x in [civ if civ.startswith('Doc') else '', title(col(p, "Prénom d'exercice")), col(p, "Nom d'exercice").upper()] if x)
        struct = col(p, 'Enseigne commerciale site') or col(p, 'Raison sociale site')
        mode = MODE.get(col(p, 'Code mode exercice'), '')
        secteur = col(p, "Libellé secteur d'activité")
        t = tel(col(p, 'Téléphone (coord. structure)') or col(p, 'Téléphone 2 (coord. structure)'))
        if not t and AMELI_TEL:
            t = AMELI_TEL.get((norm(col(p, "Nom d'exercice")), norm(col(p, "Prénom d'exercice")), cp), '')
            if t:
                STATS['tel_ameli'] += 1
        mail = col(p, 'Adresse e-mail (coord. structure)').lower()
        idpp = col(p, 'Identifiant PP')
        for cat, label in cats:
            row = [nom, label, title(adr), cp, title(ville), 0, 0, t, mail, mode, title(struct) + (' · ' + secteur if secteur and secteur not in ('Cabinet individuel',) else '')]
            add(cat, (idpp, cp, adr.upper()), row, loc)
log('  savoir-faire médecins (top):', SF.most_common(12))

# ---------------------------------------------------------------- FINESS
log('== FINESS')
fin_url = dataset_resource('finess-extraction-du-fichier-des-etablissements',
                           lambda r: 'olocalis' in (r.get('title') or '') and (r.get('format') or '').lower() == 'csv' and 'HISTORIQUE' not in (r.get('title') or ''))
fin = fetch(fin_url, os.path.join(WORK, 'finess.csv'))
FCAT = {
    '156': 'cmp', '189': 'cmp', '292': 'cmp', '161': 'cmp', '221': 'cmp',
    '197': 'csapa', '178': 'csapa',
    '214': 'chrs', '219': 'chrs',
    '228': 'sexu', '231': 'sexu',
    '124': 'cds',
}
from pyproj import Transformer
TR = {}


def to_wgs(x, y, epsg):
    t = TR.get(epsg)
    if t is None:
        t = TR[epsg] = Transformer.from_crs('EPSG:%s' % epsg, 'EPSG:4326', always_xy=True)
    lo, la = t.transform(x, y)
    return round(la, 5), round(lo, 5)


etabs, geo = {}, {}
with open(fin, encoding='utf-8', errors='replace') as f:
    for line in f:
        p = line.rstrip('\n').split(';')
        if p[0] == 'structureet' and len(p) > 27 and p[18] in FCAT:
            etabs[p[1]] = p
        elif p[0] == 'geolocalisation' and len(p) > 4:
            m = re.search(r'EPSG:(\d+)', p[4])
            try:
                geo[p[1]] = (float(p[2]), float(p[3]), m.group(1) if m else '2154')
            except ValueError:
                pass
for fid, p in etabs.items():
    cat = FCAT[p[18]]
    la = lo = None
    if fid in geo:
        try:
            la, lo = to_wgs(*geo[fid])
        except Exception:
            la = None
    m = re.match(r'(\d{5})\s+(.*)', p[15])
    cp, ville = (m.group(1), m.group(2)) if m else ('', p[15])
    ville = re.sub(r'\s+CEDEX.*$', '', ville)
    dep = p[13]
    loc = locate(None, cp, ville)
    if la is None:
        if not loc:
            MISS['finess'] += 1
            continue
        la, lo = loc[0], loc[1]
    if loc:
        dep = loc[2]
    adr = ' '.join(x for x in [p[7], p[8], p[9]] if x)
    if p[11]:
        adr += ', ' + p[11]
    statut = p[27] if len(p) > 27 and p[27] else (p[25] if len(p) > 25 else '')
    row = [title(p[3] or p[4]), p[19], title(adr), cp, title(ville), la, lo, tel(p[16]), '', 'E', title(p[4]) + (' · ' + statut if statut else '')]
    add(cat, fid, row, (la, lo, dep, ville))

# ---------------------------------------------------------------- Avocats
log('== Avocats')
av_url = dataset_resource('annuaire-des-avocats-de-france', lambda r: (r.get('format') or '').lower() == 'csv')
raw = fetch(av_url)
try:
    txt = raw.decode('utf-8')
except UnicodeDecodeError:
    txt = raw.decode('cp1252')
SP = collections.Counter()
for r in csv.DictReader(io.StringIO(txt), delimiter=';'):
    cp = (r.get('cbCp') or '').strip()
    ville = (r.get('cbVille') or '').strip()
    loc = locate(None, cp, ville)
    if not loc:
        MISS['avocats'] += 1
        continue
    sps = [s.strip() for s in (r.get('spLibelle1'), r.get('spLibelle2'), r.get('spLibelle3')) if s and s.strip()]
    for s in sps:
        SP[s] += 1
    nom = ' '.join(x for x in [title(r.get('avPrenom')), (r.get('avNom') or '').upper()] if x)
    adr = ', '.join(x for x in [(r.get('cbAdresse1') or '').strip(), (r.get('cbAdresse2') or '').strip()] if x)
    row = [nom, 'Avocat·e' + (' — ' + ', '.join(sps) if sps else ''), adr, cp, title(ville), 0, 0, '', '', 'L',
           title(r.get('cbRaisonSociale') or '') + (' · Barreau de ' + title(r.get('NomBarreau')) if r.get('NomBarreau') else '')]
    add('avocat', (nom, cp, adr.upper()), row, loc)
log('  spécialités avocats (top):', SP.most_common(30))

# ---------------------------------------------------------------- écriture
log('== écriture')
if os.path.isdir(OUT):
    import shutil
    shutil.rmtree(OUT)
os.makedirs(OUT)
bbox = {}
for code, (la, lo, dep, _) in COM.items():
    b = bbox.setdefault(dep, [la, lo, la, lo])
    b[0], b[1], b[2], b[3] = min(b[0], la), min(b[1], lo), max(b[2], la), max(b[3], lo)
cats = {}
size = 0
STATS_TEL = {c: sum(1 for d in v.values() for r in d if r[7]) for c, v in OUTD.items()}
log('  lignes avec téléphone', STATS_TEL)
for cat, deps in OUTD.items():
    os.makedirs(os.path.join(OUT, cat), exist_ok=True)
    cats[cat] = {}
    for dep, rows in deps.items():
        rows.sort(key=lambda r: (r[3], r[0]))
        pth = os.path.join(OUT, cat, dep + '.json')
        with open(pth, 'w', encoding='utf-8') as f:
            json.dump(rows, f, ensure_ascii=False, separators=(',', ':'))
        size += os.path.getsize(pth)
        cats[cat][dep] = len(rows)
index = {'updated': time.strftime('%Y-%m-%d'), 'deps': {k: [round(x, 3) for x in v] for k, v in bbox.items()},
         'cats': cats, 'counts': dict(STATS),
         'sources': ['RPPS - Annuaire Santé (ANS)', 'FINESS (ministère de la Santé)', 'Annuaire des avocats de France (CNB)', 'geo.api.gouv.fr']}
with open(os.path.join(OUT, 'index.json'), 'w', encoding='utf-8') as f:
    json.dump(index, f, ensure_ascii=False, separators=(',', ':'))
log('  counts', dict(STATS))
log('  non localisés', dict(MISS))
log('  taille totale %.1f Mo' % (size / 1e6))
for cat in sorted(cats):
    big = sorted(cats[cat].items(), key=lambda x: -x[1])[:3]
    log('  ', cat, sum(cats[cat].values()), 'lignes, plus gros départements', big)
log('  exemple psy Landes (40):', json.dumps(OUTD['psy'].get('40', [])[:3], ensure_ascii=False))
