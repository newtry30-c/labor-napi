#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gellért Medical Laboratórium - hétfői (vérvételi nap) források mechanikus összefésülése.

Öt forrást kapcsol össze páciensenként egy JSON-ba (hetfo.json), és a nap egyetlen LIS-kéréséhez sem
párosuló adatlapokat külön fájlokba sorolja (kesobb.json, nem_aktualis.json). NEM értékel, nem dönt,
nem egészít ki: amit egy forrás nem tartalmaz, az null.

Futtatás:
    python3 -I vernap/osszefesul.py ÉÉÉÉ-HH-NN

Bemenet (a repó run/ mappájában): adatlapok.json, levelezes_A/B/C.json, hp_naptar.json, ertekeles.json,
plusz élő adatok KIZÁRÓLAG HTTP GET-tel (LIS REST API, CSAPI).
Kimenet (ugyanott): hetfo.json, kesobb.json, nem_aktualis.json, ellenorzes.json
"""
import argparse
import copy
import datetime
import html
import json
import pathlib
import re
import subprocess
import sys
import time
import unicodedata
from collections import OrderedDict, defaultdict

BASE = pathlib.Path(__file__).resolve().parent.parent / "run"  # bemenet és kimenet: a repó run/ mappája (gitignore)
API = "https://a.gellertlabor.hu/api/api.php7/records/"
CSAPI = "https://a.gellertlabor.hu/p8/csapi/public/api.php"
ERVENYTELEN_SZULD = {"", "0001-01-01", None}

# A megbízás szerint: ugyanaz a személy kétszer szerepel a LIS-ben; a levelezés-rekord vid-je -> további vid-ek.
TOBBSZOROS_VID = {}  # 10-11: a 29259 törölve; napi futásnál üres

GET_LOG = []  # minden elküldött kérés (csak GET)


# --------------------------------------------------------------------------------------------------
# HTTP (kizárólag GET, curl-lel)
# --------------------------------------------------------------------------------------------------
class HttpHiba(Exception):
    def __init__(self, status, body, url):
        super().__init__("HTTP %s: %s" % (status, url))
        self.status = status
        self.body = body
        self.url = url


def http_get(url, params=None, retries=6):
    """Egyetlen GET kérés curl-lel. Átmeneti hálózati hibára / 5xx-re újrapróbál. 4xx-re HttpHiba."""
    params = params or []
    cmd = ["curl", "-sS", "-G", "--max-time", "90", "-w", "\n__HTTP__%{http_code}", url]
    for k, v in params:
        cmd += ["--data-urlencode", "%s=%s" % (k, v)]
    # biztonsági ellenőrzés: itt semmilyen nem-GET kapcsoló nem szerepelhet
    for tilos in ("-X", "-d", "--data", "-T", "-F", "--request", "--upload-file", "--form"):
        assert tilos not in cmd, "csak GET engedélyezett"
    utolso = None
    for kiserlet in range(1, retries + 1):
        GET_LOG.append(url + ("?" + "&".join("%s=%s" % (k, v) for k, v in params) if params else ""))
        p = subprocess.run(cmd, capture_output=True)
        out = p.stdout.decode("utf-8", errors="replace")
        if p.returncode == 0 and "\n__HTTP__" in out:
            body, _, code = out.rpartition("\n__HTTP__")
            code = int(code.strip() or 0)
            if 200 <= code < 300:
                return body
            if 400 <= code < 500:
                raise HttpHiba(code, body, url)
            utolso = HttpHiba(code, body, url)
        else:
            utolso = HttpHiba("curl-%s" % p.returncode, p.stderr.decode("utf-8", errors="replace"), url)
        time.sleep(1.5 * kiserlet)
    raise utolso


def api(tabla, params):
    body = http_get(API + tabla, params)
    d = json.loads(body)
    return d["records"] if isinstance(d, dict) and "records" in d else d


def chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


# --------------------------------------------------------------------------------------------------
# Névkezelés
# --------------------------------------------------------------------------------------------------
_TR = str.maketrans({"ø": "o", "ł": "l", "đ": "d", "ß": "ss", "æ": "ae", "œ": "oe", "ð": "d", "þ": "th"})


def norm_tokens(s):
    """kisbetű, ékezetek le, írásjelek le, szavak halmaza."""
    if not s:
        return frozenset()
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower().translate(_TR)
    return frozenset(t for t in re.split(r"[^a-z0-9]+", s) if t)


def _lev1(a, b):
    """True, ha a két szó szerkesztési távolsága pontosan 1."""
    if a == b:
        return False
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la == lb:
        return sum(1 for x, y in zip(a, b) if x != y) == 1
    if la > lb:
        a, b = b, a
    i = 0
    while i < len(a) and a[i] == b[i]:
        i += 1
    return a[i:] == b[i + 1:]


def szo_kozelito(a, b):
    return len(a) >= 5 and len(b) >= 5 and a[:5] == b[:5] and _lev1(a, b)


def name_match(ta, tb):
    """None, ha nem egyezik; különben 'pontos' | 'reszhalmaz' | 'kozelito'.
    Szabály: az egyik szóhalmaza részhalmaza a másiknak és >=2 közös szó; vagy 1 betűs eltérés
    (a vezetéknév egyezése + keresztnév első 5 betűje) -> 'kozelito'."""
    if not ta or not tb:
        return None
    kis, nagy = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    kozos = kis & nagy
    if kis <= nagy:
        if len(kozos) >= 2:
            return "pontos" if ta == tb else "reszhalmaz"
        return None
    maradek_kis = kis - nagy
    maradek_nagy = nagy - kis
    hasznalt = set()
    parok = 0
    for w in maradek_kis:
        for v in maradek_nagy:
            if v not in hasznalt and szo_kozelito(w, v):
                hasznalt.add(v)
                parok += 1
                break
    if parok == len(maradek_kis) and len(kozos) >= 1 and len(kozos) + parok >= 2:
        return "kozelito"
    return None


def emails_of(s):
    if not s:
        return set()
    return {x.strip().lower() for x in re.split(r"[,;\s]+", str(s)) if x.strip() and "@" in x}


def strip_html(s):
    if s is None:
        return None
    s = re.sub(r"<[^>]*>", "", str(s))
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def jloads_or_raw(s):
    try:
        return json.loads(s)
    except Exception:
        return {"_nyers": s}


def norm_date(s):
    """ÉÉÉÉ-HH-NN / ÉÉÉÉ.HH.NN. -> ISO dátum; különben None."""
    m = re.match(r"^\s*(\d{4})[-./\s]+(\d{1,2})[-./\s]+(\d{1,2})", str(s or ""))
    if not m:
        return None
    try:
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
    except ValueError:
        return None


def first_and_rest(lst):
    return (lst[0], lst[1:]) if lst else (None, [])


# --------------------------------------------------------------------------------------------------
# Betöltés
# --------------------------------------------------------------------------------------------------
def load(name):
    with open(BASE / name, encoding="utf-8") as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("nap", nargs="?", default="2026-10-12", help="a vérvételi nap (ÉÉÉÉ-HH-NN)")
    args = ap.parse_args()
    nap = datetime.date.fromisoformat(args.nap).isoformat()
    figyelmeztetesek = []

    adatlapok = load("adatlapok.json")
    lev_forrasok = {n: load("levelezes_%s.json" % n) for n in "ABCDEFGH" if (BASE / ("levelezes_%s.json" % n)).exists()}  # ami van
    hpn = load("hp_naptar.json")
    ertek = load("ertekeles.json")

    # ----------------------------------------------------------------------------------------------
    # LIS élő adatok (GET)
    # ----------------------------------------------------------------------------------------------
    vizsgalatok = api("vizsgalats", [("filter", "mintavetel,eq,%s" % nap), ("size", "1000")])
    assert len(vizsgalatok) < 1000
    vids = [v["id"] for v in vizsgalatok]
    karton_ids = sorted({v["karton_id"] for v in vizsgalatok})

    kartons = {}
    for ch in chunks(karton_ids, 100):
        for k in api("kartons", [("filter", "id,in," + ",".join(map(str, ch))), ("size", "1000")]):
            kartons[k["id"]] = k
    for kid in karton_ids:
        if kid not in kartons:
            figyelmeztetesek.append("karton nem található: %s" % kid)

    vdata = defaultdict(list)
    for ch in chunks(vids, 100):
        rows = api("vdata", [("filter", "vizsgalat_id,in," + ",".join(map(str, ch))), ("size", "2000")])
        assert len(rows) < 2000
        for r in rows:
            vdata[r["vizsgalat_id"]].append(r)

    vizsgs = defaultdict(list)
    for ch in chunks(vids, 100):
        rows = api("vizsgs", [("filter", "vizsgalat_id,in," + ",".join(map(str, ch))),
                              ("include", "id,vizsgalat_id,teszt_id,eredmeny,valid,lelet_id"), ("size", "5000")])
        assert len(rows) < 5000
        for r in rows:
            vizsgs[r["vizsgalat_id"]].append(r)

    teszt_ids = sorted({int(r["teszt_id"]) for rows in vizsgs.values() for r in rows if r.get("teszt_id") not in (None, "")})
    teszts = {}
    for ch in chunks(teszt_ids, 150):
        for t in api("teszts", [("filter", "id,in," + ",".join(map(str, ch))), ("include", "id,nev,csoport_id"), ("size", "1000")]):
            teszts[int(t["id"])] = t
    csoport_ids = sorted({int(t["csoport_id"]) for t in teszts.values() if t.get("csoport_id") not in (None, "")})
    csoports = {}
    for ch in chunks(csoport_ids, 150):
        for c in api("csoports", [("filter", "id,in," + ",".join(map(str, ch))), ("include", "id,nev"), ("size", "1000")]):
            csoports[int(c["id"])] = c["nev"]
    for tid in teszt_ids:
        if tid not in teszts:
            figyelmeztetesek.append("teszt_id nem található a teszts táblában: %s" % tid)

    # ----------------------------------------------------------------------------------------------
    # Páciens-váz (vizsgalats + karton + vdata + vizsgs)
    # ----------------------------------------------------------------------------------------------
    patients = []
    for vz in vizsgalatok:
        k = kartons.get(vz["karton_id"]) or {}
        szuld = k.get("szuld")
        vd_by_key = defaultdict(list)
        for r in vdata.get(vz["id"], []):
            vd_by_key[r["kulcs"]].append(r)
        for key in vd_by_key:
            vd_by_key[key].sort(key=lambda r: r["id"])
            if len(vd_by_key[key]) > 1:
                figyelmeztetesek.append("vid %s: %d db '%s' vdata sor, a legutóbbi (legnagyobb id) került be" % (vz["id"], len(vd_by_key[key]), key))

        foglalas = None
        fc_nyers = None
        if vd_by_key.get("foglalt_csomag"):
            fc_nyers = jloads_or_raw(vd_by_key["foglalt_csomag"][-1]["ertek"])
            vnid = fc_nyers.get("vnid") if isinstance(fc_nyers, dict) else None
            if isinstance(vnid, str) and vnid.strip().isdigit():
                vnid = int(vnid.strip())
            foglalas = {"vnid": vnid,
                        "csomag_nev": fc_nyers.get("nev") if isinstance(fc_nyers, dict) else None,
                        "nyers": fc_nyers}
        hp_info = jloads_or_raw(vd_by_key["hp_info"][-1]["ertek"]) if vd_by_key.get("hp_info") else None
        vdata_egyeb = [{"kulcs": r["kulcs"], "ertek": r["ertek"], "created_at": r.get("created_at")}
                       for key, rows in vd_by_key.items() if key not in ("foglalt_csomag", "hp_info") for r in rows] or None

        tesztek = []
        for r in sorted(vizsgs.get(vz["id"], []), key=lambda r: r["id"]):
            t = teszts.get(int(r["teszt_id"])) if r.get("teszt_id") not in (None, "") else None
            cs = None
            if t and t.get("csoport_id") not in (None, ""):
                cs = csoports.get(int(t["csoport_id"]))
            tesztek.append({"teszt_id": r.get("teszt_id"), "nev": t.get("nev") if t else None, "csoport": cs,
                            "eredmeny": r.get("eredmeny"), "valid": r.get("valid"), "lelet_id": r.get("lelet_id")})

        nev = " ".join(x for x in (k.get("vnev"), k.get("knev")) if x).strip()
        cim = " ".join(str(x).strip() for x in (k.get("irsz"), k.get("varos"), k.get("cim")) if x and str(x).strip())
        emails = emails_of(k.get("email"))
        if isinstance(fc_nyers, dict):
            emails |= emails_of(fc_nyers.get("email"))
        patients.append({
            "vz": vz, "k": k, "nev": nev, "tok": norm_tokens(nev), "szuld": szuld,
            "szuld_ervenyes": szuld not in ERVENYTELEN_SZULD, "emails": emails,
            "foglalas": foglalas, "hp_info": hp_info, "vdata_egyeb": vdata_egyeb, "lis_tesztek": tesztek,
            "karton_blokk": {
                "email": k.get("email"), "tel": k.get("tel"),
                "anyja_neve_megvan": bool((k.get("an") or "").strip()),
                "taj_megvan": bool((k.get("taj") or "").strip()),
                "cim": cim,
            },
            # párosítások
            "adatlap": [], "naptar": [], "hp_level": [], "levelezes": [],
        })
    patients.sort(key=lambda p: (p["vz"]["created"][11:16],
                                 int(p["vz"]["sorszam"]) if str(p["vz"]["sorszam"]).isdigit() else 10 ** 9,
                                 p["vz"]["id"]))
    by_vid = {p["vz"]["id"]: p for p in patients}

    # ----------------------------------------------------------------------------------------------
    # CSAPI (GET), foglalas.vnid szerint
    # ----------------------------------------------------------------------------------------------
    csapi_cache = {}

    def csapi(vnid):
        if vnid in csapi_cache:
            return csapi_cache[vnid]
        try:
            body = http_get(CSAPI, [("id", vnid)])
            d = json.loads(body)
            if isinstance(d, dict) and "name" in d:
                res = {
                    "csapi_id": d.get("id"),
                    "nev": d.get("name"), "ar": d.get("price"), "ehgyomor": d.get("fasting"),
                    "jelleg": d.get("field_jelleg"), "elkeszules": d.get("turnaround"),
                    "mintak": d.get("sample_types"), "megjegyzesek": d.get("special_notes"),
                    "tesztek": [{"nev": t.get("nev"),
                                 "hol": (t.get("gellert") or {}).get("hol"),
                                 "reszletek": (t.get("gellert") or {}).get("reszletek")}
                                for t in (d.get("tests") or [])],
                    "csomag_gellert": d.get("gellert"), "addons": d.get("addons"), "fetched_at": d.get("fetched_at"),
                }
            else:
                res = {"hiba": "a CSAPI nem csomagot adott vissza", "valasz": d}
        except HttpHiba as e:
            res = {"hiba": "HTTP %s" % e.status}
            if e.body:
                res["valasz"] = e.body.strip()[:300]
        except Exception as e:  # pragma: no cover
            res = {"hiba": "%s: %s" % (type(e).__name__, e)}
        csapi_cache[vnid] = res
        return res

    for p in patients:
        f = p["foglalas"]
        p["csomag"] = csapi(f["vnid"]) if f and f.get("vnid") not in (None, "") else None

    # ----------------------------------------------------------------------------------------------
    # Adatlap <-> LIS
    # ----------------------------------------------------------------------------------------------
    rekordok = adatlapok["rekordok"]
    adatlap_par = defaultdict(list)  # rekord index -> [vid]
    for idx, rec in enumerate(rekordok):
        eleje = rec.get("eleje") or {}
        a_nev = eleje.get("nev")
        a_tok = norm_tokens(a_nev)
        a_szuld = eleje.get("szuld")
        if not a_tok:
            continue
        for p in patients:
            m = name_match(a_tok, p["tok"])
            if not m:
                if p["szuld_ervenyes"] and a_szuld and a_szuld == p["szuld"] and rec.get("tipus") != "hp_beutalo":
                    figyelmeztetesek.append("adatlap '%s' (%s): a szuld egyezik a vid %s kartonjával, de a név nem (adatlap: %s, karton: %s) - nincs párosítva"
                                            % (rec["fajl"], a_szuld, p["vz"]["id"], a_nev, p["nev"]))
                continue
            if rec.get("tipus") == "hp_beutalo":
                par = "nev"
            elif p["szuld_ervenyes"]:
                if a_szuld and a_szuld == p["szuld"]:
                    par = "szuld+nev"
                else:
                    figyelmeztetesek.append("adatlap '%s': a név egyezik a vid %s kartonjával, de a szuld eltér (adatlap: %s, karton: %s) - nincs párosítva"
                                            % (rec["fajl"], p["vz"]["id"], a_szuld, p["szuld"]))
                    continue
            else:
                par = "nev"
            szuld_egyezik = (a_szuld == p["szuld"]) if (a_szuld and p["szuld_ervenyes"]) else None
            adatlap_par[idx].append(p["vz"]["id"])
            fogyo = {"fajl", "tipus", "eleje", "hata", "kert_vizsgalatok_szoveg", "bizonytalan"}
            p["adatlap"].append({
                "fajl": rec["fajl"], "tipus": rec.get("tipus"), "parositas": par,
                "parositas_reszlet": m, "kozelito": m == "kozelito",
                "karton_szuld_ervenytelen": not p["szuld_ervenyes"],
                "szuld_egyezik": szuld_egyezik,
                "nev_a_lapon": a_nev,
                "bejelolt": copy.deepcopy((rec.get("hata") or {}).get("bejelolt")),
                "egyebek_szoveg": (rec.get("hata") or {}).get("egyebek_szoveg"),
                "kezi_rairas": (rec.get("hata") or {}).get("kezi_rairas"),
                "kert_vizsgalatok_szoveg": copy.deepcopy(rec.get("kert_vizsgalatok_szoveg")),
                "eleje": copy.deepcopy(rec.get("eleje")),
                "bizonytalan": copy.deepcopy(rec.get("bizonytalan")),
                "hata_van": (rec.get("hata") or {}).get("van"),
                "tovabbi_mezok": {k: copy.deepcopy(v) for k, v in rec.items() if k not in fogyo},
            })

    # ----------------------------------------------------------------------------------------------
    # Levelezés <-> LIS (vid)
    # ----------------------------------------------------------------------------------------------
    lev_rekordok = []
    for forras, d in lev_forrasok.items():
        for r in d["paciensek"]:
            lev_rekordok.append((forras, r))
    lev_hozzarendelve = defaultdict(list)  # (forras, rekord vid) -> [vid]
    for forras, r in lev_rekordok:
        celok = [r["vid"]] + TOBBSZOROS_VID.get(r["vid"], [])
        for cel in celok:
            p = by_vid.get(cel)
            if not p:
                continue
            blokk = {k: copy.deepcopy(v) for k, v in r.items() if k != "keresesek"}
            blokk["parositas"] = "vid"
            blokk["forras_fajl"] = "levelezes_%s.json" % forras
            if cel != r["vid"]:
                blokk["rekord_vid"] = r["vid"]
                blokk["kezi_hozzarendeles"] = True
            p["levelezes"].append(blokk)
            lev_hozzarendelve[(forras, r["vid"])].append(cel)

    # ----------------------------------------------------------------------------------------------
    # Naptár <-> LIS (e-mail VAGY név)
    # ----------------------------------------------------------------------------------------------
    naptar_parositatlan = []
    event_par = {}
    for ei, ev in enumerate(hpn["naptar_hetfo"]):
        e_mail = (ev.get("email") or "").strip().lower()
        e_tok = norm_tokens(ev.get("nev"))
        email_talalat = [p for p in patients if e_mail and e_mail in p["emails"]]
        nev_talalat = {}
        for p in patients:
            m = name_match(e_tok, p["tok"]) if e_tok else None
            if m:
                nev_talalat[p["vz"]["id"]] = m
        if len(email_talalat) > 1 and e_tok:
            szukitett = [p for p in email_talalat if p["vz"]["id"] in nev_talalat]
            if szukitett:
                email_talalat = szukitett
        cel_vidok = []
        for p in email_talalat:
            cel_vidok.append(p["vz"]["id"])
        for vid in nev_talalat:
            if vid not in cel_vidok:
                cel_vidok.append(vid)
        if not cel_vidok:
            naptar_parositatlan.append(ev)
            continue
        event_par[ei] = cel_vidok
        for vid in cel_vidok:
            p = by_vid[vid]
            email_egy = bool(e_mail) and e_mail in p["emails"]
            o = copy.deepcopy(ev)
            o["parositas"] = "email" if email_egy else "nev"
            o["email_egyezik"] = email_egy
            o["nev_egyezik"] = (vid in nev_talalat) if e_tok else None
            o["kozelito"] = nev_talalat.get(vid) == "kozelito"
            if len(cel_vidok) > 1:
                o["tobb_lis_keres"] = list(cel_vidok)
            p["naptar"].append(o)
    # párosítatlan naptáresemények: csak jelzés, hogy a címben mely LIS-páciensek nevei szerepelnek (nem párosítás)
    parositatlan_ki = []
    for ev in naptar_parositatlan:
        c_tok = norm_tokens(ev.get("cim"))
        teljes, reszleges = [], []
        for p in patients:
            if len(p["tok"]) >= 2 and p["tok"] <= c_tok:
                teljes.append({"vid": p["vz"]["id"], "nev": p["nev"]})
            else:
                kozos = [t for t in p["tok"] if len(t) >= 4 and t in c_tok]
                if kozos:
                    reszleges.append({"vid": p["vz"]["id"], "nev": p["nev"], "kozos_szavak": sorted(kozos)})
        o = copy.deepcopy(ev)
        o["cimben_teljes_nev_talalat"] = teljes
        o["cimben_reszleges_nev_talalat"] = reszleges
        parositatlan_ki.append(o)

    # ----------------------------------------------------------------------------------------------
    # HP-levél <-> LIS (név)
    # ----------------------------------------------------------------------------------------------
    hp_lista = (hpn.get("hp_level") or {}).get("paciensek") or []
    hp_par = defaultdict(list)  # hp index -> [vid]
    for hi, hp in enumerate(hp_lista):
        h_tok = norm_tokens(hp.get("nev"))
        for p in patients:
            m = name_match(h_tok, p["tok"])
            if not m:
                continue
            hp_par[hi].append(p["vz"]["id"])
            o = copy.deepcopy(hp)
            o["parositas"] = "nev"
            o["parositas_reszlet"] = m
            o["kozelito"] = m == "kozelito"
            o["nap_egyezik"] = hp.get("nap") == nap
            p["hp_level"].append(o)

    # ----------------------------------------------------------------------------------------------
    # Értékelés (változtatás nélkül)
    # ----------------------------------------------------------------------------------------------
    ert = ertek.get("paciensek") or {}

    # ----------------------------------------------------------------------------------------------
    # hetfo.json
    # ----------------------------------------------------------------------------------------------
    now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    pac_ki = []
    for p in patients:
        vz, k = p["vz"], p["k"]
        ad, ad_tobb = first_and_rest(p["adatlap"])
        hl, hl_tobb = first_and_rest(p["hp_level"])
        lev, lev_tobb = first_and_rest(p["levelezes"])
        o = OrderedDict()
        o["vid"] = vz["id"]
        o["karton_id"] = vz["karton_id"]
        o["sorszam"] = vz.get("sorszam")
        o["ido"] = (vz.get("created") or "")[11:16] or None
        o["bekuldo"] = vz.get("bekuldo")
        o["lis_status"] = strip_html(vz.get("status"))
        o["nev"] = p["nev"]
        o["neme"] = k.get("neme")
        o["szuld"] = p["szuld"]
        o["szuld_ervenyes"] = p["szuld_ervenyes"]
        o["karton"] = p["karton_blokk"]
        o["foglalas"] = p["foglalas"]
        o["hp_info"] = p["hp_info"]
        o["lis_tesztek"] = p["lis_tesztek"]
        o["csomag"] = p["csomag"]
        o["adatlap"] = ad
        if ad_tobb:
            o["adatlap_tovabbi"] = ad_tobb
        o["levelezes"] = lev
        if lev_tobb:
            o["levelezes_tovabbi"] = lev_tobb
        o["naptar"] = p["naptar"]
        o["hp_level"] = hl
        if hl_tobb:
            o["hp_level_tovabbi"] = hl_tobb
        o["ertekeles"] = copy.deepcopy(ert.get(str(vz["id"])))
        if p["vdata_egyeb"]:
            o["vdata_egyeb"] = p["vdata_egyeb"]
        pac_ki.append(o)

    hetfo = OrderedDict()
    hetfo["nap"] = nap
    hetfo["keszult"] = now
    hetfo["forrasok"] = {
        "adatlapok_keszult": adatlapok.get("keszult"),
        "levelezes_keszult": {n: d.get("keszult") for n, d in lev_forrasok.items()},
        "hp_naptar_keszult": hpn.get("keszult"),
        "hp_level_szalak": (hpn.get("hp_level") or {}).get("szalak"),
        "hp_level_modositasok": (hpn.get("hp_level") or {}).get("modositasok"),
        "hp_naptar_ellenorzes": hpn.get("ellenorzes"),
        "hp_naptar_nem_sikerult": hpn.get("nem_sikerult"),
        "ertekeles_nap": ertek.get("nap"),
        "ertekeles_megjegyzes": ertek.get("megjegyzes"),
    }
    hetfo["paciensek"] = pac_ki
    hetfo["naptar_parositatlan"] = parositatlan_ki

    # ----------------------------------------------------------------------------------------------
    # kesobb.json / nem_aktualis.json
    # ----------------------------------------------------------------------------------------------
    def adatlap_osszefoglalo(rec):
        eleje = rec.get("eleje") or {}
        hata = rec.get("hata") or {}
        bej = hata.get("bejelolt") or []
        o = OrderedDict()
        o["fajl"] = rec["fajl"]
        o["tipus"] = rec.get("tipus")
        o["tipus_megj"] = rec.get("tipus_megj")
        o["nev"] = eleje.get("nev")
        o["szuld"] = eleje.get("szuld")
        o["email"] = eleje.get("email")
        o["bejelolt"] = [b.get("teszt_nev") or b.get("pdf_felirat") for b in bej]
        o["bejelolt_reszlet"] = copy.deepcopy(bej)
        o["egyebek_szoveg"] = hata.get("egyebek_szoveg")
        o["kezi_rairas"] = hata.get("kezi_rairas")
        o["kert_vizsgalatok_szoveg"] = copy.deepcopy(rec.get("kert_vizsgalatok_szoveg"))
        o["datumok_a_lapon"] = copy.deepcopy(rec.get("datumok_a_lapon"))
        o["bizonytalan"] = copy.deepcopy(rec.get("bizonytalan"))
        if rec.get("egyeb_tartalom") is not None:
            o["egyeb_tartalom"] = copy.deepcopy(rec["egyeb_tartalom"])
        return o

    def lis_kereses(rec):
        eleje = rec.get("eleje") or {}
        a_szuld = eleje.get("szuld")
        a_tok = norm_tokens(eleje.get("nev"))
        res = OrderedDict()
        if not a_szuld or not a_tok:
            res["kereses"] = "nem tortent"
            res["indok"] = "nincs szuld vagy nincs név az adatlapon"
            res["kartonok"] = []
            res["szuld_egyezik_reszleges_nev"] = []
            res["szuld_egyezik_mas_nev_db"] = 0
            res["legutobbi_kereses_mintavetel"] = None
            return res
        res["kereses"] = "kartons?filter=szuld,eq,%s" % a_szuld
        talalt = api("kartons", [("filter", "szuld,eq,%s" % a_szuld), ("size", "200")])
        kartonok, nev_nem, idegen_db = [], [], 0
        for k in talalt:
            nev = " ".join(x for x in (k.get("vnev"), k.get("knev")) if x).strip()
            m = name_match(a_tok, norm_tokens(nev))
            if not m:
                # idegen páciens neve nem kerül a fájlba, kivéve ha legalább egy (>=4 betűs) szó közös az adatlap nevével
                kozos = sorted(t for t in (a_tok & norm_tokens(nev)) if len(t) >= 4)
                if kozos:
                    nev_nem.append({"karton_id": k["id"], "nev": nev, "kozos_szavak": kozos})
                else:
                    idegen_db += 1
                continue
            vzs = api("vizsgalats", [("filter", "karton_id,eq,%s" % k["id"]), ("order", "mintavetel,desc"), ("size", "3")])
            fc = {}
            if vzs:
                for r in api("vdata", [("filter", "vizsgalat_id,in," + ",".join(str(v["id"]) for v in vzs)),
                                       ("filter", "kulcs,eq,foglalt_csomag"), ("size", "200")]):
                    if r["vizsgalat_id"] not in fc or r["id"] > fc[r["vizsgalat_id"]]["id"]:
                        fc[r["vizsgalat_id"]] = r
            keresek = []
            for v in vzs:
                nevcs = None
                if v["id"] in fc:
                    d = jloads_or_raw(fc[v["id"]]["ertek"])
                    nevcs = d.get("nev") if isinstance(d, dict) else None
                keresek.append({"id": v["id"], "mintavetel": v.get("mintavetel"),
                                "status": strip_html(v.get("status")), "foglalt_csomag_nev": nevcs})
            kartonok.append({"karton_id": k["id"], "nev": nev, "szuld": k.get("szuld"), "neme": k.get("neme"),
                             "parositas": "szuld+nev", "parositas_reszlet": m, "kozelito": m == "kozelito",
                             "legutobbi_keresek": keresek})
        res["kartonok"] = kartonok
        res["szuld_egyezik_reszleges_nev"] = nev_nem
        res["szuld_egyezik_mas_nev_db"] = idegen_db
        datumok = []
        for kt in kartonok:
            for kr in kt["legutobbi_keresek"]:
                nd = norm_date(kr.get("mintavetel"))
                if nd:
                    datumok.append(nd)
                    if nd != kr.get("mintavetel"):
                        figyelmeztetesek.append("LIS vizsgalat %s: nem-ISO mintavetel formátum (%r), a rendezéshez %s-ként értelmezve"
                                                % (kr["id"], kr.get("mintavetel"), nd))
                elif kr.get("mintavetel"):
                    figyelmeztetesek.append("LIS vizsgalat %s: értelmezhetetlen mintavetel (%r)" % (kr["id"], kr.get("mintavetel")))
        res["legutobbi_kereses_mintavetel"] = max(datumok) if datumok else None
        return res

    paros_idx = set(adatlap_par.keys())
    maradek = [(i, r) for i, r in enumerate(rekordok) if i not in paros_idx]

    kesobb_napok = defaultdict(list)
    elmult, nincs_idopont, nem_paciens = [], [], []
    tobbiek = hpn.get("naptar_tobbiek") or []

    for i, rec in maradek:
        eleje = rec.get("eleje") or {}
        a_nev = eleje.get("nev")
        a_tok = norm_tokens(a_nev)
        out = OrderedDict()
        out["adatlap"] = adatlap_osszefoglalo(rec)
        if rec.get("tipus") == "egyeb" and not a_tok:
            nem_paciens.append(out)
            continue
        # naptár (naptar_tobbiek) név szerint
        nt = []
        for e in tobbiek:
            m = name_match(a_tok, norm_tokens(e.get("keresett_nev")))
            if m:
                o = copy.deepcopy(e)
                o["parositas"] = "nev"
                o["parositas_reszlet"] = m
                o["kozelito"] = m == "kozelito"
                nt.append(o)
        nt1, nt_tobb = first_and_rest(nt)
        out["naptar"] = nt1
        if nt_tobb:
            out["naptar_tovabbi"] = nt_tobb
        # HP-levél név szerint
        hl = []
        for hp in hp_lista:
            m = name_match(a_tok, norm_tokens(hp.get("nev")))
            if m:
                o = copy.deepcopy(hp)
                o["parositas"] = "nev"
                o["parositas_reszlet"] = m
                o["kozelito"] = m == "kozelito"
                hl.append(o)
        hl1, hl_tobb = first_and_rest(hl)
        out["hp_level"] = hl1
        if hl_tobb:
            out["hp_level_tovabbi"] = hl_tobb
        # LIS
        out["lis"] = lis_kereses(rec)

        # időpont: naptár / HP-levél (a későbbi), különben a LIS legutóbbi kérése
        jeloltek = []
        for e in ([nt1] if nt1 else []) + nt_tobb:
            if e.get("talalat") and e.get("nap"):
                jeloltek.append({"forras": "naptar", "nap": e["nap"], "ido": e.get("idopont")})
            for kk, vv in e.items():
                if kk.startswith("korabbi") and isinstance(vv, list):
                    for x in vv:
                        if x.get("nap"):
                            jeloltek.append({"forras": "naptar", "nap": x["nap"], "ido": x.get("idopont")})
        for h in ([hl1] if hl1 else []) + hl_tobb:
            if h.get("nap"):
                jeloltek.append({"forras": "hp_level", "nap": h["nap"], "ido": h.get("idopont")})
        if jeloltek:
            # későbbi nap nyer; azonos napnál a naptár (forrás-sorrend: naptar < hp_level a rendezésben)
            best = max(jeloltek, key=lambda c: (c["nap"], c["ido"] or "", 1 if c["forras"] == "naptar" else 0))
            out["idopont"], out["idopont_ido"], out["idopont_forras"] = best["nap"], best["ido"], best["forras"]
        elif out["lis"]["legutobbi_kereses_mintavetel"]:
            out["idopont"], out["idopont_ido"], out["idopont_forras"] = out["lis"]["legutobbi_kereses_mintavetel"], None, "lis"
        else:
            out["idopont"], out["idopont_ido"], out["idopont_forras"] = None, None, None
        out["idopont_jeloltek"] = jeloltek
        # sorrendbe állítjuk a kulcsokat
        out = OrderedDict([(kk, out[kk]) for kk in ("adatlap", "idopont", "idopont_ido", "idopont_forras", "idopont_jeloltek",
                                                    "naptar", "hp_level", "lis") + tuple(x for x in out if x.endswith("_tovabbi"))])
        if out["idopont"] is None:
            nincs_idopont.append(out)
        elif out["idopont"] > nap:
            kesobb_napok[out["idopont"]].append(out)
        else:
            elmult.append(out)

    def rendez_kulcs(o):
        return (o["idopont_ido"] or "99:99", (o["adatlap"].get("nev") or ""))

    kesobb = OrderedDict()
    kesobb["nap_utan"] = nap
    kesobb["keszult"] = now
    kesobb["napok"] = OrderedDict((d, sorted(kesobb_napok[d], key=rendez_kulcs)) for d in sorted(kesobb_napok))
    elmult.sort(key=lambda o: (o["idopont"], o["idopont_ido"] or "99:99"))
    nem_aktualis = OrderedDict()
    nem_aktualis["nap"] = nap
    nem_aktualis["keszult"] = now
    nem_aktualis["elmult"] = elmult
    nem_aktualis["nincs_idopont"] = nincs_idopont
    nem_aktualis["nem_paciens_dokumentum"] = nem_paciens

    # ----------------------------------------------------------------------------------------------
    # Írás + ellenőrzés
    # ----------------------------------------------------------------------------------------------
    def write(name, obj):
        with open(BASE / name, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
            f.write("\n")

    write("hetfo.json", hetfo)
    write("kesobb.json", kesobb)
    write("nem_aktualis.json", nem_aktualis)

    ell = OrderedDict()
    ell["nap"] = nap
    ell["keszult"] = now
    # 1) páciensszám
    ell["paciensek_hetfo_json"] = len(pac_ki)
    ell["lis_vizsgalats_rekordok"] = len(vizsgalatok)
    ell["paciensszam_egyezik"] = len(pac_ki) == len(vizsgalatok) and sorted(p["vid"] for p in pac_ki) == sorted(vids)
    # 2) adatlap-darabszámok
    n_hetfo = len(paros_idx)
    n_kes = sum(len(v) for v in kesobb["napok"].values())
    n_el, n_nincs, n_nem = len(elmult), len(nincs_idopont), len(nem_paciens)
    ell["adatlap_rekordok"] = len(rekordok)
    ell["adatlap_hetfoba_parositva"] = n_hetfo
    ell["adatlap_kesobb"] = n_kes
    ell["adatlap_nem_aktualis"] = {"elmult": n_el, "nincs_idopont": n_nincs, "nem_paciens_dokumentum": n_nem}
    ell["adatlap_osszeg"] = n_hetfo + n_kes + n_el + n_nincs + n_nem
    # minden fájl pontosan egy helyre
    hely = defaultdict(list)
    for i in paros_idx:
        hely[rekordok[i]["fajl"]].append("hetfo")
    for d, lst in kesobb["napok"].items():
        for o in lst:
            hely[o["adatlap"]["fajl"]].append("kesobb:" + d)
    for nev_, lst in (("elmult", elmult), ("nincs_idopont", nincs_idopont), ("nem_paciens_dokumentum", nem_paciens)):
        for o in lst:
            hely[o["adatlap"]["fajl"]].append("nem_aktualis:" + nev_)
    ell["adatlap_pontosan_egy_helyen"] = (all(len(hely[r["fajl"]]) == 1 for r in rekordok)
                                          and len(rekordok) == ell["adatlap_osszeg"]
                                          and len({r["fajl"] for r in rekordok}) == len(rekordok))
    ell["adatlap_tobb_lis_keresheza_parosult"] = [
        {"fajl": rekordok[i]["fajl"], "vidok": v} for i, v in adatlap_par.items() if len(v) > 1]
    # 3) levelezés / értékelés
    ell["levelezes_rekordok"] = len(lev_rekordok)
    ell["levelezes_hozzarendelve_legalabb_egy_paciens"] = all(lev_hozzarendelve.get((f, r["vid"])) for f, r in lev_rekordok)
    ell["levelezes_nem_hozzarendelt"] = [{"forras": f, "vid": r["vid"], "nev": r["nev"]}
                                          for f, r in lev_rekordok if not lev_hozzarendelve.get((f, r["vid"]))]
    ell["levelezes_vid_ismetlodes"] = sorted({v for v in (r["vid"] for _, r in lev_rekordok)
                                              if sum(1 for _, r in lev_rekordok if r["vid"] == v) > 1})
    ell["ertekeles_kulcsok"] = len(ert)
    ell["ertekeles_minden_kulcs_letezo_vid"] = all(str(kk).isdigit() and int(kk) in by_vid for kk in ert)
    ell["ertekeles_nem_letezo_kulcsok"] = [kk for kk in ert if not (str(kk).isdigit() and int(kk) in by_vid)]
    # kiegészítő: naptár / HP-levél
    ell["naptar_hetfo_esemenyek"] = len(hpn["naptar_hetfo"])
    ell["naptar_parositott_esemenyek"] = len(event_par)
    ell["naptar_parositatlan_esemenyek"] = len(naptar_parositatlan)
    ell["naptar_tobb_lis_keresre_parosult"] = [
        {"cim": hpn["naptar_hetfo"][ei].get("cim"), "vidok": v} for ei, v in event_par.items() if len(v) > 1]
    ell["hp_level_paciensek"] = len(hp_lista)
    ell["hp_level_hetfo_vizsgalathoz_parositva"] = sorted({v for lst in hp_par.values() for v in lst})
    ell["hp_level_tobb_lis_keresre_parosult"] = [
        {"nev": hp_lista[hi].get("nev"), "vidok": v} for hi, v in hp_par.items() if len(v) > 1]
    # azonos személy több LIS-kérésben (tájékoztató, automatikus észlelés)
    dup = []
    for i, a in enumerate(patients):
        for b in patients[i + 1:]:
            if a["szuld_ervenyes"] and a["szuld"] == b["szuld"] and name_match(a["tok"], b["tok"]):
                dup.append([a["vz"]["id"], b["vz"]["id"]])
    ell["azonos_szemely_tobb_kerese_a_lis_ben"] = dup
    ell["get_kereses_szama"] = len(GET_LOG)
    ell["figyelmeztetesek"] = figyelmeztetesek

    write("ellenorzes.json", ell)

    # JSON-érvényesség (python3 -I -m json.tool)
    ervenyes = {}
    for fn in ("hetfo.json", "kesobb.json", "nem_aktualis.json"):
        r = subprocess.run([sys.executable, "-I", "-m", "json.tool", str(BASE / fn)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        ervenyes[fn] = r.returncode == 0
    ell["json_tool_ervenyes"] = ervenyes
    write("ellenorzes.json", ell)

    # ----------------------------------------------------------------------------------------------
    # Kiírás
    # ----------------------------------------------------------------------------------------------
    print("== ELLENŐRZÉS ==  nap: %s" % nap)
    print("páciensek a hetfo.json-ban: %d | LIS aznapi vizsgalats rekordok: %d | egyezik: %s"
          % (ell["paciensek_hetfo_json"], ell["lis_vizsgalats_rekordok"], ell["paciensszam_egyezik"]))
    print("adatlap-rekordok: %d | hetfo: %d + kesobb: %d + nem_aktualis(elmult %d, nincs_idopont %d, nem_paciens %d) = %d | pontosan egy helyen: %s"
          % (ell["adatlap_rekordok"], n_hetfo, n_kes, n_el, n_nincs, n_nem, ell["adatlap_osszeg"], ell["adatlap_pontosan_egy_helyen"]))
    print("adatlap több LIS-kéréshez párosult: %s" % (ell["adatlap_tobb_lis_keresheza_parosult"] or "nincs"))
    print("levelezés-rekordok: %d | mind hozzárendelve: %s | nem hozzárendelt: %s"
          % (ell["levelezes_rekordok"], ell["levelezes_hozzarendelve_legalabb_egy_paciens"], ell["levelezes_nem_hozzarendelt"] or "nincs"))
    print("ertekeles kulcsok: %d | mind létező vid: %s | nem létező: %s"
          % (ell["ertekeles_kulcsok"], ell["ertekeles_minden_kulcs_letezo_vid"], ell["ertekeles_nem_letezo_kulcsok"] or "nincs"))
    print("json.tool: %s" % ervenyes)
    print("naptár: %d esemény, párosítva %d, párosítatlan %d" % (ell["naptar_hetfo_esemenyek"], ell["naptar_parositott_esemenyek"], ell["naptar_parositatlan_esemenyek"]))
    print("GET kérések száma: %d (csak GET)" % len(GET_LOG))
    for w in figyelmeztetesek:
        print("FIGYELEM: " + w)
    print()
    print("== hetfo.json ==")
    for o in pac_ki:
        ad = o["adatlap"]
        cs = o["csomag"]
        if cs is None:
            cs_s = "nincs foglalas" if o["foglalas"] is None else "nincs vnid"
        elif "hiba" in cs:
            cs_s = "hiba: %s (vnid %s)" % (cs["hiba"], o["foglalas"]["vnid"])
        else:
            cs_s = "OK vnid %s (%d teszt)" % (o["foglalas"]["vnid"], len(cs["tesztek"]))
        print("%s | %s | %-30s | adatlap: %-28s | lev: %-3s | naptar: %d | lis_tesztek: %3d | csomag: %s | hp_level: %s"
              % (o["ido"], o["vid"], o["nev"],
                 ("igen (%s%s)" % (ad["parositas"], ", kozelito" if ad["kozelito"] else "")) if ad else "nincs",
                 "igen" if o["levelezes"] else "nem", len(o["naptar"]), len(o["lis_tesztek"]), cs_s,
                 ("igen (%s)" % o["hp_level"]["parositas"]) if o["hp_level"] else "nem"))
    print()
    print("== kesobb.json ==")
    for d, lst in kesobb["napok"].items():
        for o in lst:
            print("%s %s | %s | forras: %s | lis kartonok: %d" % (d, o["idopont_ido"] or "--:--", o["adatlap"]["nev"], o["idopont_forras"], len(o["lis"]["kartonok"])))
    print("== nem_aktualis.json ==")
    for nev_, lst in (("elmult", elmult), ("nincs_idopont", nincs_idopont), ("nem_paciens_dokumentum", nem_paciens)):
        for o in lst:
            print("%s | %s | idopont: %s (%s)" % (nev_, o["adatlap"]["nev"] or o["adatlap"]["fajl"], o.get("idopont"), o.get("idopont_forras")))


if __name__ == "__main__":
    main()
