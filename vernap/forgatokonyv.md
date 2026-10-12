# Vérvételi nap előkészítése — ügynök-forgatókönyv

Cél: a következő vérvételi nap minden páciensére egy helyen álljon, hogy jön-e, mit kér, mennyit fizet, és mi a teendő vele. Négy forrásból áll össze: LIS, beküldött adatlapok, levelezés, naptár (+ HP heti levél).

Első futás: 2026-10-10/11, a 2026-10-12-i (hétfő) napra. Munkakönyvtár: `hetfo_1012/`.

## Szereposztás

| Szál | Ki | Bemenet | Kimenet |
|---|---|---|---|
| 0. Vezénylés, értékelés | nagy modell | minden kimenet | `ertekeles.json`, kérdések |
| 1. Adatlap-kiolvasás | olcsó modell, 1 ügynök | adatlap-mappa (zip) | `adatlapok.json` |
| 2. LIS napi lista | script (`osszefesul.py`) | LIS API, CSAPI | a `hetfo.json` LIS- és csomagrésze |
| 3. Levelezés-keresés | olcsó modell, 3–4 páciens/ügynök, párhuzamosan | `brief_levelezes.md` + pácienslista | `levelezes_*.json` |
| 4. HP-levél + naptár | olcsó modell, 1 ügynök | Gmail, Online előjegyzések naptár | `hp_naptar.json` |
| 5. Összefésülés | script (`osszefesul.py {dátum}`) | 1–4 kimenete + `ertekeles.json` | `hetfo.json`, `kesobb.json`, `nem_aktualis.json`, `ellenorzes.json` |

Az 1., 3., 4. szál egymástól független, párhuzamosan fut. A 3. szál pácienslistájához a 2. szál LIS-listája kell (név, e-mail, foglalt csomag, időpont), ezért a LIS-lista lekérése az első lépés. Az olcsó modell sehol nem dönt: kiolvas, keres, szó szerint idéz. Az értékelés (jön-e, végső kérés, kérdés) a vezénylő dolga, a négy forrás együttes olvasatából.

## Sorrend

1. LIS: `vizsgalats?filter=mintavetel,eq,{nap}` + kartonok + `vdata` (foglalt_csomag, hp_info) + `vizsgs`. Ebből lesz a pácienslista.
2. Párhuzamosan indul az 1., a 3. és a 4. szál.
3. `osszefesul.py {nap}` — első futás értékelés nélkül.
4. A vezénylő páciensenként megírja az értékelést (`ertekeles.json`, kulcs a kérés-azonosító): `allapot` (rendben / kerdes / nem_jon), `egy_sor`, `vegso_keres` (tétel + forrás), `fizet`, `kerdes`, `teendo`.
5. `osszefesul.py {nap}` újra: az értékelés bekerül a `hetfo.json`-ba.
6. Szúrópróba a forrásokkal szemben; a `kerdes` állapotúak mennek emberi döntésre.

## Tárolás

- `hetfo.json` — a nap páciensei időrendben; páciensenként forrásonként külön blokk (`foglalas`, `lis_tesztek`, `csomag`, `adatlap`, `levelezes`, `naptar`, `hp_level`) és az `ertekeles`. A források nyers tartalma változatlan, az értékelés külön áll.
- `kesobb.json` — adatlapok, amelyek gazdája a nap után jön, napok szerint.
- `nem_aktualis.json` — már elmúlt időpontú, időpont nélküli, illetve nem páciens-dokumentum.
- A LIS-ben a kérés a `vizsgs` sorokban él (`eredmeny: "folyamatban"`); ebből nyomtatja a program a partnerlabor-kérőlapokat. A kérés oldalán a Választó „Gellért kérőlap” füle a papír hátoldal rácsát követi.

## Szabályok a szálaknak

Adatlap-kiolvasás
- Minden fájlról egy rekord, az eleje és a háta is; a szabadszöveges rovatok szó szerint.
- Kitölthető (AcroForm) PDF: kizárólag az adatmodellből, script olvassa (mezőértékek, bejelölt checkboxok, a nem-widget annotációk listája). Render, képnézés, pixel-összevetés tilos. Modell csak akkor néz rá, ha a script annotációt (Stamp, FreeText, Ink) vagy V/AS ellentmondást jelez, és akkor is csak arra az oldalra.
- Szkennelt vagy lefotózott lap: oldalanként egy képolvasás, sávozás és ellenőrző újraolvasás nélkül.
- A bejelölt checkbox állapota lehet `/0` is, nem csak `Igen` (iOS/PDFium mentés). Az `/Opt` és a megjelenítési állapot együtt dönt; ellentmondásnál `biztos: false`.
- A mappa fájlneveiben nincs e-mail-cím, csak `HH_NN_ÉÉÉÉ_[Küldő neve]_` előtag. Párosítás: születési dátum + név.
- A `gl_adatlap_jav` checkbox-megfeleltetése a `laborvizsg_adatlap_gellertmedical.pdf` 148 mezőjére is érvényes.

Levelezés-keresés
- A postafiók mindent fogad, a labor kimenő levelei nincsenek benne; a labor válasza a páciens levelének idézetében kereshető.
- Keresés e-mail-címre (from, to, bárhol) és névre mindkét sorrendben. A levelező cím eltérhet a kartonétól.
- A foglalási értesítők gyűjtőszálakba kerülnek, és nincs bennük e-mail-cím: névre kell kötni.
- Csatolmány nem tölthető le; a szöveg nélküli, csak csatolmányos válasz (kép, PDF) külön jelzendő, mert kézzel kell megnyitni.
- Ugyanarra a névre két foglalási értesítő ugyanarra a napra: külön jelzendő.

HP-levél + naptár
- A heti levél nem mindig csütörtökön jön: a legutóbbi `hairpalace.fr` levelet kell venni, és az azóta érkezett módosításokat.
- Naptár: amelyik esemény kezdőnapja nem a célnap, eldobandó; belépési adatot tartalmazó esemény nem idézhető.
- A naptárból csak időpont, cím, név, csomag, e-mail, szín kerül át; telefon, lakcím, születési dátum nem.
- Az esemény címe kézi megjegyzést hordozhat (összeg, „e-mail szerint”, csomagnév) — ez a kolléganő tudása, forrásként kezelendő.

Összefésülés
- Csak GET. A LIS felé a kapcsolat időnként megszakad, újrapróbálás kell.
- Névegyeztetés: ékezet és sorrend nélkül, részhalmaz-egyezéssel; a közelítő találat jelölve.
- `vdata.foglalt_csomag` minden kérésre lekérendő, a felvett tesztek számától függetlenül.

## Amit az első futás megmutatott

- A foglalt csomag önmagában öt páciensnél nem mondta meg a kérést (saját összeállítás, kézi időpont). Ezeknél az adatlap hátoldala, a levélbeli ajánlat vagy a naptárbejegyzés címe volt a forrás.
- Lemondás levélben, a LIS-ben még élő kéréssel: a levelezés-szál nélkül nem derül ki.
- Kétszer felvett páciens (áttett foglalás → két karton, két kérés): a levelezés mutatja meg, hogy egy foglalás van.
- Két foglalás egy névre, a LIS-ben csak az egyik.
- HP-kartonok születési dátuma `0001-01-01`, miközben a beutalón szerepel.
- Az adatlap-mappa letöltése időablakos: a korábban beküldött adatlap kimarad, pedig a levelezés szerint megérkezett.

## Amit a betöltés és a hétfői használat megmutatott (2026-10-11)

A `hetfo.json`-t a `nap_betolto.php` tölti a Nap előkészítő oldalba. A betöltő CSAK ezeket olvassa: `vid`, `nev`,
`adatlap` (bejelolt, egyebek_szoveg, kezi_rairas, kert_vizsgalatok_szoveg), `ertekeles.allapot`, `ertekeles.egy_sor`,
`ertekeles.vegso_keres`, `levelezes.arajanlat.tetelek`, `naptar[].cim`. Minden más blokk háttér az embernek.
A labort, a csövet, a nyilatkozatot és a csomag tartalmát az oldal maga oldja fel élőben (nap_labor_szabalyok.json,
nap_csomag_nevek.json, útmutató) — a vezénylő ezeket NE döntse el, tiszta tétellistát adjon.

### A `vegso_keres` szabályai (ez a legfontosabb)
- **Egy tétel = egy vizsgálat.** A hétfői 27 tételből 12 összetett volt („HP-panel (vérkép, CRP, INR…)”): ezek festetlenül,
  cső nélkül az „Egyéb vizsgálatok” közé kerültek. A panelt elemeire kell bontani.
- **A tétel neve a kérőlap cellájának pontos felirata, ahol van ilyen cella.** A betöltő csak pontos egyezést fogad el
  (kis-/nagybetű és szóköz eltérés belefér, hasonló név nem elég). A feliratok: a kérés oldalán a Választó „Gellért kérőlap” füle.
- **A lista önmagában teljes.** Utaló mondat tilos („az ajánlat 17 sora + …”): az ajánlat sorait az oldal díjsorként,
  NEM mintaként kezeli, tehát ami csak az ajánlatban szerepel, ahhoz nem kér csövet senki. Amit a páciens az ajánlatból
  kér, az tételenként kerüljön a `vegso_keres`-be is.
- **Csomagnév nem tétel** (hétfőn 3 ilyen volt; az oldal olvasáskor kihagyja). A csomag a `foglalas`/`csomag` blokkban van.
- Új mező tételenként: `tipus` = `vizsgalat` | `csomag` | `dij` | `megjegyzes`. A betöltő csak a `vizsgalat` típust (és a
  típus nélkülit) veszi fel tételnek.

### Szövegek
- `fizet`, `teendo`, `kerdes`: a betöltő nem viszi át (Allen: AI-szöveg nem kell a cetlire). Hétfőn kb. 3200 karakter
  készült fölöslegesen. Legfeljebb rövid, tényszerű jegyzet a háttérhez.
- `kerdes` állapotnál a kérdés oka most CSAK az `egy_sor`-ból látszik a felületen: ott álljon egy rövid, tényszerű
  mondatban, mi a kérdés. (Hogy legyen-e külön helye a felületen: Allen döntésére vár.)
- Szóhasználat: „Egyéb vizsgálatok” (nem „rácson kívül”); „fixátum”, „CSAPI” páciens-szövegbe nem kerül.

### Naptár, adatlap, karton
- A naptár címében a név utáni szöveg (hétfőn 15-ből 11 páciensnél) válogatás nélkül tétel lett. Új mező eseményenként:
  `megjegyzes_tipus` = `vizsgalat` | `osszeg` | `megjegyzes`; a betöltő csak a `vizsgalat` típust (és a típus nélkülit)
  veszi fel tételnek.
- Szkennelt/fotózott adatlapnál nincs mezőnév (hétfőn 9 ikszből 2): a `teszt_nev` a papír nyomtatott felirata legyen
  betűre pontosan, mert a betöltő ebből találja meg a cellát.
- HP-kartonok születési dátuma `0001-01-01`: a beutalóról kiolvasott dátum kerüljön a fájlba külön mezőben
  (`szuld_beutalo`). A „visszatérő” jelző csak TAJ vagy születési dátum alapján áll, név alapján soha.

### Betöltés
- `_snapshots/napelokeszito-20261011/betoltes.sh <fájl>` → száraz futás; `--go` csak ott ír, ahol még nincs mentett
  előkészítés; `--go --felulir` a kolléganő kézi munkáját is eldobja. A végén `--torol`.
- A nap a fájlban lévő `vid`-ekből adódik, a fájlnév mindegy.

## Napi újrafuttatás (2026-10-11 este, a hétfő második köre)

- **Ki új:** a LIS napi listája, és a `vdata`-ban `kulcs=elokeszites` megléte kérésenként. Akinek már van mentett előkészítése, azzal nem foglalkozunk; az előző fájl nem kell hozzá. Hétfőn így 16-ból 1 maradt (Rusvai Katalin, #29270).
- **Lemondás, új foglalás:** a foglalási adatbázisból (`lemondas.py`, Allen futtatja helyben; a kulcs nem hagyja el a gépét). A Google Naptárból csak az esemény címe jön át, eseményenként `megjegyzes_tipus`-szal; a címben álló csomagnév `megjegyzes`, nem tétel.
- **Lemondott, majd újra foglalt páciens:** ha a levél lemondást mond, a LIS-ben mégis élő kérés van, a foglalási adatbázis dönt. Ha onnan nincs adat, `kerdes` állapot, az ok az `egy_sor`-ban.
- **Nem páciens-dokumentum** az adatlap-mappában (pl. önéletrajz): `tipus: "egyeb"`, `nem_aktualis.json`, kiolvasás nélkül.
- **Adatlap-kiolvasás:** pypdf-script, mezőértékek + nem-widget annotációk; a FreeText annotáció szövege a `/Contents`-ből olvasható, render nélkül.
- **osszefesul.py:** a `levelezes_*.json` fájlok közül azt veszi, ami létezik (A–H); a `TOBBSZOROS_VID` üres. Az értékelés a `ertekeles.json` `paciensek` kulcsa alatt áll. A kimenetből az új kérések külön fájlba szűrhetők (`nap_{nap}_uj.json`).
- **Tapasztalat:** a fájlnévben álló küldő neve nem mindig a páciensé (10-11: Kertész Antónia küldte Jánoczki Ádám Csaba adatlapját). A párosítás a lap eleje alapján megy.

## A kedd előkészítése (2026-10-12) — tanulságok

- **A LIS-felvétel előfeltétel.** A folyamat a LIS napi listájából indul; ha a célnapra 0 kérés van, előbb Allen behívja a foglalásokat a LIS-be (az időpontfoglalóból), csak utána fut a többi szál. A levélben vagy kézzel egyeztetett páciensek a naptárban vannak, ezért a naptárral mindig össze kell nézni.
- **Első `osszefesul.py` futás:** kell egy üres `run/ertekeles.json` (`{"paciensek":{}}`), különben a script elhasal. A futás 2–5 perc (LIS-hívások); háttérfeladatként kell indítani, nem `nohup &`-pal.
- **A `vegso_keres` és a rács:** a betöltő a `vegso_keres` tételét csak pontos rács-feliratra párosítja, a `checkbox_map.json` `teszt_nev`-je ennek nem mindig felel meg. Az adatlapon ikszelt tételt ezért NEM kell a `vegso_keres`-be ismételni (az adatlap-blokk a mezőnévvel a rácsra viszi); ismételve „egyéb vizsgálat” másodpéldány lesz.
- **Párosítatlan adatlap** (pl. a név a születési dátum mezőbe került): az adatlap-blokkot kézzel kell a páciens rekordjába tenni (`parositas: "kezi"`), különben az ikszelt tételek nem kerülnek a rácsra.
- **Naptár-cím mint tétel:** ha a vezénylő a címből külön tételeket ír a `vegso_keres`-be, az eseményt `megjegyzes`-re kell állítani, különben a cím összefűzött maradéka még egy tételként bejön. A címben álló csomagnév mindig `megjegyzes`.
- **Ajánlat-sorok:** a betöltő a `levelezes.arajanlat.tetelek` minden sorát „egyéb vizsgálatként” felveszi; összetett sort (pl. „small routine panel (CBC, CRP…)”) ki kell venni, a ténylegesen kért tétel a `vegso_keres`-be megy.
- **Mindig száraz futás előbb**, és a számokat (rács / egyéb) össze kell vetni a várttal. A letöltött zip neve ütközhet (`… (1).zip`): a legfrissebbet kell kicsomagolni.

## Sorszám (Allen, 2026-10-12)

- A Gellért Medical saját kérései 20201-től, a partnerek kérései 20221-től kapnak sorszámot; naponta újraindul.
- A sorszám azt jelzi a kollégáknak, hogy a nap feldolgozása elindult (nem az érkezés sorrendje).
- Sorrend: időpont szerint; az együtt érkező párok/családtagok egymás után.
- A lemondott foglalás törlődik, sorszámot nem kap.
- A sorszámot Allen kézzel adja; a vezénylő legfeljebb javasolt listát ad, a LIS-be nem ír.
