import re

_ANGKA = re.compile(r"\d+(?:\.\d+)?")


def normalisasi_label(teks: str) -> str:
    m = _ANGKA.search(teks)
    if not m:
        return teks.strip().lower()
    angka = m.group(0)
    bulat, _, desimal = angka.partition(".")
    bulat = bulat.lstrip("0") or "0"
    return f"{bulat}.{desimal}" if desimal else bulat


def _angka(label_normal: str) -> float | None:
    try:
        return float(label_normal)
    except ValueError:
        return None


def kunci_urut_semua(label_normal_lama_ke_baru: list[str]) -> list[float]:
    kunci: list[float] = []
    for label in label_normal_lama_ke_baru:
        n = _angka(label)
        if n is None:
            n = round(kunci[-1] + 0.001, 6) if kunci else 0.0
        kunci.append(n)
    return kunci


def jendela_lima(label_terurut: list[str], sekarang: str) -> list[str]:
    i = label_terurut.index(sekarang)
    lain = [label for label in label_terurut if label != sekarang]
    mulai = max(0, min(i - 2, len(lain) - 5))
    return lain[mulai:mulai + 5]
