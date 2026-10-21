"""
Analýza výkonu balicích linek a automatický report.

Načte data z výroby (data/vyroba.csv a data/prostoje.csv) do databáze SQLite,
spočítá pro každou linku OEE, najde problémy, kterým by se měl někdo věnovat,
a výsledek uloží jako přehledný HTML report (report.html).

Spuštění:  python3 analyza.py
Používá jen standardní knihovnu Pythonu, nic se nemusí instalovat.
"""

import csv
import html
import re
import sqlite3
import statistics
from datetime import datetime

CILOVY_VYKON = 40  # sáčků za minutu při plném výkonu (stejné jako v generátoru dat)


# ---------------------------------------------------------------------------
# 1) Načtení dat do SQLite
# ---------------------------------------------------------------------------
def nacti_data():
    db = sqlite3.connect(":memory:")
    db.execute("""CREATE TABLE vyroba (linka TEXT, cas TEXT, smena TEXT,
                  planovano_min INT, bezi_min INT, vyrobeno INT, vadne INT)""")
    db.execute("CREATE TABLE prostoje (linka TEXT, cas TEXT, duvod TEXT, minuty INT)")

    with open("data/vyroba.csv", encoding="utf-8") as f:
        radky = [tuple(r.values()) for r in csv.DictReader(f)]
    db.executemany("INSERT INTO vyroba VALUES (?,?,?,?,?,?,?)", radky)

    with open("data/prostoje.csv", encoding="utf-8") as f:
        radky = [tuple(r.values()) for r in csv.DictReader(f)]
    db.executemany("INSERT INTO prostoje VALUES (?,?,?,?)", radky)
    return db


def cesky_cislo(text):
    """V textu nahradí desetinné tečky čárkami (1.5 → 1,5), jak se píše česky."""
    return re.sub(r"(?<=\d)\.(?=\d)", ",", text)


def cesky_datum(text, rok=True):
    """Z ISO data (2026-10-17...) udělá české „17. 10. 2026“."""
    d = datetime.fromisoformat(text)
    return "%d. %d. %d" % (d.day, d.month, d.year) if rok else "%d. %d." % (d.day, d.month)


# ---------------------------------------------------------------------------
# 2) Výpočty
# ---------------------------------------------------------------------------
def oee_linek(db):
    """OEE = dostupnost × výkon × kvalita, pro každou linku zvlášť."""
    radky = db.execute("""
        SELECT linka, SUM(planovano_min), SUM(bezi_min), SUM(vyrobeno), SUM(vadne)
        FROM vyroba GROUP BY linka ORDER BY linka""").fetchall()
    vysledek = []
    for linka, planovano, bezi, vyrobeno, vadne in radky:
        dostupnost = bezi / planovano                    # jak dlouho linka opravdu jela
        vykon = vyrobeno / (bezi * CILOVY_VYKON)         # jak rychle jela oproti cíli
        kvalita = (vyrobeno - vadne) / vyrobeno          # kolik sáčků bylo v pořádku
        vysledek.append({
            "linka": linka, "dostupnost": dostupnost, "vykon": vykon, "kvalita": kvalita,
            "oee": dostupnost * vykon * kvalita, "vyrobeno": vyrobeno, "vadne": vadne,
        })
    return vysledek


def najdi_problemy(db, linky):
    """Projde data a vrátí seznam problémů srozumitelnými větami."""
    problemy = []
    prumer_oee = statistics.mean(l["oee"] for l in linky)

    # a) Linky s OEE výrazně pod průměrem – a která složka je táhne dolů
    for l in linky:
        if l["oee"] < prumer_oee - 0.05:
            slozky = {"dostupnost": l["dostupnost"], "výkon": l["vykon"], "kvalita": l["kvalita"]}
            nejhorsi = min(slozky, key=slozky.get)
            problemy.append((1, "%s má OEE %.0f %% (průměr linek %.0f %%). Nejvíc ji táhne dolů %s."
                             % (l["linka"], l["oee"] * 100, prumer_oee * 100, nejhorsi)))

    # b) Opakované krátké zastávky: stejný důvod mnohem častěji než na ostatních linkách
    pocty = db.execute("""SELECT duvod, linka, COUNT(*), AVG(minuty)
                          FROM prostoje GROUP BY duvod, linka""").fetchall()
    podle_duvodu = {}
    for duvod, linka, pocet, prumer_min in pocty:
        podle_duvodu.setdefault(duvod, []).append((linka, pocet, prumer_min))
    for duvod, zaznamy in podle_duvodu.items():
        median = statistics.median(p for _, p, _ in zaznamy)
        for linka, pocet, prumer_min in zaznamy:
            if pocet > 3 * median and prumer_min <= 3:
                problemy.append((2, "%s: „%s“ se opakuje %d× za týden (ostatní linky kolem %d×). "
                                    "Jsou to krátké zastávky po %.1f min, které se snadno přehlédnou."
                                    % (linka, duvod, pocet, median, prumer_min)))

    # c) Kvalita podle směn: směna s výrazně vyšším podílem vadných sáčků
    smeny = db.execute("""SELECT linka, smena, 1.0 * SUM(vadne) / SUM(vyrobeno)
                          FROM vyroba GROUP BY linka, smena""").fetchall()
    podle_linky = {}
    for linka, smena, podil in smeny:
        podle_linky.setdefault(linka, {})[smena] = podil
    for linka, hodnoty in podle_linky.items():
        for smena, podil in hodnoty.items():
            ostatni = [v for s, v in hodnoty.items() if s != smena]
            if podil > 2 * statistics.mean(ostatni):
                problemy.append((3, "%s: na %s směně je %.1f %% vadných sáčků, na ostatních jen %.1f %%."
                                    % (linka, smena, podil * 100, statistics.mean(ostatni) * 100)))

    # d) Velké poruchy: dlouhé zastávky (průměrně 10+ min), které za den daly aspoň 2 hodiny
    dlouhe = db.execute("""SELECT linka, substr(cas, 1, 10) AS den, duvod, SUM(minuty) AS celkem
                           FROM prostoje GROUP BY linka, den, duvod
                           HAVING celkem >= 120 AND AVG(minuty) >= 10
                           ORDER BY celkem DESC""").fetchall()
    for linka, den, duvod, celkem in dlouhe:
        problemy.append((4, "%s: %s stála kvůli „%s“ celkem %.1f h."
                            % (linka, cesky_datum(den, rok=False), duvod, celkem / 60)))
    return problemy


# ---------------------------------------------------------------------------
# 3) HTML report
# ---------------------------------------------------------------------------
def svg_graf(linky, problemove):
    """Vodorovný sloupcový graf OEE. Linky s problémem jsou červeně."""
    radek, sirka = 30, 420
    casti = ['<svg viewBox="0 0 560 %d" width="100%%" role="img" aria-label="OEE linek">' % (len(linky) * radek + 10)]
    for i, l in enumerate(linky):
        y = i * radek + 5
        barva = "#c0392b" if l["linka"] in problemove else "#2e7d32"
        casti.append('<text x="0" y="%d" font-size="13">%s</text>' % (y + 17, l["linka"]))
        casti.append('<rect x="60" y="%d" width="%d" height="20" rx="3" fill="%s"/>'
                     % (y + 2, l["oee"] * sirka, barva))
        casti.append('<text x="%d" y="%d" font-size="13">%.0f %%</text>'
                     % (66 + l["oee"] * sirka, y + 17, l["oee"] * 100))
    casti.append("</svg>")
    return "".join(casti)


def uloz_report(db, linky, problemy):
    obdobi = db.execute("SELECT MIN(cas), MAX(cas) FROM vyroba").fetchone()
    od, do = (cesky_datum(c) for c in obdobi)
    problemove = {p.split(":")[0].split(" ")[0] for _, p in problemy}

    duvody = db.execute("""SELECT duvod, COUNT(*), SUM(minuty) FROM prostoje
                           GROUP BY duvod ORDER BY SUM(minuty) DESC LIMIT 6""").fetchall()

    tabulka = "".join(
        "<tr><td>%s</td><td>%.0f %%</td><td>%.0f %%</td><td>%.1f %%</td><td><b>%.0f %%</b></td>"
        "<td>%s</td><td>%s</td></tr>"
        % (l["linka"], l["dostupnost"] * 100, l["vykon"] * 100, l["kvalita"] * 100, l["oee"] * 100,
           format(l["vyrobeno"], ",").replace(",", " "), format(l["vadne"], ",").replace(",", " "))
        for l in linky)
    seznam = "".join("<li>%s</li>" % html.escape(cesky_cislo(p)) for _, p in sorted(problemy, key=lambda x: x[0]))
    tab_duvody = "".join("<tr><td>%s</td><td>%d×</td><td>%.1f h</td></tr>"
                         % (html.escape(d), n, m / 60) for d, n, m in duvody)
    tabulka, tab_duvody = cesky_cislo(tabulka), cesky_cislo(tab_duvody)

    stranka = """<!doctype html><html lang="cs"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Výkon balicích linek</title>
<style>
 body{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;max-width:860px;margin:32px auto;padding:0 16px;color:#1f2933}
 h1{margin-bottom:4px} .sub{color:#6b7280;margin-top:0}
 .box{background:#fff7ed;border-left:4px solid #d97706;padding:12px 18px;border-radius:6px}
 table{border-collapse:collapse;width:100%%;margin:8px 0 24px} th,td{padding:6px 10px;border-bottom:1px solid #e5e7eb;text-align:right}
 th:first-child,td:first-child{text-align:left} th{background:#f3f4f6}
</style></head><body>
<h1>Výkon balicích linek</h1>
<p class="sub">Období %s – %s · %d linek · report vytvořen automaticky skriptem analyza.py</p>
<h2>Na co se podívat</h2>
<div class="box"><ul>%s</ul></div>
<h2>OEE podle linek</h2>
%s
<p class="sub">OEE = dostupnost × výkon × kvalita. Červeně jsou linky, u kterých analýza našla problém.</p>
<table><tr><th>Linka</th><th>Dostupnost</th><th>Výkon</th><th>Kvalita</th><th>OEE</th><th>Vyrobeno sáčků</th><th>Vadných</th></tr>%s</table>
<h2>Nejčastější důvody prostojů</h2>
<table><tr><th>Důvod</th><th>Počet zastávek</th><th>Celkem</th></tr>%s</table>
</body></html>""" % (od, do, len(linky), seznam, svg_graf(linky, problemove), tabulka, tab_duvody)

    with open("report.html", "w", encoding="utf-8") as f:
        f.write(stranka)


def main():
    db = nacti_data()
    linky = oee_linek(db)
    problemy = najdi_problemy(db, linky)
    uloz_report(db, linky, problemy)
    print("Report uložen do report.html. Nalezené problémy:")
    for _, p in sorted(problemy, key=lambda x: x[0]):
        print(" -", cesky_cislo(p))


if __name__ == "__main__":
    main()
