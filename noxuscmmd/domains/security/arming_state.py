"""El armado con sus dos pasos: qué impide armar y qué hacer al respecto.

Antes, pulsar «armar» armaba y punto — con la puerta del trastero abierta,
armaba igual y esa puerta se quedaba fuera de la vigilancia sin que nadie lo
supiera. Ahora, si hay algo abierto, se dice qué es y se ofrecen las dos
salidas que ofrece una alarma de verdad: armar dejándolo fuera a sabiendas, o
armar en cuanto se cierre.

El desplegable aparece SOLO cuando hay algo abierto. Con todo cerrado —que es
lo normal— pulsar armar sigue siendo un solo toque, que es justo lo que se pidió
para que el uso diario no se vuelva pesado.
"""
import asyncio

import reflex as rx

from . import abiertos, arming, groups_store, logs, retardos
from ..auth import permisos
from . import audit
from ...core import sesiones


class ArmingState(rx.State):
    # Grupo sobre el que se está decidiendo. Vacío = no hay diálogo abierto.
    grupo_id: str = ""
    grupo_nombre: str = ""
    abiertos: list[dict] = []

    # Cuenta atrás de salida en curso (para pintarla)
    contando: str = ""
    restantes: int = 0

    @rx.var
    def hay_dialogo(self) -> bool:
        return self.grupo_id != ""

    @rx.var
    def cuantos_abiertos(self) -> int:
        return len(self.abiertos)

    @rx.event
    async def pedir_armar(self, group_id: str = ""):
        """Punto de entrada de todos los botones de armar.

        Si el grupo está armado, desarma sin preguntar: desarmar nunca puede
        tener fricción — es lo que hace alguien que acaba de entrar en su casa
        con la alarma sonando."""
        if (no := await permisos.denegar(self, permisos.ARMAR)):
            return no

        grupo = (groups_store.ensure_principal_group() if not group_id
                 else next((g for g in groups_store.read_all()
                            if g["id"] == group_id), None))
        if grupo is None:
            return rx.toast.error("Ese grupo ya no existe.", position="top-center")

        quien = await audit.usuario_de(self)

        if grupo["armed"]:
            await arming.set_group_armed(grupo["id"], False, quien)
            return rx.toast.success(f"{grupo['name']} desarmado.",
                                    position="top-center")

        # Si había una cuenta atrás o una espera para este grupo, pulsar otra
        # vez la cancela: el botón hace lo contrario de lo último que hizo.
        if retardos.pendiente(grupo["id"]):
            retardos.cancelar(grupo["id"])
            self.contando = ""
            logs.registrar(logs.GRUPOS, "ARMADO_CANCELADO", quien, "",
                           grupo=grupo["name"])
            return rx.toast.success("Armado cancelado.", position="top-center")

        pendientes = abiertos.con_id_de_grupo(grupo)
        if pendientes:
            self.grupo_id = grupo["id"]
            self.grupo_nombre = grupo["name"]
            self.abiertos = pendientes
            return

        return await self._armar_ya(grupo, quien, [])

    async def _armar_ya(self, grupo: dict, quien: str, bypass: list[str]):
        """Arma, o pone en marcha la cuenta atrás de salida si la hay."""
        salida = retardos.retardo_salida(grupo["id"])
        if salida:
            retardos.programar(grupo["id"], retardos.POR_TIEMPO, salida, quien,
                               bypass)
            self.contando = grupo["id"]
            self.restantes = salida
            logs.registrar(logs.GRUPOS, "SALIDA_EN_CURSO", quien,
                           f"{salida} s para salir", grupo=grupo["name"])
            # Dos eventos: el aviso y el bucle que va bajando el número. El
            # bucle tiene que salir de aquí — poner una bandera y esperar a que
            # alguien la mire no arrancaría nada.
            return [
                rx.toast.success(
                    f"{grupo['name']} se armará en {salida} s. Sal ya.",
                    position="top-center",
                    duration=min(salida * 1000, 10000)),
                ArmingState.contar,
            ]

        if bypass:
            retardos.poner_bypass(grupo["id"], bypass)
        await arming.set_group_armed(grupo["id"], True, quien)
        return rx.toast.success(f"{grupo['name']} armado.", position="top-center")

    @rx.event
    async def armar_excluyendo(self):
        """Armar dejando fuera lo que está abierto. Queda registrado."""
        if (no := await permisos.denegar(self, permisos.ARMAR)):
            return no
        grupo = next((g for g in groups_store.read_all()
                      if g["id"] == self.grupo_id), None)
        if grupo is None:
            self.grupo_id = ""
            return
        quien = await audit.usuario_de(self)
        excluidos = [a["id"] for a in self.abiertos]
        nombres = [a["nombre"] for a in self.abiertos]
        self.grupo_id = ""
        logs.registrar(logs.GRUPOS, "ARMADO_CON_EXCLUSIONES", quien,
                       f"quedan fuera: {', '.join(nombres)}", grupo=grupo["name"])
        return await self._armar_ya(grupo, quien, excluidos)

    @rx.event
    async def armar_al_cerrar(self):
        """Dejarlo dicho: en cuanto cierren, se arma. Lo remata el vigilante."""
        if (no := await permisos.denegar(self, permisos.ARMAR)):
            return no
        grupo = next((g for g in groups_store.read_all()
                      if g["id"] == self.grupo_id), None)
        if grupo is None:
            self.grupo_id = ""
            return
        quien = await audit.usuario_de(self)
        nombre = grupo["name"]
        self.grupo_id = ""
        retardos.programar(grupo["id"], retardos.AL_CERRAR, 0, quien, [])
        logs.registrar(logs.GRUPOS, "ARMADO_AL_CERRAR", quien,
                       "se armará solo cuando cierre todo", grupo=nombre)
        return rx.toast.success(
            f"{nombre} se armará en cuanto cierre todo.",
            position="top-center", duration=8000)

    @rx.event
    def cerrar(self):
        self.grupo_id = ""

    # ── Cuenta atrás visible ─────────────────────────────────────────────
    @rx.event(background=True)
    async def contar(self):
        """Refresca los segundos que quedan, una vez por segundo, y para sola.

        Esto NO arma nada: quien arma es el vigilante, leyendo del disco la hora
        a la que toca. Aquí solo se pinta lo que queda, así que si alguien
        recarga la página en mitad de la cuenta atrás pierde el número pero no
        el armado — que es la parte que importa."""
        guardia = await sesiones.guardia(self)
        while True:
            async with self:
                if not self.contando:
                    return
                ficha = await asyncio.to_thread(retardos.pendiente, self.contando)
                if not ficha:
                    # Ya no está esperando: o lo armó el vigilante o se canceló.
                    self.contando = ""
                    self.restantes = 0
                    return
                self.restantes = retardos.segundos_restantes(ficha)
            if not await sesiones.espera(guardia, 1):
                return

    @rx.event
    async def recuperar_cuenta(self):
        """Al abrir el panel: si hay una cuenta atrás corriendo, engancharse a
        ella. Sin esto, quien abre el panel a mitad de una salida no ve nada y
        parece que no se está armando."""
        for group_id, ficha in retardos.pendientes().items():
            if ficha.get("modo") == retardos.POR_TIEMPO:
                self.contando = group_id
                self.restantes = retardos.segundos_restantes(ficha)
                return ArmingState.contar
        return None

    @rx.event
    async def cancelar_cuenta(self):
        if (no := await permisos.denegar(self, permisos.ARMAR)):
            return no
        if not self.contando:
            return
        grupo_id = self.contando
        retardos.cancelar(grupo_id)
        self.contando = ""
        self.restantes = 0
        quien = await audit.usuario_de(self)
        logs.registrar(logs.GRUPOS, "ARMADO_CANCELADO", quien, "")
        return rx.toast.success("Armado cancelado.", position="top-center")
