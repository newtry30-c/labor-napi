#!/bin/zsh
# Egy nap előkészítő-fájljának (hetfo.json, kedd.json …) feltöltése a szerverre és a betöltő futtatása.
#   betoltes.sh [fájl.json]                → száraz futás (nem ír); fájl nélkül: mintaadat/hetfo.json
#   betoltes.sh [fájl.json] --go           → beírja a vdata-ba (csak ahol még nincs bejegyzés)
#   betoltes.sh [fájl.json] --go --felulir → a már mentett bejegyzést is felülírja (a kézi munka elvész!)
#   betoltes.sh [fájl.json] --adatlap-jelzo [--go]  → csak a „van adatlapja” jelzőt írja (vdata 'adatlap'), az előkészítéshez nem nyúl
#   betoltes.sh --torol                    → a szerveren maradt fájlok törlése (páciensadat!) – minden betöltés végén
# A nap a fájlban lévő vizsgálat-azonosítókból (paciensek[].vid) adódik, a fájl neve mindegy: a keddi nap ugyanígy tölthető.
S=zygjid@gellertlabor.hu
D="$(cd "$(dirname "$0")" && pwd)"
if [[ "$1" == "--torol" ]]; then
  ssh $S 'rm -rf ~/nap-betoltes' 2>&1 | grep -v bashrc
  echo "Törölve."
  exit 0
fi
F="$D/mintaadat/hetfo.json"; ARGS=()
for a in "$@"; do
  if [[ "$a" == --* ]]; then ARGS+=("$a"); else F="$a"; fi
done
[[ -f "$F" ]] || { echo "Nincs ilyen fájl: $F" >&2; exit 1; }
B="$(basename "$F")"
ssh $S 'mkdir -p ~/nap-betoltes' 2>&1 | grep -v bashrc
scp "$F" "$S:~/nap-betoltes/$B" || exit 1
ssh $S "cd ~/wwwroot/l && /opt/alt/php83/usr/bin/php nap_betolto.php ~/nap-betoltes/$B ${ARGS[*]}" 2>&1 | grep -v bashrc
