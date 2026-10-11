#!/usr/bin/env python3
"""Adatlap-mappa (zip vagy könyvtár) kiolvasása run/adatlapok.json-ba, render és képnézés nélkül.

Futtatás:  python3 -I vernap/adatlap_kiolvas.py <adatlap.zip | mappa>
Kitölthető PDF: mezőértékek, bejelölt checkboxok (/0 és Igen is bejelölt), nem-widget annotációk
(FreeText szövege a /Contents-ből). Mező nélküli PDF: "egyeb" (pl. önéletrajz) vagy "szkennelt"
(ezt oldalanként egyszer képként kell elolvasni).
"""
import json, logging, pathlib, re, sys, tempfile, zipfile
from pypdf import PdfReader

logging.disable(logging.CRITICAL)
REPO = pathlib.Path(__file__).resolve().parent.parent
MAP = json.load(open(pathlib.Path(__file__).with_name("checkbox_map.json"), encoding="utf-8"))
ELEJE = {"tnev": "nev", "szuld": "szuld", "email": "email", "telsz": "tel", "an": "anyja_neve",
         "taj": "taj", "lakhely": "lakhely", "mintavetel": "mintavetel_a_lapon", "bekuldo": "bekuldo"}
URES = {None, "", "-", "/Off", "Off"}


def norm_datum(s):
    d = re.findall(r"\d+", s or "")
    if len(d) >= 3 and len(d[0]) == 4:
        return "%s-%02d-%02d" % (d[0], int(d[1]), int(d[2]))
    if len(d) == 1 and len(d[0]) == 8:
        return "%s-%s-%s" % (d[0][:4], d[0][4:6], d[0][6:])
    return s


def egy(f):
    r = PdfReader(str(f))
    fl = r.get_fields() or {}
    rec = {"fajl": f.name, "tipus": "adatlap", "eleje": {},
           "hata": {"van": False, "bejelolt": [], "egyebek_szoveg": None, "kezi_rairas": None},
           "kert_vizsgalatok_szoveg": None, "datumok_a_lapon": [], "bizonytalan": []}
    if not fl:
        szoveg = (r.pages[0].extract_text() or "")[:2000]
        if re.search(r"adatlap|vizsgálat|anyja", szoveg, re.I):
            rec["tipus"] = "szkennelt"
            rec["bizonytalan"].append("nincs kitölthető mező: oldalanként egyszer képként elolvasandó")
        else:
            rec["tipus"] = "egyeb"
            rec["tipus_megj"] = "nem páciens-dokumentum (mező nélküli PDF)"
        return rec
    egyeb = {}
    for k, v in fl.items():
        val = v.get("/V")
        if isinstance(val, dict) or val in URES:
            continue
        val = str(val)
        if k in ELEJE:
            rec["eleje"][ELEJE[k]] = val.strip()
        elif k == "egyebek":
            rec["hata"]["egyebek_szoveg"] = val
        elif k.startswith("Check Box"):
            rec["hata"]["bejelolt"].append({"mezo": k, "teszt_nev": MAP.get(k), "ertek": val, "biztos": k in MAP})
            if k not in MAP:
                rec["bizonytalan"].append("bejelölt mező a térképen kívül: %s" % k)
        elif k == "BK":
            egyeb["fizetes"] = "bankkártya"
        else:
            egyeb[k] = val.strip()
    e = rec["eleje"]
    if e.get("szuld"):
        e["szuld"] = norm_datum(e["szuld"])
    if e.get("mintavetel_a_lapon"):
        rec["datumok_a_lapon"].append(e["mintavetel_a_lapon"] + " (mintavétel)")
    taj = re.sub(r"\D", "", e.pop("taj", ""))
    e["taj_megvan"] = len(taj) == 9
    if taj and len(taj) != 9:
        rec["bizonytalan"].append("a taj mező nem 9 számjegy")
    e["an_megvan"] = bool(e.get("anyja_neve"))
    rec["hata"]["van"] = bool(rec["hata"]["bejelolt"] or rec["hata"]["egyebek_szoveg"])
    rec["eleje_egyeb"] = egyeb
    for i, p in enumerate(r.pages):
        for a in (p.get("/Annots") or []):
            a = a.get_object()
            st = a.get("/Subtype")
            if st in ("/FreeText", "/Stamp", "/Ink"):
                rec["bizonytalan"].append("%d. oldal %s annotáció: %r" % (i + 1, st[1:], a.get("/Contents")))
    return rec


def main():
    src = pathlib.Path(sys.argv[1])
    if src.suffix.lower() == ".zip":
        tmp = tempfile.mkdtemp()
        zipfile.ZipFile(src).extractall(tmp)
        src = pathlib.Path(tmp)
    rek = [egy(f) for f in sorted(src.rglob("*.pdf"))]
    out = REPO / "run"
    out.mkdir(exist_ok=True)
    json.dump({"rekordok": rek}, open(out / "adatlapok.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for x in rek:
        print("%-10s | %-28s | %s | iksz: %d | egyéb: %s" % (x["tipus"], (x["eleje"].get("nev") or "")[:28],
              x["eleje"].get("szuld") or "-", len(x["hata"]["bejelolt"]), "igen" if x["hata"].get("egyebek_szoveg") else "-"))


if __name__ == "__main__":
    main()
