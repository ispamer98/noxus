"""
Estado reactivo de la pestaña Automatizaciones.

Dos cosas que conviene tener claras al leer esto:

1. El catálogo se REHACE en cada _reload(), y _reload() corre tras cada alta o
   baja y en el sync_loop. Por eso una luz dada de alta en otra pestaña aparece
   aquí como acción en menos de dos segundos, sin recargar la página.

2. Mientras se edita, los ajustes de cada paso se guardan como TEXTO
   (dict[str, str]). Es lo que devuelven los campos del formulario, y mezclar
   tipos en una Var de Reflex es fuente segura de sorpresas. La conversión al
   tipo de verdad (número, lista de días, booleano) se hace en un solo sitio,
   al guardar, usando la declaración del propio campo.
"""
import time

import reflex as rx

from ..auth import permisos

from . import catalog, engine, store
from ..nodes import store as nodes_store
from ..security import audit, logs
from ...core import sesiones

# Secciones del editor. El nombre es el que se pasa a los eventos para saber
# sobre cuál de las tres listas se está operando.
DISPARADORES, CONDICIONES, ACCIONES = "triggers", "conditions", "actions"


def _a_texto(params: dict, campos: list[dict]) -> dict[str, str]:
    """Lo guardado -> lo que enseña el formulario."""
    salida = {}
    for campo in campos:
        valor = params.get(campo["name"], campo.get("default"))
        if campo["kind"] == "days":
            salida[campo["name"]] = ",".join(str(d) for d in (valor or []))
        elif campo["kind"] == "bool":
            salida[campo["name"]] = "true" if valor else "false"
        else:
            salida[campo["name"]] = "" if valor is None else str(valor)
    return salida


def _a_json(params: dict[str, str], campos: list[dict]) -> dict:
    """Lo que enseña el formulario -> lo que se guarda, ya con su tipo."""
    salida = {}
    for campo in campos:
        crudo = params.get(campo["name"], "")
        if campo["kind"] == "days":
            salida[campo["name"]] = sorted(
                int(d) for d in str(crudo).split(",") if d.strip().isdigit())
        elif campo["kind"] == "bool":
            salida[campo["name"]] = str(crudo).lower() in ("true", "1", "on")
        elif campo["kind"] == "number":
            try:
                numero = float(crudo)
                salida[campo["name"]] = int(numero) if numero.is_integer() else numero
            except (TypeError, ValueError):
                salida[campo["name"]] = campo.get("default", 0)
        else:
            salida[campo["name"]] = str(crudo)
    return salida


def _cuando(marca: float) -> str:
    if not marca:
        return "nunca"
    segundos = max(0, int(time.time() - marca))
    if segundos < 60:
        return "hace un momento"
    if segundos < 3600:
        return f"hace {segundos // 60} min"
    if segundos < 86400:
        return f"hace {segundos // 3600} h"
    return f"hace {segundos // 86400} días"


class AutomationsState(rx.State):
    rules: list[dict] = []
    folders: list[dict] = []

    # Catálogo vivo, en tres listas de secciones ya agrupadas.
    cat_triggers: list[dict] = []
    cat_conditions: list[dict] = []
    cat_actions: list[dict] = []

    status: str = ""

    # ── Editor ───────────────────────────────────────────────────────────
    editing: bool = False
    draft_id: str = ""
    draft_name: str = ""
    draft_icon: str = "workflow"
    draft_folder: str = ""
    draft_match: str = "all"
    draft_cooldown: str = "60"
    draft_triggers: list[dict] = []
    draft_conditions: list[dict] = []
    draft_actions: list[dict] = []

    # ── Selector ─────────────────────────────────────────────────────────
    picker_for: str = ""          # "" = cerrado; si no, la sección que lo abrió
    picker_query: str = ""

    # ── Carga ────────────────────────────────────────────────────────────
    @rx.event
    def on_load(self):
        self._reload()
        return AutomationsState.sync_loop

    def _reload(self):
        datos = nodes_store.read_all()
        try:
            reglas = store.read_all()
        except store.ArchivoCorrupto as e:
            self.status = f"⛔ {e}"
            return
        etiquetas = catalog.labels(datos)
        estados = store.read_state()
        self.folders = store.list_folders()
        self.rules = [
            {
                **r,
                "summary": catalog.resumir(r, etiquetas),
                "last_run_text": _cuando(float(estados.get(r["id"], {}).get("last_run", 0) or 0)),
                "last_result": estados.get(r["id"], {}).get("last_result", ""),
                "last_error": estados.get(r["id"], {}).get("last_error", ""),
                "folder_name": next(
                    (c["name"] for c in self.folders if c["id"] == r["folder_id"]), ""),
            }
            for r in reglas
        ]
        self.cat_triggers = catalog.build_trigger_catalog(datos)
        self.cat_conditions = catalog.build_condition_catalog(datos)
        self.cat_actions = catalog.build_action_catalog(datos)

    @rx.event(background=True)
    async def sync_loop(self):
        """Una por sesión: refleja lo que cambie el motor (última ejecución,
        una regla que se desactive sola) y rehace el catálogo para que el
        hardware dado de alta en otra pestaña aparezca aquí."""
        guardia = await sesiones.guardia(self)
        while True:
            try:
                async with self:
                    if not self.editing:
                        # Mientras se edita NO se recarga: reconstruir las
                        # listas debajo del formulario haría saltar lo que se
                        # está escribiendo.
                        self._reload()
                if not await sesiones.espera(guardia, 2):
                    return
            except Exception as e:
                print(f"⚠️ Error en AutomationsState.sync_loop: {e}")
                if not await sesiones.espera(guardia, 2):
                    return

    @rx.var
    def hay_reglas(self) -> bool:
        return bool(self.rules)

    @rx.var
    def rules_by_id(self) -> dict[str, dict]:
        """Para el widget "Estado de una automatización" del Resumen — mismo
        criterio que GroupsState.groups_by_id: recorrer self.rules dentro de
        un rx.foreach para encontrar UNA regla concreta no se puede hacer,
        así que se resuelve aquí como diccionario."""
        return {r["id"]: r for r in self.rules}

    @rx.var
    def rules_by_folder(self) -> dict[str, list[dict]]:
        """Agrupadas por carpeta, resuelto aquí y no en el frontend: filtrar
        una lista dentro de un rx.foreach obliga a condicionales anidados por
        cada fila."""
        salida: dict[str, list[dict]] = {c["id"]: [] for c in self.folders}
        for r in self.rules:
            if r["folder_id"] in salida:
                salida[r["folder_id"]].append(r)
        return salida

    @rx.var
    def rules_sin_carpeta(self) -> list[dict]:
        carpetas = {c["id"] for c in self.folders}
        return [r for r in self.rules if r["folder_id"] not in carpetas]

    @rx.var
    def titulo_editor(self) -> str:
        return "Editar automatización" if self.draft_id else "Nueva automatización"

    # ── Lista ────────────────────────────────────────────────────────────
    @rx.event
    async def toggle_rule(self, rule_id: str):
        # Editar la instalacion es cosa de administradores: «familia»
        # puede USAR todo y no cambiar nada (ver auth/permisos.py).
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        regla = next((r for r in self.rules if r["id"] == rule_id), None)
        if regla is None:
            return
        nuevo = not regla["enabled"]
        store.set_enabled(rule_id, nuevo)
        self._reload()
        await audit.registrar(
            self, logs.AUTOMATIZACIONES,
            "AUTOMATIZACION_ACTIVADA_MANUAL" if nuevo else "AUTOMATIZACION_DESACTIVADA_MANUAL",
            regla["name"], entidad=rule_id)

    @rx.event
    async def delete_rule(self, rule_id: str):
        # Editar la instalacion es cosa de administradores: «familia»
        # puede USAR todo y no cambiar nada (ver auth/permisos.py).
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        nombre = next((r["name"] for r in self.rules if r["id"] == rule_id), rule_id)
        store.delete_rule(rule_id)
        self._reload()
        await audit.registrar(self, logs.AUTOMATIZACIONES, "AUTOMATIZACION_ELIMINADA",
                              nombre, entidad=rule_id)

    @rx.event
    def duplicate_rule(self, rule_id: str):
        copia = store.duplicate_rule(rule_id)
        self._reload()
        if copia:
            self.status = f"📋 Copiada como «{copia['name']}» — está desactivada hasta que la revises."

    @rx.event(background=True)
    async def run_now(self, rule_id: str):
        # Una regla puede llevar dentro un pulso de puerta o un armado, así que
        # lanzarla a mano vale tanto como el paso más gordo que contenga. Sin un
        # mapa de tipo-de-paso a capacidad se pide lo mismo que sus hermanos:
        # AJUSTES (ver auth/permisos.py).
        async with self:
            no = await permisos.denegar(self, permisos.AJUSTES)
        if no:
            yield no
            return
        async with self:
            self.status = "▶️ Ejecutando..."
        try:
            detalle = await engine.ejecutar_ahora(rule_id)
            mensaje = f"✅ Ejecutada: {detalle}"
        except Exception as e:
            mensaje = f"❌ {e}"
        async with self:
            self.status = mensaje
            self._reload()

    # ── Carpetas ─────────────────────────────────────────────────────────
    @rx.event
    async def submit_add_folder(self, form_data: dict):
        # Editar la instalacion es cosa de administradores: «familia»
        # puede USAR todo y no cambiar nada (ver auth/permisos.py).
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        nombre = (form_data.get("name") or "").strip()
        if nombre:
            store.add_folder(nombre)
            self._reload()

    @rx.event
    async def delete_folder(self, folder_id: str):
        # Editar la instalacion es cosa de administradores: «familia»
        # puede USAR todo y no cambiar nada (ver auth/permisos.py).
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        store.delete_folder(folder_id)
        self._reload()

    # ── Editor ───────────────────────────────────────────────────────────
    @staticmethod
    def _campos(clave: str) -> list[dict]:
        """La declaración de los ajustes, normalizada para el frontend: TODOS
        los campos con exactamente las mismas claves y las opciones como
        diccionarios.

        Los dos detalles importan. Un campo al que le falte una clave hace que
        el frontend lea `undefined` al pintarlo, y una lista de pares
        ["on", "Encender"] obliga a indexar por posición dentro de un foreach,
        que es justo donde el tipado de Reflex se pierde."""
        return [{
            "name": c["name"],
            "kind": c["kind"],
            "label": c.get("label", ""),
            "help": c.get("help", ""),
            "min": str(c.get("min", "")),
            "max": str(c.get("max", "")),
            "options": [{"v": str(v), "t": t} for v, t in c.get("options", [])],
        } for c in catalog.params_de(clave)]

    def _fila(self, clave: str, target: str, params: dict, extra: dict | None = None,
              etiquetas: dict | None = None) -> dict:
        """Una fila del editor: lo que se guarda + lo que hace falta para
        pintarla (su frase y la declaración de sus campos).

        `etiquetas` se puede pasar hecho: abrir una regla construye una fila por
        cada disparador, condición y acción, y calcularlo dentro significaría
        releer el almacén entero una vez por fila."""
        campos = self._campos(clave)
        etiquetas = catalog.labels() if etiquetas is None else etiquetas
        if clave in catalog.TRIGGERS_BY_KIND:
            texto = catalog.frase_predicado(
                {"kind": clave, "target": target, "params": params}, etiquetas,
                catalog.TRIGGERS_BY_KIND)
        elif clave in catalog.CONDITIONS_BY_KIND:
            texto = catalog.frase_predicado(
                {"kind": clave, "target": target, "params": params}, etiquetas,
                catalog.CONDITIONS_BY_KIND)
        else:
            texto = catalog.frase_accion(
                {"type": clave, "target": target, "params": params,
                 "repeat": (extra or {}).get("repeat", 1)}, etiquetas)
        return {
            "kind": clave, "target": target,
            "params": _a_texto(params, catalog.params_de(clave)),
            "fields": campos,
            "text": texto,
            "repeat": str((extra or {}).get("repeat", 1)),
            "repeat_pause": str((extra or {}).get("repeat_pause", 0.4)),
            "continue_on_error": bool((extra or {}).get("continue_on_error", False)),
        }

    # Los cuatro campos de la ficha. Escritos a mano en vez de dejar que Reflex
    # genere los set_* automáticos: esos están marcados como obsoletos y dejan
    # de existir en la 0.9.
    @rx.event
    def set_draft_name(self, valor: str):
        self.draft_name = valor

    @rx.event
    def set_draft_folder(self, valor: str):
        self.draft_folder = valor

    @rx.event
    def set_draft_match(self, valor: str):
        self.draft_match = valor

    @rx.event
    def set_draft_cooldown(self, valor: str):
        self.draft_cooldown = valor

    @rx.event
    def new_rule(self):
        self.draft_id = ""
        self.draft_name = ""
        self.draft_icon = "workflow"
        self.draft_folder = ""
        self.draft_match = "all"
        self.draft_cooldown = "60"
        self.draft_triggers = []
        self.draft_conditions = []
        self.draft_actions = []
        self.status = ""
        self.editing = True

    @rx.event
    def edit_rule(self, rule_id: str):
        regla = store.get_rule(rule_id)
        if regla is None:
            return
        self.draft_id = regla["id"]
        self.draft_name = regla["name"]
        self.draft_icon = regla["icon"]
        self.draft_folder = regla["folder_id"]
        self.draft_match = regla["match"]
        self.draft_cooldown = str(regla["cooldown_seconds"])
        etiquetas = catalog.labels()
        self.draft_triggers = [self._fila(t["kind"], t["target"], t["params"], None, etiquetas)
                               for t in regla["triggers"]]
        self.draft_conditions = [self._fila(c["kind"], c["target"], c["params"], None, etiquetas)
                                 for c in regla["conditions"]]
        self.draft_actions = [self._fila(a["type"], a["target"], a["params"], a, etiquetas)
                              for a in regla["actions"]]
        self.status = ""
        self.editing = True

    @rx.event
    def cancel_edit(self):
        self.editing = False
        self.picker_for = ""
        self._reload()

    @rx.event
    async def save_rule(self):
        # Editar la instalacion es cosa de administradores: «familia»
        # puede USAR todo y no cambiar nada (ver auth/permisos.py).
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        nombre = self.draft_name.strip()
        if not nombre:
            self.status = "⚠️ Ponle un nombre a la automatización."
            return
        if not self.draft_actions:
            self.status = "⚠️ Una automatización sin acciones no haría nada — añade al menos una."
            return

        def predicados(filas):
            return [{"kind": f["kind"], "target": f["target"],
                     "params": _a_json(f["params"], catalog.params_de(f["kind"]))}
                    for f in filas]

        acciones = [{
            "type": f["kind"], "target": f["target"],
            "params": _a_json(f["params"], catalog.params_de(f["kind"])),
            "repeat": f["repeat"], "repeat_pause": f["repeat_pause"],
            "continue_on_error": f["continue_on_error"],
        } for f in self.draft_actions]

        campos = dict(
            name=nombre, icon=self.draft_icon, folder_id=self.draft_folder,
            match=self.draft_match, cooldown_seconds=self.draft_cooldown,
            triggers=predicados(self.draft_triggers),
            conditions=predicados(self.draft_conditions),
            actions=acciones,
            # Guardar una regla rota la desatasca: el motivo de la desactivación
            # automática se limpia para que vuelva a poder activarse.
            disabled_reason="",
        )
        if self.draft_id:
            store.update_rule(self.draft_id, **campos)
            accion = "AUTOMATIZACION_EDITADA"
            rid = self.draft_id
        else:
            # Nace apagada: encenderla es un acto consciente, y una regla que
            # acciona relés no debe empezar a hacerlo por el mero hecho de
            # haberla guardado.
            creada = store.add_rule(enabled=False, **campos)
            accion = "AUTOMATIZACION_CREADA"
            rid = creada["id"]
        self.editing = False
        self.picker_for = ""
        self._reload()
        self.status = ("💾 Guardada." if self.draft_id
                       else "💾 Creada y desactivada — actívala cuando la hayas revisado.")
        await audit.registrar(self, logs.AUTOMATIZACIONES, accion, nombre, entidad=rid)

    # ── Filas del editor ─────────────────────────────────────────────────
    def _lista(self, seccion: str) -> list[dict]:
        return {DISPARADORES: self.draft_triggers,
                CONDICIONES: self.draft_conditions,
                ACCIONES: self.draft_actions}[seccion]

    def _guardar_lista(self, seccion: str, filas: list[dict]) -> None:
        if seccion == DISPARADORES:
            self.draft_triggers = filas
        elif seccion == CONDICIONES:
            self.draft_conditions = filas
        else:
            self.draft_actions = filas

    def _refrescar_texto(self, seccion: str, filas: list[dict]) -> None:
        """Rehace la frase de cada fila tras tocar un ajuste, para que lo que
        se lee coincida con lo que se ha elegido."""
        etiquetas = catalog.labels()
        for fila in filas:
            params = _a_json(fila["params"], catalog.params_de(fila["kind"]))
            if seccion == ACCIONES:
                fila["text"] = catalog.frase_accion(
                    {"type": fila["kind"], "target": fila["target"],
                     "params": params, "repeat": int(float(fila["repeat"] or 1))}, etiquetas)
            else:
                tabla = (catalog.TRIGGERS_BY_KIND if seccion == DISPARADORES
                         else catalog.CONDITIONS_BY_KIND)
                fila["text"] = catalog.frase_predicado(
                    {"kind": fila["kind"], "target": fila["target"], "params": params},
                    etiquetas, tabla)

    @rx.event
    def remove_row(self, seccion: str, indice: int):
        filas = [f for i, f in enumerate(self._lista(seccion)) if i != indice]
        self._guardar_lista(seccion, filas)

    @rx.event
    def move_action(self, indice: int, salto: int):
        filas = list(self.draft_actions)
        destino = indice + salto
        if 0 <= destino < len(filas):
            filas[indice], filas[destino] = filas[destino], filas[indice]
            self.draft_actions = filas

    @rx.event
    def set_param(self, seccion: str, indice: int, nombre: str, valor):
        filas = list(self._lista(seccion))
        if not 0 <= indice < len(filas):
            return
        filas[indice]["params"][nombre] = str(valor)
        self._refrescar_texto(seccion, filas)
        self._guardar_lista(seccion, filas)

    @rx.event
    def toggle_day(self, seccion: str, indice: int, nombre: str, dia: int):
        filas = list(self._lista(seccion))
        if not 0 <= indice < len(filas):
            return
        actuales = {int(d) for d in str(filas[indice]["params"].get(nombre, "")).split(",")
                    if d.strip().isdigit()}
        actuales.symmetric_difference_update({dia})
        filas[indice]["params"][nombre] = ",".join(str(d) for d in sorted(actuales))
        self._refrescar_texto(seccion, filas)
        self._guardar_lista(seccion, filas)

    @rx.event
    def set_action_field(self, indice: int, campo: str, valor):
        filas = list(self.draft_actions)
        if not 0 <= indice < len(filas):
            return
        filas[indice][campo] = valor if campo == "continue_on_error" else str(valor)
        self._refrescar_texto(ACCIONES, filas)
        self.draft_actions = filas

    # ── Selector ─────────────────────────────────────────────────────────
    @rx.event
    def open_picker(self, seccion: str):
        self.picker_query = ""
        self.picker_for = seccion

    @rx.event
    def close_picker(self):
        self.picker_for = ""

    @rx.event
    def picker_open_change(self, abierto: bool):
        """Escape y el clic fuera del diálogo llegan por aquí."""
        if not abierto:
            self.picker_for = ""

    @rx.event
    def set_picker_query(self, texto: str):
        self.picker_query = texto

    @rx.var
    def picker_title(self) -> str:
        return {DISPARADORES: "Añadir disparador",
                CONDICIONES: "Añadir condición",
                ACCIONES: "Añadir acción"}.get(self.picker_for, "")

    @rx.var
    def picker_sections(self) -> list[dict]:
        """Las secciones del selector, ya filtradas por el buscador. El filtro
        se hace AQUÍ, en Python, y no en el frontend: recorrer y comparar
        cadenas dentro de rx.foreach obliga a montar condicionales anidados que
        no se leen ni se mantienen."""
        origen = {DISPARADORES: self.cat_triggers,
                  CONDICIONES: self.cat_conditions,
                  ACCIONES: self.cat_actions}.get(self.picker_for, [])
        busca = self.picker_query.strip().lower()
        if not busca:
            return origen
        salida = []
        for seccion in origen:
            opciones = [o for o in seccion["options"]
                        if busca in o["label"].lower() or busca in seccion["label"].lower()]
            if opciones:
                salida.append({**seccion, "options": opciones})
        return salida

    @rx.event
    def pick(self, valor: str):
        """`valor` es "<kind>|<target>" — lo que compone catalog._opciones_de."""
        seccion = self.picker_for
        if not seccion:
            return
        clave, _, target = valor.partition("|")
        campos = catalog.params_de(clave)
        # Los valores por defecto se materializan YA, para que la fila recién
        # añadida se lea entera desde el primer momento en vez de aparecer con
        # huecos hasta que alguien toque cada campo.
        params = {c["name"]: c.get("default") for c in campos}
        filas = list(self._lista(seccion))
        filas.append(self._fila(clave, target, params))
        self._guardar_lista(seccion, filas)
        self.picker_for = ""
