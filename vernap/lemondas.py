#!/usr/bin/env python3
# Egy nap lemondasai + LIS nevsor osszevetes. Futtatas: python3 lemondas.py 2026-10-13 A kulcsot a helyi l20/api/index.php-bol olvassa, nem irja ki.
import glob, json, os, re, sys, urllib.parse, urllib.request

if len(sys.argv) < 2 or not re.match(r"^\d{4}-\d{2}-\d{2}$", sys.argv[1]):
    sys.exit("Add meg a napot: python3 lemondas.py 2026-10-13")
NAP = sys.argv[1]
home = os.path.expanduser("~")

cands = []
if len(sys.argv) > 2 and os.path.isfile(os.path.expanduser(sys.argv[2])):
    cands = [os.path.expanduser(sys.argv[2])]
if not cands:
    SKIP = {"Library", ".Trash", "node_modules", ".git", "venv", ".cache", "Movies", "Music", "Pictures", "Applications"}
    for root, dirs, files in os.walk(home):
        dirs[:] = [d for d in dirs if d not in SKIP]
        if "index.php" in files and root.replace(os.sep, "/").endswith("l20/api"):
            cands.append(os.path.join(root, "index.php"))
            break
if not cands:
    sys.exit("Nem talalom az l20/api/index.php fajlt a home mappaban. Add meg utvonalkent: python3 lemondas.py 2026-10-13 /ut/az/index.php")
print("Kulcs forrasa:", cands[0])
src = open(cands[0], encoding="utf-8", errors="replace").read()
m = re.search(r"apiKeyAuth\.keys'\s*=>\s*'([0-9a-f]{32})", src)
if not m:
    sys.exit("Nem talalom a kulcsot az index.php-ben.")
key = m.group(1)

def get(url, params, headers=None):
    req = urllib.request.Request(url + "?" + urllib.parse.urlencode(params), headers=dict({"User-Agent": "Mozilla/5.0"}, **(headers or {})))
    return json.load(urllib.request.urlopen(req, timeout=30))

lis = get("https://a.gellertlabor.hu/api/api.php7/records/vizsgalat_folyamatban",
          {"filter": "mintavetel,eq," + NAP, "include": "sorszam,full_name,bekuldo"})["records"]

foglalasok = get("https://api.gellertlabor.hu/api/index.php/records/wp_cpabc_appointments",
                 {"filter": "json,cs,lemondva", "order": "id,desc", "size": "100",
                  "include": "id,booked_time,name,json"}, {"X-API-Key": key})["records"]

lemondott = []
for r in foglalasok:
    if (r.get("booked_time") or "")[:10] != NAP:
        continue
    mm = re.search(r'lemondva":\{"mikor":"([^"]+)', r.get("json") or "")
    lemondott.append((r["id"], r["booked_time"], r["name"], mm.group(1) if mm else "?"))

def tok(s):
    return frozenset(re.findall(r"\w+", (s or "").lower()))

lemondott_tok = {tok(x[2]): x for x in lemondott}

print("Lemondasok %s napra: %d" % (NAP, len(lemondott)))
for x in sorted(lemondott, key=lambda x: x[3], reverse=True):
    print("  id %s | %s | %s | lemondva: %s" % x)
print()
print("LIS nevsor %s (%d fo):" % (NAP, len(lis)))
for p in sorted(lis, key=lambda p: p["sorszam"]):
    jel = "  <-- LEMONDVA" if tok(p["full_name"]) in lemondott_tok else ""
    print("  %s  %s%s" % (p["sorszam"], p["full_name"], jel))

# --- Uj foglalasok: aktiv (nem lemondott) foglalasok a napra, amik nincsenek a LIS-ben ---
akt = get("https://api.gellertlabor.hu/api/index.php/records/wp_cpabc_appointments",
          {"filter": "booked_time,sw," + NAP, "order": "booked_time,asc", "size": "200",
           "include": "id,booked_time,name,json"}, {"X-API-Key": key})["records"]
lis_tok = [tok(p["full_name"]) for p in lis]
print()
print("Aktiv foglalasok %s napra (lemondottak nelkul):" % NAP)
hiany = 0
for r in akt:
    if '"lemondva"' in (r.get("json") or ""):
        continue
    nev = r["name"]
    t = tok(nev)
    bent = any(t == l or (len(t) > 1 and t <= l) or (len(l) > 1 and l <= t) for l in lis_tok)
    if not bent:
        hiany += 1
    print("  id %s | %s | %s%s" % (r["id"], r["booked_time"], nev, "" if bent else "  <-- NINCS A LIS-BEN"))
print("Nincs a LIS-ben: %d" % hiany)
