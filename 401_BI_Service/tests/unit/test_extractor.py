from extractor import Extractor
from tests.unit.fakes import FakeCliente


def test_recorre_todo_y_solo_pide_refresh_de_datasets_actualizables():
    cliente = FakeCliente()
    inv = Extractor(cliente, 10).extraer()
    assert len(inv.workspaces) == 2
    assert len(inv.datasets) == 3
    assert len(inv.informes) == 1
    assert len(inv.actualizaciones) == 2
    assert cliente.llamadas_refresh == ["ds-1", "ds-3"]  # ds-2 (DirectQuery) no
    assert inv.errores == []


def test_error_de_un_dataset_no_corta_la_corrida():
    inv = Extractor(FakeCliente(sin_acceso={"ds-1"}), 10).extraer()
    assert len(inv.datasets) == 3
    assert inv.actualizaciones == []
    assert [(e["NIVEL"], e["OBJETO"], e["HTTP"]) for e in inv.errores] == [("DATASET", "Modelo Ventas", 403)]


def test_error_de_un_workspace_sigue_con_los_demas():
    inv = Extractor(FakeCliente(sin_acceso={"ws-1"}), 10).extraer()
    assert [d["id"] for d in inv.datasets] == ["ds-3"]
    assert inv.errores[0]["WORKSPACE"] == "Ventas"


def test_filtro_por_nombre_o_id_sin_distinguir_mayusculas():
    assert [w["id"] for w in Extractor(FakeCliente()).extraer(["ventas"]).workspaces] == ["ws-1"]
    assert [w["id"] for w in Extractor(FakeCliente()).extraer(["WS-2"]).workspaces] == ["ws-2"]
