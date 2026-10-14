<?php
/**
 * nap_betolto.php — a vérvételi nap előkészítő folyamatának (hetfo.json) betöltése a vdata 'elokeszites' bejegyzésekbe.
 *
 * Futtatás a SZERVEREN, parancssorból, a docrootból; a hetfo.json a docrooton KÍVÜL legyen (páciensadat), a futás után törlendő:
 *     cd ~/wwwroot/l
 *     /opt/alt/php83/usr/bin/php nap_betolto.php ~/nap-betoltes/hetfo.json          → terv: kérésenként mit írna; NEM ír
 *     /opt/alt/php83/usr/bin/php nap_betolto.php ~/nap-betoltes/hetfo.json --go     → beírja (csak ahol még nincs bejegyzés)
 *     ... --go --felulir                                                           → a már mentett bejegyzést is felülírja (a kézi munka elvész!)
 * Csak a vdata táblába ír (kulcs: 'elokeszites', és ugyanez 'elokeszites_alap' néven: az oldal „Előről kezdem” gombjának kiinduló állapota); vizsgálatot, kartont, vizsgs-t nem módosít. Idempotens: a már meglévő
 * bejegyzést alapból békén hagyja, hogy a kolléganő kézi szerkesztése ne vesszen el.
 *
 * Mit épít kérésenként (az oldal ugyanazt a kiinduló állapotot adná: csomag + felvett vizsgálatok, ne_alap()), plusz:
 *   - az adatlap ikszelt mezői (bejelolt[].mezo = a rács cellájának azonosítója; ismeretlen mező → „Egyéb vizsgálat”),
 *   - az értékelés végső kérése (vegso_keres) „Egyéb vizsgálatként”, a forrásával,
 *   - a levélbeli ajánlat sorai és a naptár-cím megjegyzése „Egyéb vizsgálatként”,
 *   - az adatlap „Egyéb vizsgálat” szövege szó szerint (adatlap_egyeb),
 *   - az elszamolas.szoveg az adatlap_egyeb végére (ha a vegosszeg egyezik a sorok összegével; különben eldobva),
 *   - állapot és egy mondat az értékelésből (a fizet/teendő/kérdés AI-szöveg nem kerül be). mod = "kezi", modellnév nincs.
 * Kérés-azonosító: hetfo.json paciensek[].vid = vizsgalats.id.
 *
 * Külön mód: --adatlap-jelzo → NEM az előkészítést tölti, hanem a „van adatlapja” jelzőt írja a vdata 'adatlap' kulcsba
 * ({"van":true,"fajl":…,"datum":ÉÉÉÉ-HH-NN,"forras":"nap_betolto"}) azoknál a kéréseknél, ahol a hetfo.json-ban van adatlap-blokk.
 * Csak ezt a kulcsot érinti, a meglévő jelzőt nem írja felül, az 'elokeszites'-hez nem nyúl. A lista ezt mutatja.
 */

if (PHP_SAPI !== 'cli') {
    http_response_code(403);
    exit('Csak parancssorból futtatható.');
}

$args = array_slice($argv, 1);
$go = in_array('--go', $args, true);
$felulir = in_array('--felulir', $args, true);
$fajl = '';
foreach ($args as $a) if (substr($a, 0, 2) !== '--') $fajl = $a;
if ($fajl === '' || !is_file($fajl)) {
    fwrite(STDERR, "Használat: php nap_betolto.php <hetfo.json> [--go] [--felulir]\n");
    exit(2);
}
$hetfo = json_decode((string) file_get_contents($fajl), true);
if (!is_array($hetfo) || !isset($hetfo['paciensek'])) {
    fwrite(STDERR, "A fájl nem hetfo.json.\n");
    exit(2);
}

// Adatbázis: ugyanaz a kapcsolat, mint az index.php-ban (a jelszót onnan olvassuk, nem másoljuk). A próbakörnyezet felülírhatja.
if (!function_exists('db_query')) {
    $idx = (string) file_get_contents(dirname(__FILE__) . '/index.php');
    if (!preg_match('/mysqli_connect\(\s*localhost\s*,\s*"([^"]+)"\s*,\s*"([^"]*)"\s*,\s*"([^"]+)"\s*\)/', $idx, $m)) {
        fwrite(STDERR, "Az index.php-ban nem találom a kapcsolatot.\n");
        exit(2);
    }
    $con = mysqli_connect('localhost', $m[1], $m[2], $m[3]);
    if (!$con) {
        fwrite(STDERR, "Nincs adatbázis-kapcsolat.\n");
        exit(2);
    }
    mysqli_set_charset($con, 'utf8');
    function db_query($query)
    {
        global $con;
        $r = mysqli_query($con, $query);
        if (mysqli_error($con)) {
            fwrite(STDERR, mysqli_error($con) . "\n");
            return null;
        }
        $ki = array();
        if ($r) while ($f = mysqli_fetch_assoc($r)) $ki[] = $f;
        return $ki ? $ki : null;
    }
}
date_default_timezone_set('CET');
require_once dirname(__FILE__) . '/nap_elokeszito_lib.php';

function nb_lista($v)
{
    if (is_array($v)) return trim(implode("\n", array_map('strval', $v)));
    return trim((string) $v);
}

function nb_kivul(&$tetelek, $nev, $forras)
{
    $nev = trim((string) $nev);
    if ($nev === '') return;
    foreach ($tetelek as $t) if (!$t['racs'] && $t['nev'] === $nev) return;
    $n = 1;
    $van = array();
    foreach ($tetelek as $t) $van[$t['id']] = 1;
    while (isset($van['x' . $n])) $n++;
    $tetelek[] = array('id' => 'x' . $n, 'nev' => $nev, 'forras' => $forras, 'racs' => false, 'szin' => '', 'szin_ok' => null, 'cso' => null);
}

if (in_array('--adatlap-jelzo', $args, true)) {
    $vidk = array();
    foreach ($hetfo['paciensek'] as $p) if (!empty($p['vid'])) $vidk[] = intval($p['vid']);
    $mar = ne_vdata($vidk, array('adatlap'));
    $irt = 0;
    $hiba = 0;
    foreach ($hetfo['paciensek'] as $p) {
        if (empty($p['vid'])) continue;
        $vid = intval($p['vid']);
        $ad = isset($p['adatlap']) && is_array($p['adatlap']) ? $p['adatlap'] : null;
        if (!$ad) { echo "$vid  nincs adatlap\n"; continue; }
        if (isset($mar[$vid]['adatlap'])) { echo "$vid  KIHAGYVA (már van jelző)\n"; continue; }
        $fajl = isset($ad['fajl']) ? basename((string) $ad['fajl']) : '';
        $datum = '';
        if (preg_match('/^(\d\d)_(\d\d)_(\d{4})_/', $fajl, $m)) $datum = $m[3] . '-' . $m[1] . '-' . $m[2];
        elseif (preg_match('/(\d{4}-\d{2}-\d{2})/', $fajl, $m)) $datum = $m[1];
        echo "$vid  adatlap van" . ($datum !== '' ? " ($datum)" : '') . "\n";
        if (!$go) continue;
        $ertek = ne_esc(ne_json(array('van' => true, 'fajl' => $fajl, 'datum' => $datum, 'forras' => 'nap_betolto')));
        if (ne_ir("INSERT INTO vdata (vizsgalat_id, kulcs, ertek) VALUES (" . $vid . ", 'adatlap', '" . $ertek . "')")) $irt++;
        else { $hiba++; echo "   HIBA: a $vid jelzője nem íródott\n"; }
    }
    echo ($go ? "Kész: $irt jelző beírva, $hiba hiba.\n" : "Terv (nem írt semmit). Beíráshoz: --go\n");
    exit($hiba ? 1 : 0);
}

$racs = ne_racs();
$cellak = array();
foreach ($racs['oszlopok'] as $lista) foreach ($lista as $c) if (isset($c['k']) && $c['k']) $cellak[$c['k']] = $c;

// A papír nyomtatott felirata → cella. Szkennelt/lefotózott lapnál a kiolvasásban nincs mezőnév, csak a felirat; ez a rács saját
// felirata, ezért pontos egyezés kell (kis-/nagybetű és szóköz eltérés nem számít), hasonlóság nem.
function nb_felirat($s)
{
    return mb_strtolower(trim(preg_replace('/\s+/u', ' ', (string) $s)), 'UTF-8');
}
$feliratok = array();
foreach ($cellak as $k => $c) {
    $f = nb_felirat($c['l']);
    $feliratok[$f] = isset($feliratok[$f]) ? false : $k; // kétszer szereplő felirat nem egyértelmű
}

$vd = array();
$vidk = array();
foreach ($hetfo['paciensek'] as $p) if (!empty($p['vid'])) $vidk[] = intval($p['vid']);
$vd = ne_vdata($vidk, array('elokeszites', 'foglalt_csomag'));

$irt = 0;
$kihagy = 0;
$hiba = 0;
foreach ($hetfo['paciensek'] as $p) {
    if (empty($p['vid'])) continue;
    $vid = intval($p['vid']);
    $van = isset($vd[$vid]['elokeszites']);
    if ($van && !$felulir) {
        echo "$vid  KIHAGYVA (már van mentett előkészítés)\n";
        $kihagy++;
        continue;
    }
    $a = ne_alap($vid, isset($vd[$vid]['foglalt_csomag']) ? $vd[$vid]['foglalt_csomag'] : '');
    $bent = array();
    foreach ($a['tetelek'] as $t) $bent[$t['id']] = 1;
    $ad = isset($p['adatlap']) && is_array($p['adatlap']) ? $p['adatlap'] : null;
    $nemRacs = 0;
    if ($ad) {
        foreach ((array) $ad['bejelolt'] as $b) {
            $mezo = isset($b['mezo']) ? (string) $b['mezo'] : '';
            if ($mezo === '' && isset($b['teszt_nev'])) {
                $f = nb_felirat($b['teszt_nev']);
                if (isset($feliratok[$f]) && $feliratok[$f] !== false) $mezo = $feliratok[$f];
            }
            if ($mezo !== '' && isset($cellak[$mezo])) {
                if (!isset($bent[$mezo])) {
                    $bent[$mezo] = 1;
                    $a['tetelek'][] = array('id' => $mezo, 'nev' => $cellak[$mezo]['l'], 'forras' => (isset($b['mezo']) && $b['mezo'] !== '' ? 'adatlap (ikszelt)' : 'adatlap (ikszelt, felirat szerint)'), 'racs' => true, 'szin' => '', 'szin_ok' => null, 'cso' => $cellak[$mezo]['cso']);
                }
            } else {
                $nemRacs++;
                nb_kivul($a['tetelek'], isset($b['teszt_nev']) ? $b['teszt_nev'] : $mezo, 'adatlap (ikszelt, nincs a rácson)');
            }
        }
        $egyeb = array();
        foreach (array('egyebek_szoveg', 'kezi_rairas', 'kert_vizsgalatok_szoveg') as $k) {
            if (isset($ad[$k]) && trim((string) (is_array($ad[$k]) ? json_encode($ad[$k], JSON_UNESCAPED_UNICODE) : $ad[$k])) !== '') {
                $egyeb[] = ($k === 'kezi_rairas' ? 'Kézi ráírás: ' : ($k === 'kert_vizsgalatok_szoveg' ? 'Kért vizsgálatok: ' : '')) . (is_array($ad[$k]) ? json_encode($ad[$k], JSON_UNESCAPED_UNICODE) : trim($ad[$k]));
            }
        }
        $a['adatlap_egyeb'] = implode("\n\n", $egyeb);
    }
    $e = isset($p['ertekeles']) && is_array($p['ertekeles']) ? $p['ertekeles'] : null;
    if ($e) {
        $a['allapot'] = isset($e['allapot']) ? $e['allapot'] : '';
        if (!empty($e['egy_sor'])) $a['egy_sor'] = $e['egy_sor'];
        // fizet / teendo / kerdes: az AI szabad szövegét NEM töltjük be (Allen, 10-11: nem kellenek a tudálékos AI-szövegek)
        $megj = array();
        foreach ((array) (isset($e['vegso_keres']) ? $e['vegso_keres'] : array()) as $k) {
            // tipus (forgatókönyv, 10-11): csak a vizsgálat tétel; a csomagnév, díj és megjegyzés nem. Típus nélkül a régi viselkedés.
            // megjegyzes (pl. a cset-szálban számolt ár): nem tétel, szövegként az adatlap_egyeb végére (10-14)
            if (isset($k['tipus']) && $k['tipus'] === 'megjegyzes' && isset($k['tetel']) && trim($k['tetel']) !== '') $megj[] = 'Megjegyzés: ' . trim($k['tetel']);
            if (isset($k['tipus']) && $k['tipus'] !== '' && $k['tipus'] !== 'vizsgalat') continue;
            $f = nb_felirat(isset($k['tetel']) ? $k['tetel'] : '');
            if (isset($feliratok[$f]) && $feliratok[$f] !== false && isset($bent[$feliratok[$f]])) continue; // már bejelölt rács-cella, nem kell kétszer
            nb_kivul($a['tetelek'], isset($k['tetel']) ? $k['tetel'] : '', 'értékelés: ' . (isset($k['forras']) ? $k['forras'] : ''));
        }
        if ($megj) $a['adatlap_egyeb'] = trim((isset($a['adatlap_egyeb']) ? $a['adatlap_egyeb'] : '') . "\n\n" . implode("\n", $megj));
    }
    $lv = isset($p['levelezes']) && is_array($p['levelezes']) ? $p['levelezes'] : null;
    if ($lv && isset($lv['arajanlat']['tetelek']) && is_array($lv['arajanlat']['tetelek'])) {
        foreach ($lv['arajanlat']['tetelek'] as $t) {
            nb_kivul($a['tetelek'], isset($t['nev']) ? $t['nev'] . (isset($t['ar']) && $t['ar'] !== '' ? ' (' . $t['ar'] . ')' : '') : '', 'levél: ajánlat');
        }
    }
    foreach ((array) (isset($p['naptar']) ? $p['naptar'] : array()) as $n) {
        if (isset($n['megjegyzes_tipus']) && $n['megjegyzes_tipus'] !== '' && $n['megjegyzes_tipus'] !== 'vizsgalat') continue; // összeg, megjegyzés: nem tétel
        $cim = isset($n['cim']) ? trim($n['cim']) : '';
        $nev = isset($p['nev']) ? trim($p['nev']) : '';
        $maradek = $cim;
        if ($nev !== '' && stripos($cim, $nev) === 0) $maradek = trim(ltrim(substr($cim, strlen($nev)), " /-–"));
        if ($maradek !== '' && $maradek !== $cim) nb_kivul($a['tetelek'], $maradek, 'naptár megjegyzés');
        elseif ($maradek !== '' && $nev === '') nb_kivul($a['tetelek'], $maradek, 'naptár megjegyzés');
    }
    // elszámolás (10-14): a lapra nyomtatott szöveg betűre ugyanaz; ha a végösszeg nem egyezik a sorok összegével, eldobjuk
    $el = isset($p['elszamolas']) && is_array($p['elszamolas']) ? $p['elszamolas'] : null;
    $elMegj = '';
    if ($el) {
        $osszeg = 0;
        foreach ((array) (isset($el['sorok']) ? $el['sorok'] : array()) as $s) $osszeg += intval(isset($s['ar']) ? $s['ar'] : 0);
        if (!isset($el['vegosszeg']) || intval($el['vegosszeg']) !== $osszeg || !isset($el['szoveg']) || trim($el['szoveg']) === '') {
            $elMegj = ' (elszámolás eldobva: a végösszeg nem egyezik)';
        } else {
            $a['adatlap_egyeb'] = trim((isset($a['adatlap_egyeb']) ? $a['adatlap_egyeb'] : '') . "\n\n" . trim($el['szoveg']));
        }
    }
    $uj = ne_tisztit($a);
    $racsDb = 0;
    foreach ($uj['tetelek'] as $t) if ($t['racs']) $racsDb++;
    echo "$vid  " . ($van ? 'FELÜLÍR' : 'új') . "  rács: $racsDb, egyéb vizsgálat: " . (count($uj['tetelek']) - $racsDb) . ($nemRacs ? " (ebből adatlap-mező ismeretlen: $nemRacs)" : '') . ", állapot: " . ($uj['allapot'] === '' ? '-' : $uj['allapot']) . $elMegj . "\n";
    if (!$go) continue;
    $ertek = ne_esc(ne_json($uj));
    $sor = db_query("SELECT id FROM vdata WHERE vizsgalat_id = " . $vid . " AND kulcs = 'elokeszites' ORDER BY id DESC LIMIT 1");
    $ok = $sor ? ne_ir("UPDATE vdata SET ertek = '" . $ertek . "' WHERE id = " . intval($sor[0]['id']))
        : ne_ir("INSERT INTO vdata (vizsgalat_id, kulcs, ertek) VALUES (" . $vid . ", 'elokeszites', '" . $ertek . "')");
    if ($ok) ne_kulcs_ir($vid, 'elokeszites_alap', ne_json($uj));   // az oldal „Előről kezdem” gombja ide áll vissza
    if ($ok) $irt++;
    else {
        $hiba++;
        echo "   HIBA: a $vid mentése nem sikerült\n";
    }
}
echo ($go ? "Kész: $irt beírva, $kihagy kihagyva, $hiba hiba.\n" : "Terv (nem írt semmit). Beíráshoz: --go\n");
exit($hiba ? 1 : 0);
