# Linky monitor – výkon balicích linek a automatický report

Malý projekt v Pythonu, který z dat o výrobě spočítá, jak dobře běží jednotlivé
balicí linky, sám najde problémy, kterým by se měl někdo věnovat, a připraví
z toho přehledný report. Místo ručního procházení tabulek stačí spustit jeden skript.

## Co umí

- **Načte data do SQL databáze** (SQLite) a výpočty dělá SQL dotazy.
- **Spočítá OEE každé linky** – dostupnost × výkon × kvalita – a ukáže, která z těch tří složek linku nejvíc brzdí.
- **Najde problémy automaticky:**
  - linky s OEE výrazně pod průměrem,
  - opakované krátké zastávky, které se v provozu snadno přehlédnou (např. zasekávající se váha),
  - směnu, na které je výrazně víc vadných kusů než na ostatních,
  - velké poruchy, kvůli kterým linka stála hodiny.
- **Vytvoří HTML report** (`report.html`) s výpisem „Na co se podívat“, grafem OEE a tabulkami. Report jde poslat e-mailem nebo otevřít v prohlížeči.

## Jak to spustit

Stačí Python 3.9 nebo novější, nic dalšího se neinstaluje.

```bash
python3 generuj_data.py   # vytvoří ukázková data do složky data/
python3 analyza.py        # spočítá výsledky a uloží report.html
```

## Odkud jsou data

Skutečná výrobní data nemám, proto `generuj_data.py` simuluje 8 linek za 7 dní
ve třísměnném provozu. Do dat jsou schválně vložené tři problémy
(chyba váhy na PP-03, vadné sáčky na noční směně PP-06, dlouhá porucha na PP-07),
aby šlo ověřit, že je analýza opravdu najde. Najde je všechny.

Se skutečnými daty by se vyměnila jen funkce `nacti_data()` – místo CSV souborů
by četla třeba z výrobního systému (MES) nebo z databáze.

## Co bych přidal dál

- export výsledků pro **Power BI**, aby šlo data dál filtrovat a sdílet,
- **upozornění** (e-mail nebo Teams), když OEE linky během směny spadne pod limit,
- porovnání týden po týdnu, aby bylo vidět, jestli opatření pomohla.

## Jak projekt vznikl

Projekt jsem udělal jako ukázku k přihlášce na studentskou pozici IT & Digital
Solutions v LEGO továrně v Kladně, inspirovaný příklady z inzerátu.

Matyáš Amler · amler.prace@gmail.com · [matyasamler.cz](https://matyasamler.cz)
