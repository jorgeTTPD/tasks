#!/usr/bin/env python3
"""Tests del Apuntador de Tareas (portados de los tests de Julia)."""
import asyncio
import os
import sys
import tempfile
from pathlib import Path

# Redirigir el almacenamiento a un directorio temporal antes de importar
_TMP = tempfile.mkdtemp(prefix="apuntador_test_")
os.environ["APUNTADOR_DIR"] = _TMP
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from apuntador import Tarea, cargar, guardar, ApuntadorApp  # noqa: E402
from textual.widgets import Static  # noqa: E402


def test_persistencia_ida_vuelta():
    arch = Path(_TMP) / "tareas.json"
    tareas = [
        Tarea(nombre="Comprar leche", descripcion="en el supermercado",
              creada="2026-08-03 10:00:00"),
        Tarea(nombre="Terminar proyecto", creada="2026-08-03 11:00:00"),
    ]
    guardar(tareas, arch)
    m2 = cargar(arch)
    assert len(m2) == 2
    assert m2[0].nombre == "Comprar leche"
    assert m2[0].descripcion == "en el supermercado"
    assert m2[0].creada == tareas[0].creada
    assert m2[1].descripcion == ""
    assert not m2[1].done
    print("✅ persistencia ida y vuelta (con descripción)")


def test_archivo_corrupto():
    arch = Path(_TMP) / "corrupto.json"
    arch.write_text("{esto no es json")
    assert cargar(arch) == []
    print("✅ archivo corrupto → lista vacía")


def test_archivo_inexistente():
    assert cargar(Path(_TMP) / "no_existe.json") == []
    print("✅ archivo inexistente → lista vacía")


async def _teclear(pilot, texto: str):
    for ch in texto:
        await pilot.press("space" if ch == " " else ch)


async def _anadir(pilot, nombre, descripcion=""):
    """Pulsa 'a', escribe nombre, Enter, descripción, Enter."""
    await pilot.press("a")
    await _teclear(pilot, nombre)
    await pilot.press("enter")
    if descripcion:
        await _teclear(pilot, descripcion)
    await pilot.press("enter")


async def test_ui_completa():
    async with ApuntadorApp(tareas=[]).run_test() as pilot:
        app = pilot.app

        # ── Backspace y escape en el formulario ──
        await pilot.press("a")
        await _teclear(pilot, "xy")
        await pilot.press("backspace")
        assert app.input == "x"
        await pilot.press("escape")
        assert app.modo == "ver"
        assert app.input == ""

        # ── Añadir con nombre + descripción ──
        await pilot.press("a")
        assert app.modo == "anadir"
        assert app.campo == "nombre"
        await _teclear(pilot, "comprar leche")
        await pilot.press("enter")
        assert app.campo == "descripcion"
        await _teclear(pilot, "en la tienda")
        await pilot.press("enter")
        assert len(app.tareas) == 1
        assert app.tareas[0].nombre == "comprar leche"
        assert app.tareas[0].descripcion == "en la tienda"
        assert not app.tareas[0].done
        assert app.tareas[0].creada != ""
        assert app.modo == "ver"
        # La pantalla se repintó (listado y resumen visibles)
        assert "comprar leche" in app.query_one("#list", Static).content
        assert "Tareas: 1" in app.query_one("#summary", Static).content

        # ── Añadir sin descripción ──
        await _anadir(pilot, "terminar proyecto")
        assert len(app.tareas) == 2
        assert app.tareas[1].nombre == "terminar proyecto"
        assert app.tareas[1].descripcion == ""

        # ── Marcar completada / pendiente ──
        await pilot.press("x")
        assert app.tareas[1].done
        assert app.tareas[1].completada != ""
        assert "Hechas: 1" in app.query_one("#summary", Static).content
        await pilot.press("x")
        assert not app.tareas[1].done
        assert app.tareas[1].completada == ""

        # ── Ver tarea (detalle) ──
        app.selected = 1
        await pilot.press("v")
        assert app.modo == "detalle"
        det = app.query_one("#list", Static).content
        assert "Tarea" in det
        assert "comprar leche" in det
        assert "en la tienda" in det
        # Cualquier tecla vuelve a la lista
        await pilot.press("w")
        assert app.modo == "ver"

        # ── Filtros ──
        app.tareas[0].done = True
        app.tareas[0].completada = "2026-08-03 10:00:00"
        assert len(app.idx_visible()) == 2
        await pilot.press("f")
        assert app.filtro == "pendientes"
        assert len(app.idx_visible()) == 1
        assert app.tareas[app.idx_visible()[0]].nombre == "terminar proyecto"
        await pilot.press("f")
        assert app.filtro == "hechas"
        assert len(app.idx_visible()) == 1
        assert app.tareas[app.idx_visible()[0]].nombre == "comprar leche"
        await pilot.press("f")
        assert app.filtro == "todas"

        # ── Borrar ──
        app.selected = 1
        await pilot.press("d")
        assert len(app.tareas) == 1
        assert app.tareas[0].nombre == "terminar proyecto"

        # ── Limpiar completadas ──
        app.tareas.append(Tarea(nombre="Ya hecha", done=True))
        await pilot.press("c")
        assert len(app.tareas) == 1
        assert app.tareas[0].nombre == "terminar proyecto"

        # ── Navegación ──
        await _anadir(pilot, "otra tarea")
        await pilot.press("k")
        assert app.selected == 1
        await pilot.press("j")
        assert app.selected == 2

        # ── Salir ──
        await pilot.press("q")

    print("✅ UI completa (formulario 2 campos/ver/marcar/filtrar/borrar/limpiar/navegar/salir)")


def main():
    test_persistencia_ida_vuelta()
    test_archivo_corrupto()
    test_archivo_inexistente()
    asyncio.run(test_ui_completa())
    print("\n🎉 Todos los tests pasaron")


if __name__ == "__main__":
    main()
