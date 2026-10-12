#!/usr/bin/env python3
"""gellertlabor.hu csomaglista (/cscs CSV) régi–új összevetése.

Használat:
  python3 honlap_audit/osszevet.py honlap_audit/adat/cscs_regi.csv honlap_audit/adat/cscs_2026-10-12.csv

Kimenet (honlap_audit/kimenet/):
  parok.json        csomagonként: allapot (uj / torolt / valtozatlan / megvaltozott),
                    név- és árváltozás, szöveghasonlóság, régi és új tisztított szöveg
                    (csak a megváltozottaknál), ujjlenyomat-jelzők mindkét oldalon
  valtozatok.json   kifejezésváltozatok előfordulása régi vs új állományban
  osszesito.txt     rövid számszerű áttekintés a modell-értékelés előtt

A párosítás ID szerint megy; ha egy ID csak az egyik oldalon van, név szerint is
megpróbálja (normalizált név), mert az átírás új nódot is létrehozhatott.
"""
import csv, re, sys, html, json, difflib, collections, unicodedata
from pathlib import Path

csv.field_size_limit(10**9)

def tiszta(d):
    t = re.sub(r'</(p|li|h\d|div|tr|td|ul|ol)>|<br\s*/?>', '\n', d, flags=re.I)
    t = html.unescape(re.sub(r'<[^>]+>', ' ', t))
    t = re.sub(r'[ \t ]+', ' ', t)
    return re.sub(r'\n\s*\n+', '\n', t).strip()

def normnev(n):
    n = unicodedata.normalize('NFKC', n).lower()
    return re.sub(r'[^0-9a-záéíóöőúüű]+', ' ', n).strip()

def beolvas(p):
    sorok = list(csv.reader(open(p, encoding='utf-8')))
    fej, adat = sorok[0], sorok[1:]
    out = {}
    for r in adat:
        r = r + [''] * (5 - len(r))
        i = r[4].strip() or 'nev:' + normnev(r[0])
        out[i] = {'id': i, 'nev': r[0].strip(), 'nyers': r[1], 'szoveg': tiszta(r[1]),
                  'ar': r[2].strip(), 'jelleg': r[3].strip()}
    return out

# Gépi (ChatGPT) átírás jelzői. A szamlalt jelzők csak valószínűsítenek; a
# 'biztos' jelzők (láthatatlan karakter, forrásnév) bemásolásra utalnak.
BIZTOS = {
    'u2060_lathatatlan': '\u2060',
    'forrasnev': r'MedlinePlus|\bNICE\b|\bNIH\b|\bWHO\b|American Thyroid|Mayo Clinic|\bCDC\b|UpToDate|PubMed',
    'chatgpt_marad': r'turn\d+search|oaicite|\bcite\b|chatgpt',
}
VALOSZINU = {
    'onmagaban_nem': r'önmagában (?:nem|nem alkalmas)',
    'tamogat_segit': r'\bsegíthet\b|támpont\w*|támogatja\b|elősegít\w*',
    'kinek_ajanlott': r'Kiknek? (?:ajánl|javasol)\w*|különösen indokolt',
    'kezeloorvos': r'kezelőorvos\w*',
    'fontos_tudnivalok': r'Fontos tudnivaló',
    'nem_helyettesiti': r'nem helyettesíti|nem zárja ki|nem igazolj',
}
# Egyéb láthatatlan karakter (U+200B/FEFF): régi Drupal/Word-szövegben is előfordul,
# ezért nem bemásolás-bizonyíték, csak külön jelezzük.
EGYEB = {'zero_width': r'[\u200b\u200c\u200d\ufeff]'}
def jelzok(t):
    b = {k: len(re.findall(v, t, re.I if k != 'u2060_lathatatlan' else 0)) for k, v in BIZTOS.items()}
    v = {k: len(re.findall(rx, t, re.I)) for k, rx in VALOSZINU.items()}
    gj = t.count('–') + t.count('—')
    v['gondolatjel_per_1000'] = round(1000 * gj / max(len(t), 1), 1)
    e = {k: len(re.findall(rx, t)) for k, rx in EGYEB.items()}
    return {'biztos': {k: n for k, n in b.items() if n},
            'egyeb': {k: n for k, n in e.items() if n},
            'valoszinu': {k: n for k, n in v.items() if n},
            'valoszinu_pont': sum(1 for k, n in v.items() if n and k != 'gondolatjel_per_1000')
                              + (1 if v['gondolatjel_per_1000'] >= 3 else 0),
            'hossz': len(t)}

VALTOZAT_CSOPORT = {
    'ehgyomor': r'\béh(?:gyomor|omi|omra|gyomri|gyomorra|en)\w*',
    'szifilisz': r'szifilisz\w*|syphil\w*|lues\w*|treponema pallidum(?: elleni antitest| PCR)?',
    'vervetel_mintavetel': r'\bvérvétel\w*|\bmintavétel\w*|\bmintaadás\w*',
    'leletido': r'\d+\s*(?:[-–]\s*\d+\s*)?munkanap',
    'fejlec': r'Fontos tudnivaló\w*|Tudnivalók|Mikor (?:javasolt|ajánlott)|Kiknek? ajánl\w*|A csomag tartalma|A vizsgált kórokozók|Előkészület\w*',
    'd_vitamin': r'25-?OH[- ]?D(?:-?vitamin)?|D3?-?vitamin',
    'vizelet': r'vizelet (?:általános|rutin|üledék)\w*(?: vizsgálata)?(?: (?:és )?üledékkel)?',
}
def valtozatok(csomagok):
    out = {}
    for g, rx in VALTOZAT_CSOPORT.items():
        c = collections.defaultdict(set)
        for i, cs in csomagok.items():
            for m in re.finditer(rx, cs['szoveg'], re.I):
                c[re.sub(r'\s+', ' ', m.group(0)).lower()].add(i)
        out[g] = {k: len(v) for k, v in sorted(c.items(), key=lambda x: -len(x[1]))}
    return out

def main(regi_p, uj_p, ki=Path(__file__).parent / 'kimenet'):
    ki.mkdir(exist_ok=True)
    R, U = beolvas(regi_p), beolvas(uj_p)
    # név szerinti mentőpárosítás az egyoldalú ID-kra
    r_nev = {normnev(c['nev']): i for i, c in R.items() if i not in U}
    u_nev = {normnev(c['nev']): i for i, c in U.items() if i not in R}
    atnevpar = {r_nev[n]: u_nev[n] for n in r_nev.keys() & u_nev.keys()}
    parok = []
    lattuk_u = set()
    for i, r in R.items():
        ui = i if i in U else atnevpar.get(i)
        if not ui:
            parok.append({'id': i, 'allapot': 'torolt', 'nev': r['nev'], 'ar_regi': r['ar'],
                          'jelzok_regi': jelzok(r['szoveg'])})
            continue
        u = U[ui]; lattuk_u.add(ui)
        hasonlo = round(difflib.SequenceMatcher(None, r['szoveg'], u['szoveg'], autojunk=False).ratio(), 3)
        p = {'id': i, 'uj_id': ui if ui != i else None, 'nev': u['nev'],
             'nev_regi': r['nev'] if r['nev'] != u['nev'] else None,
             'ar_regi': r['ar'], 'ar_uj': u['ar'], 'arvaltozas': r['ar'] != u['ar'],
             'hasonlosag': hasonlo,
             'jelzok_regi': jelzok(r['szoveg']), 'jelzok_uj': jelzok(u['szoveg'])}
        if r['szoveg'] == u['szoveg'] and not p['nev_regi']:
            p['allapot'] = 'valtozatlan'
        else:
            p['allapot'] = 'megvaltozott'
            p['szoveg_regi'], p['szoveg_uj'] = r['szoveg'], u['szoveg']
        parok.append(p)
    for i, u in U.items():
        if i not in lattuk_u:
            parok.append({'id': i, 'allapot': 'uj', 'nev': u['nev'], 'ar_uj': u['ar'],
                          'jelzok_uj': jelzok(u['szoveg']), 'szoveg_uj': u['szoveg']})
    kulcs = lambda p: int(p['id']) if str(p['id']).isdigit() else 10**9
    parok.sort(key=kulcs)
    json.dump(parok, open(ki / 'parok.json', 'w'), ensure_ascii=False, indent=1)
    json.dump({'regi': valtozatok(R), 'uj': valtozatok(U)}, open(ki / 'valtozatok.json', 'w'),
              ensure_ascii=False, indent=1)
    db = collections.Counter(p['allapot'] for p in parok)
    biztos_uj = [p['id'] for p in parok if p.get('jelzok_uj', {}).get('biztos')]
    biztos_regi = [p['id'] for p in parok if p.get('jelzok_regi', {}).get('biztos')]
    with open(ki / 'osszesito.txt', 'w') as f:
        f.write(f"régi: {len(R)} csomag, új: {len(U)} csomag\n")
        f.write(f"állapotok: {dict(db)}\n")
        f.write(f"név szerint párosított (új ID-val újra felvett): {atnevpar}\n")
        f.write(f"bemásolás-nyom az új állományban ({len(biztos_uj)}): {biztos_uj}\n")
        f.write(f"bemásolás-nyom a régi állományban ({len(biztos_regi)}): {biztos_regi}\n")
        megv = [p for p in parok if p['allapot'] == 'megvaltozott']
        f.write(f"megváltozott, hasonlóság szerint (legjobban átírt elöl):\n")
        for p in sorted(megv, key=lambda p: p['hasonlosag'])[:60]:
            f.write(f"  {p['id']}\t{p['hasonlosag']}\t{p['nev']}\n")
    print(open(ki / 'osszesito.txt').read())

if __name__ == '__main__':
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
