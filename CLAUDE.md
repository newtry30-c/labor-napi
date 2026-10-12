# labor-napi — Gellért Medical Labor napi operatív munkái

Ez a repó a napi adatmunka helye (vérvételi nap előkészítése, naptár–LIS egyeztetés, lemondások, HP-hét).
A LIS kódja nem itt van (az a listools repó). Mindig magyarul válaszolj.

## Állandó szabályok
- LIS felé alapból csak GET. Írás (POST/PUT/DELETE) csak akkor, ha Allen az adott feladatban kifejezetten kéri.
- Valódi páciensadat (adatlap, levelezés, napi JSON, lemondás-kimenet) soha nem kerül commitba: minden ilyen a `run/` mappában él (gitignore).
- A LIS-be írt adatban soha nincs modellnév; kézi/ügynöki beírásnál `mod: "kezi"`.
- Modell: Sonnet, kevés effort. Tömeges kiolvasás/keresés Sonnet-ügynökre megy, a főszál vezényel. Opus nem kell.
- PDF/adatlap: csak mezőszintű kiolvasás (vernap/adatlap_kiolvas.py). Render, képnézés, pixel-összevetés tilos; képként csak a mező nélküli, szkennelt lapot olvasd, oldalanként egyszer.
- Foglalás és lemondás forrása az adatbázis (vernap/lemondas.py kimenete), nem a Google Naptár. A naptárból csak az esemény címében álló kézi megjegyzés jön át; telefon, lakcím, születési dátum nem.
- A Gmail-fiók mindent fogadó technikai fiók: csak olvasás; a labor kimenő levelei nincsenek benne, a válasz a páciens levelének idézetében kereshető. Csatolmány nem tölthető le.
- Egy menet: forrásonként egy olvasás, ellenőrző újraolvasás nélkül.
- Jelentés: legfeljebb tíz számozott sor, a sor elején jelölővel (fő megállapítás / átgondolandó / lezárható). Nagy számdobozok, összesítő csempék nincsenek.
- Ha egy eszköz (Gmail, naptár, hálózat) nem érhető el: állj meg és mondd meg; kerülőutat ne keress.

## Gépek, hostok
- LIS REST API (nyitott, kulcs nélkül): `https://a.gellertlabor.hu/api/api.php7/records/` — vizsgalats, kartons, vdata, vizsgs, vizsgalat_folyamatban.
- CSAPI: `https://a.gellertlabor.hu/p8/csapi/public/api.php`
- Foglalási adatbázis API: `https://api.gellertlabor.hu/api/index.php/records/wp_cpabc_appointments` — `X-API-Key` fejléccel. A kulcs CSAK Allen Macén van: `~/GL_LIS/…/l20/api/index.php` (`apiKeyAuth.keys`). Te nem olvasod, nem kéred el, nem írod ki.
- Webszerver SSH: `zygjid@gellertlabor.hu` (Allen Macén az alapértelmezett ssh-kulccsal megy, külön `-i` nélkül). Docroot: `~/wwwroot/l`; PHP: `/opt/alt/php83/usr/bin/php`; betöltés-fájlok: `~/nap-betoltes/` (futás után törlendő).
- A szerver sűrű ssh-kapcsolatnál visszautasít: néhány perc szünet, utána újra.

## Ha valamit innen nem érsz el (kulcs, ssh, Allen gépe)
Ne próbálkozz tovább. Írd meg helyette Allennek úgy, hogy csak be kelljen másolnia a Mac termináljába:
1. A teendőt egy scriptbe írd a repóban (`vernap/` vagy `run/` alá, ha páciensadat van benne), amit Allen letölt.
2. Adj EGYETLEN parancsot, idézőjelek és többsoros szerkezet nélkül (a chat okos idézőjelekre cseréli és összetöri a sortöréseket), pl. `python3 ~/Downloads/lemondas.py 2026-10-13`.
3. Mondd meg, mit másoljon vissza a kimenetből.
A kulcs soha ne hagyja el Allen gépét: a script helyben olvassa be, és csak az eredményt írja ki.

## Feladatok
- `vernap/` — vérvételi nap előkészítése. Eligazítás: `vernap/forgatokonyv.md`; a napi indítás: `vernap/PROMPT_nap.md`.
- `honlap_audit/` — honlap csomagleírások régi–új összevetése (gépi átírás hatása). Eligazítás: `honlap_audit/FELADAT.md`.
