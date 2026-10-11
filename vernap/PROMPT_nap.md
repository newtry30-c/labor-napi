# Napi indítás (másold be, a dátumot írd át)

Készítsd el a 2026-10-13-i vérvételi nap előkészítő fájlját a vernap/forgatokonyv.md szerint. Csatolva: az adatlap-zip és a lemondas.py kimenete.

---

## Menet (a vezénylőnek)
1. `pip install -r requirements.txt` (ha a pypdf hiányzik). Hálózat-próba: egy GET a LIS-re; ha nem megy, állj meg.
2. LIS: a nap kérései (`vizsgalats?filter=mintavetel,eq,{nap}`) és kérésenként a vdata. Akinél már van `kulcs=elokeszites`, az kimarad. A többi az új.
3. `python3 -I vernap/adatlap_kiolvas.py <adatlap.zip>` → `run/adatlapok.json`.
4. Lemondás és nem felvett foglalás: a csatolt lemondas.py-kimenetből. Ha nincs csatolva, add meg Allennek a parancsot: `python3 ~/Downloads/lemondas.py {nap}` (a lemondas.py a repó vernap/ mappájából tölthető le).
5. Levelezés: Sonnet-ügynökök, legfeljebb 5 új páciens ügynökönként, a vernap/brief_levelezes.md szerint → `run/levelezes_A.json`, `_B` … HP-páciensnél levelezés-keresés nincs, csak a legutóbbi hairpalace.fr levél.
6. Naptár: csak a célnap eseményeinek címe, eseményenként `megjegyzes_tipus` → `run/hp_naptar.json` (`naptar_hetfo` kulcs alatt; a név történeti).
7. `python3 -I vernap/osszefesul.py {nap}` → értékelés (`run/ertekeles.json`, `paciensek` kulcs alatt, vid szerint) → újra `osszefesul.py {nap}`.
8. A kimenetből csak az új kérések: `run/nap_{nap}.json`; mellé `run/kesobb.json`, `run/nem_aktualis.json`; a három egy zipben, letölthetően.
9. Jelentés (max. 10 számozott sor) + a betöltés parancsai Allen Macére:
   `_snapshots/napelokeszito-20261011/betoltes.sh ~/Downloads/nap_{nap}.json` (száraz), majd ugyanez `--go`, a végén `betoltes.sh --torol`.

Az értékelés szabályai a forgatókönyv végén: egy tétel = egy vizsgálat a kérőlap cellájának feliratával; `tipus` (vizsgalat | csomag | dij | megjegyzes); utaló mondat tilos; kérdés oka az `egy_sor`-ban; labort, csövet nem döntesz el; a LIS-be nem írsz.
