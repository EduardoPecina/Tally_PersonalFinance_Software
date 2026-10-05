"""Limpieza de copias viejas del programa: solo borra lo que es seguro que es una copia."""

from portal import limpieza


def instalacion(tmp_path):
    programa = tmp_path / "TALLY" / "_Programa"
    for nombre in ("motor", "portal", "README.md"):
        (programa / nombre).mkdir(parents=True) if "." not in nombre else (programa / nombre).write_text("x")
    (tmp_path / "TALLY" / "Datos").mkdir()
    (tmp_path / "TALLY" / "Datos" / "tally.db").write_text("mis datos")
    return programa


def test_borra_copias_del_programa(tmp_path):
    programa = instalacion(tmp_path)
    copia = programa.with_name("_Programa_anterior")
    (copia / "motor").mkdir(parents=True)
    (copia / "README.md").write_text("viejo")
    copia_2 = programa.with_name("_Programa_anterior_2")
    copia_2.mkdir()  # vacía (a medio borrar): también es copia
    limpieza.limpiar_copias(programa, en_segundo_plano=False)
    assert not copia.exists() and not copia_2.exists()
    assert (tmp_path / "TALLY" / "Datos" / "tally.db").read_text() == "mis datos"
    assert programa.exists()


def test_no_borra_lo_que_no_reconoce(tmp_path):
    programa = instalacion(tmp_path)
    sospechosa = programa.with_name("_Programa_anterior")
    sospechosa.mkdir()
    (sospechosa / "mis_notas.txt").write_text("no es del programa")
    limpieza.limpiar_copias(programa, en_segundo_plano=False)
    assert (sospechosa / "mis_notas.txt").exists()


def test_en_desarrollo_no_toca_nada(tmp_path):
    repo = tmp_path / "Tally_PersonalFinance_Software"
    repo.mkdir()
    (tmp_path / "_Programa_anterior").mkdir()
    assert limpieza.copias_viejas(repo) == []
