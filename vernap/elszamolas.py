#!/usr/bin/env python3
"""
elszamolas.py — páciensenkénti elszámolás-blokk a napi JSON-ba és a kérőlap hátoldalára.

A lap és a JSON ugyanabból a függvényből kapja a szöveget: elszamolas(...)["szoveg"].
A kérőlap-kitöltő ezt importálja, nem fogalmazza meg újra.

Bemenet páciensenként (run/elszamolas.json, "paciensek" kulcs alatt, vid szerint; az árakat a számoló szál adja,
eltérés esetén már eldöntve: csomagnál a honlap, tételnél az árlista):
    {"sorok": [{"nev": "Nagyrutin plusz", "ar": 45000, "tipus": "csomag", "forras": "honlap"}, ...],
     "fuggo": [{"nev": "Omega zsírsav profil", "ar": 18000, "feltetel": "csak ha megerősítik"}],
     "nyitott": ["C3 (?)", "Vitamin K ár egyeztetendő"],
     "ok": "a kért vizsgálatok nem ismertek, ár nem számolható"}
Az adminisztrációs díjat a kód teszi hozzá (3 000 Ft, egyszer), ha van legalább egy számolható sor,
kivéve "admin_nelkul": true esetén (HP-panel: 28 000 Ft, admin díj nélkül; ha a HP fizet, 0 Ft, sorok nélkül).
A végösszeget a kód számolja.

Önteszt: python3 -I vernap/elszamolas.py
"""
import re

ADMIN_NEV = "Adminisztrációs díj"
ADMIN_AR = 3000
TIPUSOK = ("csomag", "tetel", "admin", "kedvezmeny")
FORRASOK = ("honlap", "árlista", "megadott")  # megadott: Allen adta meg (pl. HP-panel)
TILTOTT = re.compile(r"csapi", re.I)


def ft(n):
    """45000 -> '45 000'"""
    s = "{:,}".format(abs(int(n))).replace(",", " ")
    return ("-" if n < 0 else "") + s


def _sor_szoveg(s):
    nev = "adminisztrációs díj" if s["tipus"] == "admin" else s["nev"]
    return "%s %s" % (nev, ft(s["ar"]))


def elszamolas(bemenet, ar_ellenorizve):
    """bemenet: a fenti páciensenkénti dict (vagy None). Visszaad: a JSON elszamolas-blokkja."""
    b = bemenet or {}
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", ar_ellenorizve or ""):
        raise ValueError("ar_ellenorizve: ÉÉÉÉ-HH-NN kell, ezt kaptam: %r" % ar_ellenorizve)

    sorok = []
    for s in b.get("sorok") or []:
        t = s.get("tipus")
        if t not in TIPUSOK:
            raise ValueError("ismeretlen tipus: %r" % t)
        if t == "admin":
            continue  # a kód teszi hozzá, egyszer
        ar = s.get("ar")
        if not isinstance(ar, int) or isinstance(ar, bool):
            raise ValueError("az ar egész forint legyen: %r" % s)
        if t == "kedvezmeny":
            if ar >= 0:
                raise ValueError("a kedvezmény negatív: %r" % s)
        elif ar < 0:
            raise ValueError("negatív ár csak kedvezmény lehet: %r" % s)
        if s.get("forras") not in FORRASOK and t != "kedvezmeny":
            raise ValueError("forras csak honlap vagy árlista: %r" % s)
        sor = {"nev": s["nev"], "ar": ar, "tipus": t}
        if t != "kedvezmeny":
            sor["forras"] = s["forras"]
        sorok.append(sor)
    if any(s["tipus"] in ("csomag", "tetel") for s in sorok) and not b.get("admin_nelkul"):
        sorok.append({"nev": ADMIN_NEV, "ar": ADMIN_AR, "tipus": "admin"})
    elif not any(s["tipus"] in ("csomag", "tetel") for s in sorok):
        sorok = []  # kedvezmény önmagában nem számol

    fuggo = [{"nev": f["nev"], "ar": int(f["ar"])} for f in (b.get("fuggo") or [])]
    vegosszeg = sum(s["ar"] for s in sorok)

    if sorok:
        szoveg = "Elszámolás: %s = %s Ft." % (" + ".join(_sor_szoveg(s) for s in sorok).replace("+ -", "− "), ft(vegosszeg))
    else:
        szoveg = "Elszámolás: %s." % (b.get("ok") or "ár nem számolható").rstrip(".")
    for f, eredeti in zip(fuggo, b.get("fuggo") or []):
        szoveg += " %s +%s Ft, %s." % (f["nev"], ft(f["ar"]), (eredeti.get("feltetel") or "csak ha megerősítik").rstrip("."))
    for n in b.get("nyitott") or []:
        szoveg += " %s." % n.rstrip(".")

    blokk = {"szoveg": szoveg, "sorok": sorok}
    if fuggo:
        blokk["fuggo"] = fuggo
    blokk["vegosszeg"] = vegosszeg
    blokk["ar_ellenorizve"] = ar_ellenorizve
    ellenoriz(blokk)
    return blokk


def ellenoriz(blokk):
    assert blokk["vegosszeg"] == sum(s["ar"] for s in blokk["sorok"]), "a vegosszeg nem egyezik a sorok összegével"
    assert blokk["szoveg"].strip(), "üres szoveg"
    assert not TILTOTT.search(repr(blokk)), "tiltott szó az elszámolásban"
    assert sum(1 for s in blokk["sorok"] if s["tipus"] == "admin") <= 1, "admin díj többször"


if __name__ == "__main__":
    pelda = {"sorok": [{"nev": "Nagyrutin plusz", "ar": 45000, "tipus": "csomag", "forras": "honlap"},
                       {"nev": "Lp(a)", "ar": 10500, "tipus": "tetel", "forras": "árlista"}],
             "fuggo": [{"nev": "Omega zsírsav profil", "ar": 18000}]}
    e = elszamolas(pelda, "2026-10-13")
    assert e["szoveg"] == ("Elszámolás: Nagyrutin plusz 45 000 + Lp(a) 10 500 + adminisztrációs díj 3 000 = 58 500 Ft. "
                           "Omega zsírsav profil +18 000 Ft, csak ha megerősítik."), e["szoveg"]
    assert e["vegosszeg"] == 58500
    u = elszamolas(None, "2026-10-13")
    assert u["sorok"] == [] and u["vegosszeg"] == 0 and u["szoveg"] == "Elszámolás: ár nem számolható."
    n = elszamolas({"sorok": [{"nev": "TSH", "ar": 4200, "tipus": "tetel", "forras": "árlista"}], "nyitott": ["C3 (?)"]}, "2026-10-13")
    assert n["vegosszeg"] == 7200 and n["szoveg"].endswith(" C3 (?).")
    h = elszamolas({"sorok": [{"nev": "HP-panel", "ar": 28000, "tipus": "csomag", "forras": "megadott"}], "admin_nelkul": True}, "2026-10-14")
    assert h["vegosszeg"] == 28000 and h["szoveg"] == "Elszámolás: HP-panel 28 000 = 28 000 Ft."
    print("ok")
