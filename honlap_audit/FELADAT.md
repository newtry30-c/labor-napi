# Honlap csomagleírások: régi–új összevetés (gépi átírás hatása)

## Kérdés
A gellertlabor.hu csomagleírásait egy kolléga ChatGPT-vel átírta. Kérdés: hol van ennek nyoma, és a tartalom jobb vagy rosszabb lett-e. Különösen: romlott-e a kifejezések következetessége (régen ugyanaz az ember ugyanazt a szót használta az árlistában és a csomagoknál).

## Bemenet
- `adat/cscs_2026-10-12.csv` — az élő `/cscs` (https://www.gellertlabor.hu/cscs) 2026-10-12-i állapota, 223 csomag. Oszlopok: Vizsgálati csomag, Leírás (HTML), Ár (Forint), Vizsgálat jellege, ID (Drupal nid).
- `adat/cscs_regi.csv` — a gépi átírás előtti állapot. Allen teszi be; amíg nincs ott, állj meg és szólj.

Az ID a nód létrehozását mutatja, nem az átírást: régi nódot is átírtak (pl. 301, 308 bemásolás-nyomot hordoz). Ezért az átírást csak a két állapot összevetése mutatja.

## Menet
1. `python3 honlap_audit/osszevet.py honlap_audit/adat/cscs_regi.csv honlap_audit/adat/cscs_2026-10-12.csv`
   Kimenet a `honlap_audit/kimenet/` alá: `parok.json`, `valtozatok.json`, `osszesito.txt`. Ez gépi, modell nem kell hozzá.
2. A `megvaltozott` és `uj` párokat Sonnet-ügynökök értékelik, 20–30 páronként egy ügynök, párhuzamosan. Változatlan csomaggal nem foglalkozunk.
   Ügynökönként párosonként adja vissza (JSON-sor): `id`, `gepi_atiras` (biztos / valószínű / nem), `jobb_rosszabb` (jobb / rosszabb / vegyes / egyenértékű), `elveszett` (konkrétum, ami a régiben megvolt és az újból hiányzik: ár, leletidő, előkészület, mintatípus, vizsgálat), `uj_hiba` (ellentmondás, tévedésgyanú, csonka szöveg, forrásnév a páciensszövegben, üres általánosság — rövid idézettel, max 12 szó), `elnevezes_valtas` (régi kifejezés → új kifejezés ugyanarra a dologra).
   Csak a párban lévő szövegből dolgozzon; amit nem tud eldönteni, azt jelölje, ne találja ki.
3. A főszál összefésüli: `kimenet/ertekeles.jsonl`, és jelentést ír.

## Jelentés
Legfeljebb tíz számozott sor, sor elején jelölővel (fő megállapítás / átgondolandó / lezárható):
- a kifejezés-következetesség régi vs új (a `valtozatok.json`-ból: hány alak élt egy fogalomra előtte és utána, mely alakok újak),
- az elveszett konkrétumok csomaglistája,
- az új hibák csomaglistája, típus szerint,
- ahol az átírás valóban javított,
- ítélet: csomagonként és rendszerként.
Mellé egy döntési artifact: csomagonként a javasolt teendő (visszaállítás / javítás / marad), megjegyzésmezővel.

## Ami a 2026-10-12-i előfelmérésből már ismert (csak az új állomány alapján)
- U+2060 (ChatGPT-forrásjelölés maradványa) 17 csomagban: 301, 308, 811, 833, 934, 969, 1032, 1052, 1074, 1076, 1109, 1164, 1280, 1282, 1285, 1287, 1308. Forrásnév a páciensszövegben: MedlinePlus (301), NICE (308, 833, 1305), NIH (1032, 1280), WHO (934, 1074, 1109, 1280), American Thyroid Association (1280).
- Szifilisz-szerológia hatféle néven (175, 576, 88, 189, 1278, 1180); a fekélypanelek (1279, 1096) PCR-jelölés nélkül írják a Treponema pallidumot.
- Éhgyomor-alakok: „éhomi” csak 1276, 1293, 1295, 1296, 1299-ben.
- Egy csomagon belül kettős fejléc (Fontos tudnivalók + Tudnivalók): 66, 88, 92, 93, 988.
- Üres ár: 614, 620, 722, 795, 852, 1033, 1286; az 1286 leírása is üres.
- U+200B/FEFF régi szövegekben is van (Drupal/Word), ezért nem bizonyíték; az `osszevet.py` külön (`egyeb`) jelzi.
