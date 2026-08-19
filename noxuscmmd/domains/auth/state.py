"""Quién es esta pestaña y qué puede hacer.

La identidad se sostiene en la cookie firmada (sessions.py), NO en la
suscripción push. Se apoyan la una en la otra pero no dependen: un navegador
al que le han borrado los avisos —o que nunca los aceptó, como un portátil—
sigue siendo el mismo dispositivo y conserva su acceso. La suscripción sirve
para reconocer de entrada a los aparatos que ya estaban dados de alta, que es
lo que evita tener que volver a presentar uno por uno los que ya funcionaban.
"""
import asyncio

import os

import reflex as rx

from . import permisos, sessions, store
from ..security import logs
from ...core import sesiones

# Cada cuánto se comprueba si a este dispositivo le han cambiado el acceso. Tres
# segundos: lo bastante para que quitar un permiso se sienta inmediato y lo
# bastante poco para no leer el fichero sin parar.
_VIGILANCIA = 3.0


class AuthState(rx.State):
    # La cookie. Es pública porque Reflex tiene que poder sincronizarla con el
    # navegador; su contenido no es secreto y va firmado, así que tocarla desde
    # el cliente solo consigue invalidarla.
    # `secure` sale del entorno y no va puesto a fuego. Marcarla significa que
    # el navegador solo la manda por HTTPS, que es lo correcto... salvo que esta
    # casa entra al panel TAMBIEN por HTTP dentro de la LAN
    # (http://192.168.1.x:3000): con secure fijo, esas sesiones dejarian de
    # funcionar y solo se podria entrar por el dominio de fuera. Asi que se deja
    # preparado y se enciende poniendo COOKIE_SECURE=1 en .env el dia que todo
    # el acceso sea por HTTPS.
    #
    # rx.Cookie declara sus flags al arrancar, no por peticion, asi que no se
    # puede decidir "secure si esta conexion es HTTPS": o para todas o para
    # ninguna.
    testigo: str = rx.Cookie(
        name=sessions.NOMBRE_COOKIE,
        max_age=sessions.DURACION,
        path="/",
        same_site="lax",
        secure=os.getenv("COOKIE_SECURE", "") == "1",
    )

    # Lo verificado en el servidor. Con guion bajo delante a propósito: así
    # Reflex no las manda al navegador NI genera un evento `set_` para ellas.
    # Sin el guion, cualquier pestaña conectada podría llamar
    # `set__rol("admin")` y darse permisos sola — que es justo lo que esto
    # viene a impedir.
    _id: str = ""
    _rol: str = store.PENDIENTE
    _nombre: str = ""
    # Copia de si el bloqueo está en vigor. Mientras no lo esté, la interfaz
    # tiene que enseñarlo TODO: el rodaje sirve para ver quién es quién sin
    # quitarle nada a nadie, y esconder botones ya es quitar. Sin esto, un
    # aparato todavía sin reconocer se quedaba sin el botón de armar aunque el
    # sistema le hubiera dejado armar de todas formas — lo peor de los dos
    # mundos: no puede pulsar y encima parece roto.
    _bloqueo: bool = False
    # Si `identificar` ya ha corrido. Hasta entonces no se sabe si este
    # navegador tiene acceso, y no se puede pintar ni el panel (seria
    # ensenarselo a quien no debe) ni la puerta cerrada (un parpadeo de
    # "no tienes acceso" a quien si lo tiene). Se pinta "comprobando".
    _identificado: bool = False
    # Código de una invitación que está esperando a que la persona diga cómo
    # se llama. Mientras no sea "", el panel enseña el alta y nada más.
    invitacion_pendiente: str = ""
    nombre_invitado: str = ""

    # ── Lo que la interfaz puede leer ────────────────────────────────────
    @rx.var
    def rol_actual(self) -> str:
        return self._rol

    @rx.var
    def nombre_rol(self) -> str:
        return store.NOMBRES_DE_ROL.get(self._rol, self._rol)

    @rx.var
    def nombre_dispositivo(self) -> str:
        return self._nombre

    def _ve(self, capacidad: str) -> bool:
        """Si la interfaz debe ENSEÑAR algo. No es lo mismo que poder hacerlo:
        mientras el bloqueo no esté en vigor se enseña todo, porque en rodaje
        nadie debe notar el cambio."""
        return (not self._bloqueo) or permisos.puede_rol(self._rol, capacidad)

    @rx.var
    def registrando(self) -> bool:
        """Hay una invitación válida esperando el nombre de quien la usa."""
        return self.invitacion_pendiente != ""

    @rx.var
    def comprobando(self) -> bool:
        """Todavia no se sabe quien es este navegador."""
        return not self._identificado

    @rx.var
    def es_admin(self) -> bool:
        return self._rol == store.ADMIN

    @rx.var
    def tiene_acceso(self) -> bool:
        return self._ve(permisos.VER)

    @rx.var
    def puede_armar(self) -> bool:
        return self._ve(permisos.ARMAR)

    @rx.var
    def puede_puertas(self) -> bool:
        return self._ve(permisos.PUERTAS)

    @rx.var
    def puede_equipos(self) -> bool:
        return self._ve(permisos.EQUIPOS)

    @rx.var
    def puede_camaras(self) -> bool:
        return self._ve(permisos.CAMARAS)

    @rx.var
    def puede_ajustes(self) -> bool:
        return self._ve(permisos.AJUSTES)

    # ── Preferencias de ESTE aparato (densidad y color de acento) ────────
    # Se leen en _refrescar y se guardan en su ficha, no en un ajuste global:
    # ver auth/store.preferencias.
    densidad: str = store.DENSIDAD_POR_DEFECTO
    acento: str = store.ACENTO_POR_DEFECTO

    @rx.var
    def es_pro(self) -> bool:
        return self.densidad == "pro"

    @rx.event
    def poner_densidad(self, valor: str):
        """La cambia para ESTE aparato. No pide permiso de ajustes: es como se
        ve su propia pantalla, no configuración de la casa — y un invitado en
        una tablet tiene el mismo derecho a ver los botones grandes."""
        if valor not in store.DENSIDADES or not self._id:
            return
        store.actualizar(self._id, densidad=valor)
        self.densidad = valor

    @rx.event
    def poner_acento(self, valor: str):
        if valor not in store.ACENTOS or not self._id:
            return
        store.actualizar(self._id, acento=valor)
        self.acento = valor

    @rx.var
    def densidades_ui(self) -> list[dict]:
        return [
            {"id": "casa", "nombre": "Casa", "detalle": "Cómoda, con aire",
             "activa": self.densidad == "casa"},
            {"id": "pro", "nombre": "Pro", "detalle": "Apretada, cabe más",
             "activa": self.densidad == "pro"},
        ]

    @rx.var
    def acentos_ui(self) -> list[dict]:
        return [{"id": a, "activo": self.acento == a} for a in store.ACENTOS]

    # ── Decisiones ───────────────────────────────────────────────────────
    def _tiene(self, capacidad: str) -> bool:
        """Si este dispositivo puede hacer algo, preguntado EN VIVO.

        Con guion bajo delante para que Reflex NO lo publique como evento: sin
        él aparecía en la lista de eventos invocables desde el navegador. No
        era peligroso —solo devuelve un sí o un no— pero todo lo que se pueda
        llamar desde fuera hay que poder justificarlo, y esto no hace falta.

        No usa `self._rol` a propósito: esa copia es de cuando se cargó la
        pestaña y sirve para pintar. Quitarle el permiso a alguien tiene que
        surtir efecto aunque tenga el panel abierto desde ayer, así que lo que
        decide va a mirar el fichero."""
        return permisos.puede(self._id, capacidad)

    def _refrescar(self) -> None:
        ficha = store.dispositivo(self._id) or {}
        self._rol = store.rol_de(self._id)
        self._nombre = ficha.get("nombre", "")
        self._bloqueo = store.estricto()
        prefs = store.preferencias(self._id)
        self.densidad = prefs["densidad"]
        self.acento = prefs["acento"]
        # _refrescar es el punto por el que pasan los tres caminos de
        # identificar (cookie buena, cookie inservible y sin cookie), asi
        # que es el sitio donde marcarlo una sola vez.
        self._identificado = True

    # ── Vigilancia en vivo ───────────────────────────────────────────────
    @rx.event(background=True)
    async def vigilar_acceso(self):
        """Relee del disco el rol de ESTE dispositivo cada pocos segundos.

        Sin esto, quitarle el acceso a un aparato no surtía efecto hasta que
        alguien recargaba la página: `_rol` es una copia del momento en que se
        cargó la pestaña, y es la que decide qué se pinta. Una tablet colgada en
        la pared con el panel abierto desde ayer seguía enseñándolo todo.

        Lo que se compara es el rol EFECTIVO (store.rol_de ya cuenta la
        caducidad), así que esto es también lo que hace que a un invitado con
        acceso de dos horas se le caiga la pantalla sola al cumplirse la hora, en
        vez de quedarse dentro mientras no toque nada.

        Cuesta una lectura de un JSON pequeño cada tres segundos por sesión: lo
        mismo que ya hacen las demás pantallas para refrescarse, y a cambio quitar
        un permiso es inmediato.
        """
        guardia = await sesiones.guardia(self)
        while True:
            try:
                if not await sesiones.espera(guardia, _VIGILANCIA):
                    return
                async with self:
                    if not self._id:
                        continue
                    rol = await asyncio.to_thread(store.rol_de, self._id)
                    bloqueo = await asyncio.to_thread(store.estricto)
                    if rol != self._rol or bloqueo != self._bloqueo:
                        # Solo se refresca cuando ha cambiado algo: reasignar en
                        # cada vuelta repintaría el panel entero cada tres
                        # segundos en todos los dispositivos.
                        self._refrescar()
            except Exception as e:
                print(f"⚠️ Error vigilando el acceso: {e}")
                if not await sesiones.espera(guardia, 10):
                    return

    # ── Entrada ──────────────────────────────────────────────────────────
    @rx.event
    def identificar(self):
        """Al abrir el panel: resolver quién es este navegador.

        Tres caminos: trae una cookie válida y se le reconoce; trae una cookie
        inservible (caducada, manipulada o de un servidor cuyo secreto ya no
        está) y se le trata como nuevo; o no trae nada y se le abre ficha sin
        permisos, a la espera de que un administrador o una invitación se los
        dé."""
        store.sembrar_si_hace_falta()

        id_dispositivo = sessions.verificar(self.testigo)

        if id_dispositivo and store.dispositivo(id_dispositivo):
            self._id = id_dispositivo
            store.visto(id_dispositivo)
            if sessions.hay_que_renovar(self.testigo):
                self.testigo = sessions.emitir(id_dispositivo)
            self._refrescar()
            return

        # Ficha nueva, sin ningún permiso. Todavía no se registra nada: hasta
        # que no se sepa si es un aparato ya conocido por su suscripción push
        # (vincular_push, justo después), apuntarlo llenaría el registro de
        # "dispositivo nuevo" en cada visita de los de siempre.
        nuevo = sessions.nuevo_id()
        store.alta(nuevo, nombre="", rol=store.PENDIENTE)
        self._id = nuevo
        self.testigo = sessions.emitir(nuevo)
        self._refrescar()

    @rx.event
    def vincular_push(self, endpoint: str, nombre: str = ""):
        """Casa esta sesión con la suscripción de avisos de este aparato.

        Lo llama PushState cuando el navegador le dice cuál es su suscripción.
        Sirve para dos cosas: reconocer de entrada a los que ya estaban dados
        de alta antes de que existieran los permisos —si no, el día del cambio
        se quedaban todos fuera— y para que el nombre que sale en los registros
        y el de la sesión sean el mismo.

        Sobre la confianza: el endpoint lo manda el navegador. Quien conociera
        el de otro aparato podría adoptar su identidad. Es un secreto que solo
        está en este servidor y en el aparato dueño, así que quien lo tenga ya
        ha entrado en uno de los dos; y hasta hoy el panel no pedía nada en
        absoluto, así que esto no abre ninguna puerta que estuviera cerrada.
        """
        if not endpoint:
            return

        id_conocido, _ = store.por_endpoint(endpoint)

        if id_conocido and id_conocido != self._id:
            # Este navegador ya era conocido. Se adopta su ficha —con su rol— y
            # se tira la que se le acababa de abrir, que estaba vacía.
            if self._id and store.rol_de(self._id) == store.PENDIENTE:
                store.eliminar(self._id)
            self._id = id_conocido
            self.testigo = sessions.emitir(id_conocido)
            store.visto(id_conocido)
            # Queda apuntado. Adoptar una ficha por su endpoint es el mecanismo
            # que reconoce a los aparatos de siempre, pero también es la única
            # via por la que una sesión toma la identidad —y el rol— de otra sin
            # que nadie lo autorice: si algún día pasa sin motivo, tiene que
            # poder verse en el registro en vez de no haber ocurrido nunca.
            rol_adoptado = store.rol_de(id_conocido)
            ficha_conocida = store.dispositivo(id_conocido) or {}
            logs.registrar(
                logs.ACCESOS, "DISPOSITIVO_RECONOCIDO",
                ficha_conocida.get("nombre", "") or nombre or "sin nombre",
                f"reconocido por su suscripción de avisos · rol {rol_adoptado}",
                entidad=id_conocido,
            )
            self._refrescar()
            return

        ficha = store.dispositivo(self._id)
        if ficha is None:
            return
        cambios = {}
        if not ficha.get("endpoint"):
            cambios["endpoint"] = endpoint
        if nombre and not ficha.get("nombre"):
            cambios["nombre"] = nombre
        if cambios:
            store.actualizar(self._id, **cambios)
            self._refrescar()
            # Un aparato que aparece por primera vez y se queda esperando
            # permiso. Se avisa AQUÍ y no en `identificar` porque es el primer
            # punto en el que se sabe que es nuevo de verdad: en `identificar`
            # todavía no se ha comprobado si su suscripción push pertenece a un
            # aparato ya conocido que simplemente ha perdido la cookie, y avisar
            # allí llenaría el móvil de falsas alarmas cada vez que alguien de
            # casa borra los datos del navegador.
            if self._rol == store.PENDIENTE:
                self._avisar_de_desconocido(nombre)

    def _avisar_de_desconocido(self, nombre: str) -> None:
        """Deja constancia y avisa a los administradores.

        Se apunta en el registro y además se manda un aviso al móvil: un
        dispositivo desconocido intentando entrar en el panel de una casa es
        justo lo que no se puede quedar esperando a que alguien mire una lista.

        El aviso va SOLO a los administradores, que son quienes pueden decidir,
        y con un tag propio para que dos intentos seguidos no apilen dos avisos.
        """
        como = nombre or "sin nombre"
        # La marca de «está llamando a la puerta», que NO es lo mismo que tener
        # el rol «Sin acceso». Sin separarlas, poner a un aparato en «Sin
        # acceso» lo devolvía al aviso de desconocidos, y el aviso volvía a
        # saltar una y otra vez por una decisión que ya se había tomado.
        # La quita el administrador al decidir (ver AuthAdminState.cambiar_rol).
        store.actualizar(self._id, pide_acceso=True)
        logs.registrar(logs.ACCESOS, "DISPOSITIVO_NUEVO", como,
                       "pide acceso al panel")
        try:
            from ..notifications.push import enviar_notificacion
            admins = [f.get("nombre") for f in store.leer()["dispositivos"].values()
                      if f.get("rol") == store.ADMIN and f.get("nombre")]
            if admins:
                enviar_notificacion(
                    "🔓 Dispositivo desconocido",
                    f"«{como}» ha intentado entrar en el panel. Dale acceso o "
                    f"bloquéalo desde Ajustes → Dispositivos.",
                    admins, "acceso:desconocido",
                )
        except Exception as e:
            print(f"⚠️ No se pudo avisar del dispositivo desconocido: {e}")

    # ── Invitaciones: el lado de quien la recibe ─────────────────────────
    @rx.event
    def canjear_de_la_url(self):
        """Entrar con una invitación: /panel?invitacion=<código>.

        Se comprueba después de identificar, así que quien llega con un enlace
        válido pasa de no tener acceso a tenerlo sin más pasos: abre el enlace y
        ya está dentro. Un código inválido o caducado no dice por qué con
        detalle, solo que no vale."""
        codigo = self.router.url.query_parameters.get("invitacion", "")
        if not codigo or not self._id:
            return
        if permisos.puede(self._id, permisos.VER):
            return  # ya tenía acceso: la invitación no le hace falta

        # Antes de dejarle entrar se le pregunta cómo se llama, salvo que ya
        # traiga nombre de su suscripción push. No es burocracia: ese nombre es
        # el que queda escrito en cada línea del registro junto a lo que haga, y
        # sin él todo lo que toque un invitado se apunta como «Invitado», que en
        # una casa con dos invitados no distingue a nadie. Ver `registrarse`.
        if not self._nombre:
            self.invitacion_pendiente = codigo
            return

        return self._canjear(codigo, self._nombre)

    @rx.event
    def set_nombre_invitado(self, valor: str):
        self.nombre_invitado = valor

    @rx.event
    def registrarse(self):
        """Alta de un invitado con su nombre, por el tiempo que dure el enlace.

        El acceso NO se hace permanente por darse un nombre: la caducidad la pone
        la invitación (ver store.canjear) y cuando pasa la hora, rol_de deja de
        devolver su rol y el acceso se cae solo, sin que nadie tenga que ir a
        borrarlo."""
        nombre = self.nombre_invitado.strip()
        if len(nombre) < 2:
            return rx.toast.error("Escribe tu nombre para entrar.",
                                  position="top-center")
        codigo = self.invitacion_pendiente
        if not codigo:
            return
        self.invitacion_pendiente = ""
        return self._canjear(codigo, nombre)

    def _canjear(self, codigo: str, nombre: str):
        ok, motivo = store.canjear(codigo, self._id, nombre=nombre)
        self._refrescar()
        if not ok:
            return rx.toast.error(motivo, position="top-center")

        inv = store.invitacion(codigo) or {}
        logs.registrar(
            logs.ACCESOS, "INVITACION_USADA", nombre or "invitado",
            f"invitación de {inv.get('creada_por', '?')} — "
            f"acceso hasta {_cuando(inv.get('caduca'))}",
        )
        return rx.toast.success(
            f"Acceso concedido hasta {_cuando(inv.get('caduca'))}.",
            position="top-center", duration=8000,
        )


def _cuando(marca: float | None) -> str:
    if not marca:
        return "sin fecha"
    from datetime import datetime
    return datetime.fromtimestamp(marca).strftime("%d/%m/%Y %H:%M")
