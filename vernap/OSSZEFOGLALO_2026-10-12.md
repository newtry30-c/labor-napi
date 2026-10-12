# Összefoglaló a keddi (10-13) előkészítésről — mi a technikai baj

## Mi történt
Egy egész este ment el egy olyan napra, amit kézzel kb. 20 perc alatt meg lehet csinálni. A kimenet (betölthető JSON) végül bekerült, de reggelre nem lett belőle használható papír: se ár, se címke, se teljes adatlap-kép.

## A technikai problémák

1. **Rossz kiindulópont.** A folyamat a LIS-listából és a letöltött adatlap-zipből indul. Az igazi jelzés a naptár: a lila szín (Google colorId 3) jelenti, hogy van adatlap. Ezt a naptár-ügynök kigyűjtötte, de a folyamat nem használta. Keddre 6 lila volt, ebből 2 adatlapja hiányzott a zipből.
2. **A zip időablakos.** Csak a legutóbbi napok adatlapjait hozza; a régebben beküldöttek kimaradnak (ez az első futáskor is kiderült, mégsem lett javítva).
3. **Rossz levelezés-forrás.** A Gmail MCP-ből csatolmány nem tölthető le, a labor kimenő levelei (ajánlatok, árak) nincsenek benne, csak idézetben. Közben a teljes levelezés IMAP-pal már a saját szerveren van, a csatolmányokkal együtt. Ezt a folyamat nem ismeri: nincs a CLAUDE.md-ben, nincs hozzáférés a felhős munkamenetből.
4. **Ár nincs a kimenetben.** A csomagár a CSAPI-ban megvan, az ajánlat összege a levélben; a betöltő a `fizet` mezőt szándékosan eldobja. Reggel kézzel, tollal kellett ráírni.
5. **A kimenet nem a reggeli igényre szól.** A JSON a Nap előkészítő oldalnak készül; nyomtatható napi lap és címke nem készül belőle.
6. **Minden kör a Macen megy át.** Lemondás (API-kulcs), betöltés (ssh) csak Allen gépéről; minden lépés másolás-beillesztés oda-vissza.
7. **Egész napos újrafuttatás.** Lemondás vagy új foglalás után az egész lánc újra; a kérésenkénti (delta) működés csak félig van meg.
8. **Törékeny párosítás.** A betöltő pontos rács-feliratot vár; a tételnevek nem egyeztek, másodpéldányok és párosítatlan adatlap miatt kézi javítás és újrafeltöltés kellett.
9. **Szétszórt tudás.** A szabályok promptokban, skillekben, scriptekben vannak, minden munkamenet újra felfedezi vagy újragenerálja őket (ugyanaz a minta, mint a CSAPI-nál). A fontos tényeket (lila = adatlap, IMAP a szerveren, sorszám) senki nem írta le egy helyre.

## Mire jutottunk (javaslat, sorrendben)
1. **Forrás:** naptár (szín + cím) és a szerveren lévő IMAP-postafiók (adatlap-csatolmányok közvetlenül), nem a Gmail és nem a zip.
2. **Kimenet:** egy nyomtatható napi lap (idő, név, kért tételek, ár, adatlap van/nincs, nyitott kérdés) és címkék; a vdata-betöltés másodlagos.
3. **Ár:** CSAPI-csomagár + a levélbeli ajánlat összege, minden páciensnél.
4. **Futás:** a szerveren, a LIS-beolvasáshoz kötve, kérésenként; változásnál csak az érintett kérés fut újra, és jelzés megy a kártyára.
5. **Tudás egy helyen:** a fenti tények a forgatókönyvbe/CLAUDE.md-be, hogy ne kelljen újra kitalálni.
