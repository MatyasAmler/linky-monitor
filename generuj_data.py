import csv
import os
import random
from datetime import datetime, timedelta

random.seed(42)

LINKY = ["PP-%02d" % i for i in range(1, 9)]
CILOVY_VYKON = 40  # sáčků za minutu
DNY = 7

# důvod zastávky: (min, max) minut
DUVODY = {
    "Prázdný zásobník dílků": (2, 6),
    "Zaseknutý dílek": (1, 4),
    "Výměna role fólie": (5, 10),
    "Chyba váhy": (1, 3),
    "Porucha senzoru": (3, 15),
}


def smena(hodina):
    if 6 <= hodina < 14:
        return "ranní"
    if 14 <= hodina < 22:
        return "odpolední"
    return "noční"


def main():
    os.makedirs("data", exist_ok=True)
    zacatek = datetime.now().replace(minute=0, second=0, microsecond=0) - timedelta(days=DNY)

    vyroba = []
    prostoje = []

    for linka in LINKY:
        for h in range(DNY * 24):
            cas = zacatek + timedelta(hours=h)
            stoji_minut = 0

            if random.random() < 0.5:
                duvod = random.choice(list(DUVODY))
                minuty = random.randint(*DUVODY[duvod])
                prostoje.append([linka, cas.isoformat(timespec="minutes"), duvod, minuty])
                stoji_minut += minuty

            # PP-03 - chyba váhy několikrát za hodinu
            if linka == "PP-03":
                for _ in range(random.randint(2, 5)):
                    minuty = random.randint(1, 2)
                    prostoje.append([linka, cas.isoformat(timespec="minutes"), "Chyba váhy", minuty])
                    stoji_minut += minuty

            # PP-07 - porucha podavače třetí den
            if linka == "PP-07" and 2 * 24 + 10 <= h < 2 * 24 + 15:
                prostoje.append([linka, cas.isoformat(timespec="minutes"), "Porucha podavače", 60])
                stoji_minut = 60

            bezi_minut = max(0, 60 - stoji_minut)
            vyrobeno = int(bezi_minut * CILOVY_VYKON * random.uniform(0.85, 1.0))

            podil_vadnych = random.uniform(0.002, 0.01)
            # PP-06 - víc vadných na noční
            if linka == "PP-06" and smena(cas.hour) == "noční":
                podil_vadnych = random.uniform(0.04, 0.07)
            vadne = int(vyrobeno * podil_vadnych)

            vyroba.append([linka, cas.isoformat(timespec="minutes"), smena(cas.hour),
                           60, bezi_minut, vyrobeno, vadne])

    with open("data/vyroba.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["linka", "cas", "smena", "planovano_min", "bezi_min", "vyrobeno", "vadne"])
        w.writerows(vyroba)

    with open("data/prostoje.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["linka", "cas", "duvod", "minuty"])
        w.writerows(prostoje)

    print("Hotovo: %d hodinových záznamů, %d zastávek." % (len(vyroba), len(prostoje)))


if __name__ == "__main__":
    main()
