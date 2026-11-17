from sela.urutan import jendela_lima, kunci_urut_semua, normalisasi_label


def test_normalisasi():
    assert [normalisasi_label(t) for t in ["Chapter 10.5", "Ch. 01", "chapter-26", " Prolog "]] == ["10.5", "1", "26", "prolog"]


def test_kunci_urut_label_tanpa_angka_ikut_posisi():
    assert kunci_urut_semua(["prolog", "1", "2", "ekstra", "3", "10.5"]) == [0.0, 1.0, 2.0, 2.001, 3.0, 10.5]


LABEL = [str(i) for i in range(1, 11)] + ["10.5"] + [str(i) for i in range(11, 28)]


def test_jendela_lima():
    assert jendela_lima(LABEL, "12") == ["10.5", "11", "13", "14", "15"]
    assert jendela_lima(LABEL, "1") == ["2", "3", "4", "5", "6"]
    assert jendela_lima(LABEL, "27") == ["22", "23", "24", "25", "26"]
    assert jendela_lima(["1", "2", "3"], "2") == ["1", "3"]
