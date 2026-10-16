# Hol tartunk (2026-10-16)

Ezt a fájlt minden munkamenet elején olvasd el: a többi munkamenet a beszélgetést nem látja, csak a repót.

## Ami változott a napi menetben (2026-10-14/15)

1. **A LIS a kiinduló, nem az adatlap-PDF.** A kérések, a sorszám, a csomag a LIS-ből jönnek; a tervező mentett állapota (a kolléganő módosításaival) a reggeli exportban (`nap_{nap}_MEGOLDATLAN.json`, `tesztek[].hatlap.mezo` = a hátlap jelölőnégyzete).
2. **Elszámolás külön szálból.** Az árakat egy másik szál (cset) számolja, és `elszamolas.json`-t ad (spec: `forgatokonyv.md` vége). A `vernap/elszamolas.py` teszi hozzá az admin díjat és a végösszeget, és ugyanez a függvény adja a lap és a JSON szövegét.
   - Admin díj 3 000 Ft, személyenként egyszer (két kérés egy embernek: a másodiknál `admin_nelkul`).
   - HP-panel: ha a páciens fizet, 28 000 Ft admin díj nélkül (`forras: megadott`); ha a HP fizet, 0 Ft.
   - Levélben adott kedvezmény (ajánlat) negatív `kedvezmeny` sorként megy be.
3. **Adatlap-megjegyzés** (`adatlap_megjegyzes`, a páciens szó szerinti ráírása) az elszámolás-fájlban jön; a betöltő az `adatlap_egyeb` végére írja. A PDF-eket itt nem dolgozzuk fel újra.
4. **A betöltő** (`vernap/betoltes/nap_betolto.php`) új változata viszi át az elszámolást (eldobja, ha a végösszeg nem egyezik) és az adatlap-megjegyzést. A szerveren még a régi futhat: le kell cserélni.
5. **Sorszámozás a LIS-ben:** naponta 20201-től időrendben (azonos időpontnál vid szerint); a HP-páciensek 20221-től, ezeket nem írjuk át. LIS-írás csak Allen kifejezett kérésére.
6. **Nyomtatandó adatlap-PDF:** az ügynök készíti, nem a régi `kerolap.py`.
   - Sablon: `gl_adatlap_jav.pdf`, az ár-mezők nélküli (kisebbik) változat. A lap aljára nem írunk árat.
   - Előlap: a beküldött eredeti, ha van; különben a LIS-kartonból. Jobb felső sarok: sorszám · időpont.
   - Hátlap: a tervező exportjának pipái; a rácson nem szereplő tétel és a pipa nélküli csomag neve az „Egyéb vizsgálat" rovatba; alatta az elszámolás 9,5 pontos félkövérrel. Az ajánlat díjsorai nem tételek.
   - HP-páciens: csak előlap, a hátlap üres oldal (kétoldalas nyomtatás). Születési dátum a beutalóról (a karton `0001-01-01`).
   - ő/ű: TrueType betűvel rajzolva; a kész PDF-ben nincs kitölthető mező.
   - A PDF-et telefonon a fájlkártya nem mindig tölti le: nézőben (render) küldve onnan menthető.

## Nyitott

- A generáló szkript még csak a munkamenet `run/` mappájában van (páciensadattal); újrahasználható, adat nélküli formában be kell tenni a `vernap/` alá.
- A sablon (`gl_adatlap_jav.pdf`) nincs a repóban; a commitot a jogosultság-ellenőrzés megfogta. Allen jóváhagyásával `vernap/sablon/` alá kerül.
- Az ambuláns árlista nem érhető el innen: tételár csak a számoló szálból jön.
- 2026-10-15 nyitott kérdései: Baranyai Dénes (mit kér), Magyar Tamás (egyedi, ismeretlen), Székely-László Ágnes (HE4/ROMA ára), Lázár Gergely (egy vagy két tenyésztés).
