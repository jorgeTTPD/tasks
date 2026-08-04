#!/usr/bin/env python3
# ═══════════════════════════════════════════════════════════════════
#  Apuntador de Tareas — TUI (Python 3 + Textual)
#
#  Atajos:
#    a            añadir tarea (nombre + descripción)
#    v            ver detalle de la tarea seleccionada
#    d            borrar tarea seleccionada
#    x / Espacio  marcar como completada / pendiente
#    c            limpiar todas las completadas
#    f            cambiar filtro (todas / pendientes / hechas)
#    ↑ ↓ / j k    mover selección
#    q / Esc      salir
#
#  Los datos se guardan automáticamente en ~/.apuntador_tareas/tareas.json
#  (se puede cambiar el directorio con la variable de entorno APUNTADOR_DIR)
#
#  Requisitos:  python3 -m pip install textual
#  Ejecutar:    ./run.sh   o   python3 apuntador.py
# ═══════════════════════════════════════════════════════════════════

from __future__ import annotations

import datetime
import json
import os
from dataclasses import dataclass
from pathlib import Path

from rich.markup import escape
from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import Header, Static

DATA_DIR = Path(os.environ.get("APUNTADOR_DIR", str(Path.home() / ".apuntador_tareas")))
DATA_FILE = DATA_DIR / "tareas.json"


def _ahora() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class Tarea:
    nombre: str = ""
    descripcion: str = ""
    creada: str = ""
    completada: str = ""
    done: bool = False


# ── Persistencia ───────────────────────────────────────────────────

def cargar(archivo: Path = DATA_FILE) -> list[Tarea]:
    """Lee las tareas del JSON. Devuelve [] si no existe o está corrupto."""
    if not Path(archivo).is_file():
        return []
    try:
        raw = json.loads(Path(archivo).read_text(encoding="utf-8"))
        return [
            Tarea(
                nombre=str(t.get("nombre", "")),
                descripcion=str(t.get("descripcion", "")),
                creada=str(t.get("creada", "")),
                completada=str(t.get("completada", "")),
                done=bool(t.get("done", False)),
            )
            for t in raw
        ]
    except Exception:
        return []


def guardar(tareas: list[Tarea], archivo: Path = DATA_FILE) -> None:
    Path(archivo).parent.mkdir(parents=True, exist_ok=True)
    Path(archivo).write_text(
        json.dumps(
            [
                {"nombre": t.nombre, "descripcion": t.descripcion,
                 "creada": t.creada, "completada": t.completada,
                 "done": t.done}
                for t in tareas
            ],
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


class ApuntadorApp(App):
    """TUI del Apuntador de Tareas."""

    TITLE = "Apuntador de Tareas"
    # Transparencia: requiere un terminal con fondo transparente
    # (p. ej. urxvt con depth 32 + alpha + picom). Si no, se ve el
    # fondo por defecto del terminal.
    #
    # background: ansi_default = fondo por defecto del terminal.
    # Con ansi_color=True (constructor) Textual no lo sobreescribe.
    # Trade-off: ansi_color desactiva el alpha-blending de Textual
    # (aceptable: esta app usa colores planos).
    CSS = """
    App, Screen, Header {
        background: ansi_default;
    }

    #summary {
        color: $accent;
        text-style: bold;
        padding: 0 1;
        border-bottom: solid $primary;
    }
    #cols {
        color: $text-muted;
        text-style: bold;
        padding: 0 1;
    }
    #list {
        padding: 0 1;
        height: 1fr;
    }
    #footer {
        padding: 0 1;
        border-top: solid $primary;
    }
    """

    def __init__(self, tareas: list[Tarea] | None = None) -> None:
        # ansi_color=True: Textual deja de forzar fondos true-color por
        # celda (con "transparent" pintaría NEGRO). Así el fondo por
        # defecto del terminal (transparente en urxvt + picom) se ve.
        super().__init__(ansi_color=True)
        self._tareas_inicial: list[Tarea] | None = tareas
        self.tareas: list[Tarea] = []
        self.selected: int = 1          # 1-based, como el original
        self.filtro: str = "todas"      # todas | pendientes | hechas
        self.modo: str = "ver"          # ver | anadir | detalle
        self.campo: str = "nombre"      # campo activo del formulario
        self.input: str = ""            # nombre (en modo añadir)
        self.input_desc: str = ""       # descripción (en modo añadir)
        self.flash: str = ""
        self._flash_timer = None

    # ── Lógica ─────────────────────────────────────────────────────

    def idx_visible(self) -> list[int]:
        return [
            i for i, t in enumerate(self.tareas)
            if self.filtro == "todas"
            or (self.filtro == "pendientes" and not t.done)
            or (self.filtro == "hechas" and t.done)
        ]

    def _guardar(self) -> None:
        guardar(self.tareas)

    def set_flash(self, msg: str) -> None:
        self.flash = msg
        if self._flash_timer is not None:
            self._flash_timer.stop()
        self._flash_timer = self.set_timer(5.0, self._limpiar_flash)

    def _limpiar_flash(self) -> None:
        self.flash = ""
        self._refrescar()

    def anadir(self) -> None:
        nombre = self.input.strip()
        if nombre:
            self.tareas.append(Tarea(
                nombre=nombre,
                descripcion=self.input_desc.strip(),
                creada=_ahora(),
            ))
            self.selected = len(self.idx_visible())
            self.set_flash(f"Añadida ✓  {nombre}")
            self._guardar()
        self.modo = "ver"
        self.campo = "nombre"
        self.input = ""
        self.input_desc = ""
        self._refrescar()

    def marcar(self) -> None:
        ids = self.idx_visible()
        if not ids:
            return
        t = self.tareas[ids[min(self.selected, len(ids)) - 1]]
        t.done = not t.done
        t.completada = _ahora() if t.done else ""
        self.set_flash("Completada ✓" if t.done else "Pendiente otra vez")
        self._guardar()
        self._refrescar()

    def borrar(self) -> None:
        ids = self.idx_visible()
        if not ids:
            return
        i = ids[min(self.selected, len(ids)) - 1]
        nombre = self.tareas[i].nombre
        del self.tareas[i]
        self.selected = min(self.selected, max(1, len(ids) - 1))
        self.set_flash(f"Borrada ✗  {nombre}")
        self._guardar()
        self._refrescar()

    def limpiar(self) -> None:
        n = sum(1 for t in self.tareas if t.done)
        if n > 0:
            self.tareas = [t for t in self.tareas if not t.done]
        self.selected = min(self.selected, max(1, len(self.tareas)))
        msg = f"Limpiadas {n} completadas 🧹" if n > 0 else "No hay completadas que limpiar"
        self.set_flash(msg)
        self._guardar()
        self._refrescar()

    def ciclar_filtro(self) -> None:
        self.filtro = {"todas": "pendientes",
                       "pendientes": "hechas",
                       "hechas": "todas"}[self.filtro]
        self.selected = min(self.selected, max(1, len(self.idx_visible())))
        self.set_flash(f"Filtro: {self.filtro}")
        self._refrescar()

    # ── UI ─────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Vertical():
            yield Static(id="summary")
            yield Static(id="cols")
            yield Static(id="list")
            yield Static(id="footer")

    def on_mount(self) -> None:
        # Si no reciben tareas explícitas, se cargan desde el disco
        self.tareas = self._tareas_inicial if self._tareas_inicial is not None else cargar()
        self._refrescar()

    def on_key(self, event) -> None:
        # Modo añadir: formulario de nombre + descripción
        if self.modo == "anadir":
            event.stop()
            if event.character is not None and event.is_printable:
                if self.campo == "nombre":
                    self.input += event.character
                else:
                    self.input_desc += event.character
                self._refrescar_lista()
            elif event.key == "backspace":
                if self.campo == "nombre":
                    self.input = self.input[:-1]
                else:
                    self.input_desc = self.input_desc[:-1]
                self._refrescar_lista()
            elif event.key == "enter":
                if self.campo == "nombre":
                    self.campo = "descripcion"
                    self._refrescar()
                else:
                    self.anadir()
            elif event.key == "escape":
                self.modo = "ver"
                self.campo = "nombre"
                self.input = ""
                self.input_desc = ""
                self._refrescar()
            return

        # Modo detalle (ver tarea): cualquier tecla vuelve a la lista
        if self.modo == "detalle":
            event.stop()
            self.modo = "ver"
            self._refrescar()
            return

        k = event.key
        if k in ("q", "escape"):
            event.stop()
            self.exit()
        elif k == "a":
            event.stop()
            self.modo = "anadir"
            self.campo = "nombre"
            self.input = ""
            self.input_desc = ""
            self._refrescar()
        elif k == "v":
            event.stop()
            if self.idx_visible():
                self.modo = "detalle"
                self._refrescar()
        elif k == "d":
            event.stop()
            self.borrar()
        elif k in ("x", "w", "space"):
            event.stop()
            self.marcar()
        elif k == "c":
            event.stop()
            self.limpiar()
        elif k == "f":
            event.stop()
            self.ciclar_filtro()
        elif k in ("j", "down"):
            event.stop()
            self.selected = min(self.selected + 1, max(1, len(self.idx_visible())))
            self._refrescar_lista()
        elif k in ("k", "up"):
            event.stop()
            self.selected = max(self.selected - 1, 1)
            self._refrescar_lista()
        elif k == "enter":
            event.stop()
            self.marcar()

    # ── Renderizado ────────────────────────────────────────────────

    def _refrescar(self) -> None:
        self._refrescar_resumen()
        self._refrescar_columnas()
        self._refrescar_lista()
        self._refrescar_footer()

    def _ancho(self) -> int:
        return max(self.size.width, 80)

    def _refrescar_resumen(self) -> None:
        total = len(self.tareas)
        pend = sum(1 for t in self.tareas if not t.done)
        hech = total - pend
        self.query_one("#summary", Static).update(
            f" Tareas: {total}   Pendientes: {pend}   Hechas: {hech}"
            f"   ·   Filtro: {escape(self.filtro)} "
        )

    def _layout(self) -> tuple[int, int, bool, int]:
        """Columnas del listado: (col_estado, col_fecha, con_fechas, max_nombre)."""
        w = self._ancho()
        col_estado, col_fecha = 6, 17
        x_nombre = col_estado
        x_creada = w - 2 * col_fecha - 1
        con_fechas = x_creada > x_nombre + 4
        if not con_fechas:
            x_creada = w
        max_nombre = max(0, x_creada - x_nombre - 1)
        return col_estado, col_fecha, con_fechas, max_nombre

    def _refrescar_columnas(self) -> None:
        # En formulario/detalle no se muestran las cabeceras de columnas
        if self.modo != "ver":
            self.query_one("#cols", Static).update("")
            return
        col_estado, col_fecha, con_fechas, max_nombre = self._layout()
        cab = "Estado".ljust(col_estado) + "Tarea".ljust(max_nombre)
        if con_fechas:
            cab += "  " + "Creada".ljust(col_fecha) + "  " + "Completada"
        self.query_one("#cols", Static).update(cab)

    def _refrescar_lista(self) -> None:
        if self.modo == "anadir":
            self._refrescar_formulario()
            return
        if self.modo == "detalle":
            self._refrescar_detalle()
            return

        _, _, con_fechas, max_nombre = self._layout()
        ids = self.idx_visible()
        n = len(ids)
        self.selected = min(self.selected, max(1, n))

        lineas: list[str] = []
        if n == 0:
            if self.filtro == "todas":
                msg = "  No hay tareas todavía — pulsa [a] para añadir"
            elif self.filtro == "pendientes":
                msg = "  Sin pendientes — ¡todo hecho! 🎉"
            else:
                msg = "  Nada completado todavía"
            lineas.append(f"[dim]{escape(msg)}[/dim]")

        for k, i in enumerate(ids):
            t = self.tareas[i]
            es_sel = k + 1 == self.selected

            chk = escape("[x]") if t.done else escape("[ ]")
            estado = ("▶ " if es_sel else "  ") + chk
            if es_sel:
                estado = f"[bold cyan]{estado}[/]"
            elif t.done:
                estado = f"[green bold]{estado}[/]"

            nombre = t.nombre
            if len(nombre) > max_nombre:
                nombre = nombre[:max_nombre]
            nombre = escape(nombre.ljust(max_nombre))
            if es_sel:
                nombre = f"[bold cyan]{nombre}[/]"
            elif t.done:
                nombre = f"[dim]{nombre}[/]"

            fila = estado + " " + nombre
            if con_fechas:
                creada = escape(t.creada[:16].ljust(16))
                fila += "  " + f"[dim]{creada}[/]"
                if t.done:
                    hecha = escape(t.completada[:16].ljust(16))
                    fila += "  " + f"[green]{hecha}[/]"
            lineas.append(fila)

        self.query_one("#list", Static).update("\n".join(lineas))

    def _refrescar_formulario(self) -> None:
        """Formulario de añadir: nombre + descripción."""
        nom = escape(self.input) + ("▌" if self.campo == "nombre" else "")
        des = escape(self.input_desc) + ("▌" if self.campo == "descripcion" else "")
        if self.campo == "nombre":
            nom = f"[bold cyan]{nom}[/]"
        else:
            des = f"[bold cyan]{des}[/]"
        lineas = [
            "  ── Nueva tarea ──",
            f"  Nombre:      {nom}",
            f"  Descripción: {des}",
        ]
        self.query_one("#list", Static).update("\n".join(lineas))

    def _refrescar_detalle(self) -> None:
        """Ver tarea: muestra todos los datos de la seleccionada."""
        ids = self.idx_visible()
        if not ids:
            self.query_one("#list", Static).update("[dim]  No hay tarea que ver[/dim]")
            return
        sel = min(max(self.selected, 1), len(ids))
        t = self.tareas[ids[sel - 1]]
        estado = "[green bold]Completada ✓[/]" if t.done else "[yellow]Pendiente[/]"
        desc = escape(t.descripcion) if t.descripcion else "[dim]—[/dim]"
        hecha = escape(t.completada) if t.completada else "[dim]—[/dim]"
        lineas = [
            "  ── Tarea ──",
            f"  Nombre:      [bold]{escape(t.nombre)}[/]",
            f"  Descripción: {desc}",
            f"  Creada:      [dim]{escape(t.creada)}[/dim]",
            f"  Completada:  {hecha}",
            f"  Estado:      {estado}",
        ]
        self.query_one("#list", Static).update("\n".join(lineas))

    def _refrescar_footer(self) -> None:
        footer = self.query_one("#footer", Static)
        if self.modo == "anadir":
            paso = " Enter: siguiente campo · Esc: cancelar"
            footer.update(f"[bold cyan]{escape(paso)}[/]")
        elif self.modo == "detalle":
            footer.update("[dim] Pulsa cualquier tecla para volver[/dim]")
        else:
            if self.flash:
                footer.update(f"[bold yellow]  {escape(self.flash)}[/]")
            else:
                hints = (" [a]ñadir  [v]er  [d]borrar  [x/␣]marcar  [c]limpiar"
                         "  [f]filtro  [↑↓]navegar  [q]salir")
                footer.update(f"[dim]{escape(hints)}[/]")

    # ── Punto de entrada ───────────────────────────────────────────

def main() -> None:
    ApuntadorApp().run()


if __name__ == "__main__":
    main()
