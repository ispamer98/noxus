"""
Estado propio del Centro de Control (/panel): navegación del sidebar y qué
ventanas flotantes están abiertas. Deliberadamente no toca ningún domain
state existente (SecurityState, InfraState, CameraState, PushState) — el
dashboard nuevo solo los *lee* y les reenvía eventos, igual que hace la
vista clásica.
"""
import reflex as rx


class DashboardState(rx.State):
    sidebar_collapsed: bool = False
    active_view: str = "overview"

    # ids de ventana abiertas, en orden de apertura (no se usa para z-index:
    # eso lo gestiona el script de arrastre en el propio DOM)
    open_windows: list[str] = []

    # Modo edición de la pestaña Resumen: mientras está activo, cada widget
    # muestra sus controles de mover/quitar y aparece el botón "Añadir widget".
    editing_overview: bool = False

    def toggle_editing_overview(self):
        self.editing_overview = not self.editing_overview

    # Qué grupos de accesos rápidos del Resumen están DESPLEGADOS ahora mismo
    # (Luces, Puertas, Mandos...) — el resto de familias se ven recogidas, solo
    # con su cabecera, hasta que se tocan. Es justo "por grupos pero recogidos,
    # que se puedan abrir con un clic": una persona que solo quiere encender
    # una luz no tiene que ver primero los botones de las puertas, los mandos y
    # los equipos.
    open_action_families: list[str] = []

    def toggle_action_family(self, family_id: str):
        if family_id in self.open_action_families:
            self.open_action_families = [f for f in self.open_action_families if f != family_id]
        else:
            self.open_action_families = [*self.open_action_families, family_id]

    # El bloque "Más información" (contadores, nº de equipos, rejilla de
    # equipos con su ping...) del Resumen — recogido por defecto: es
    # información de "cómo está instalado esto", no algo que se accione, así
    # que no debe competir por espacio con los accesos rápidos.
    show_overview_extra: bool = False

    def toggle_overview_extra(self):
        self.show_overview_extra = not self.show_overview_extra

    # Modo organizar de la pestaña Equipos: mientras está activo cada tarjeta
    # muestra las flechas de subir/bajar y no se despliega al pulsarla, para
    # poder recolocarlas sin abrir la ficha de cada una sin querer.
    editing_equipment: bool = False

    def toggle_editing_equipment(self):
        self.editing_equipment = not self.editing_equipment

    # Modo edición del plano de planta: mientras está activo los marcadores se
    # arrastran para recolocarlos y su clic NO ejecuta su acción (abrir puerta,
    # encender luz...). Apagado por defecto para que el uso normal del plano no
    # mueva iconos sin querer.
    editing_floor_plan: bool = False

    def toggle_editing_floor_plan(self):
        self.editing_floor_plan = not self.editing_floor_plan

    def set_view(self, view: str):
        self.active_view = view

    # Las pestañas de configuración ya no tienen fila propia en el menú: se
    # llega a ellas desde "Ajustes" (ver dashboard/views/settings_hub.py). Sin
    # esto, estar dentro de "Alarma" no dejaría NINGUNA fila del menú marcada
    # como activa y el usuario perdería la referencia de dónde está.
    # "equipment" NO está aquí: tiene fila propia en el menú (ver sidebar.py).
    _EN_AJUSTES = ("alarm", "groups", "access", "cctv", "lights", "ir_remotes", "automations")

    @rx.var
    def settings_hub_active(self) -> bool:
        return self.active_view in self._EN_AJUSTES or self.active_view == "settings_hub"

    def toggle_sidebar(self):
        self.sidebar_collapsed = not self.sidebar_collapsed

    # Ventanas abiertas en modo "compacto": solo el contenido, sin los
    # controles de edición. Es lo que distingue abrir un mando desde el plano
    # (se quiere usar: teclas y nada más, y se cierra al tocar fuera) de
    # abrirlo desde la pestaña Mandos IR (el taller: añadir botones,
    # recolocarlos, editarlos).
    compact_windows: list[str] = []

    def open_window(self, window_id: str):
        self.compact_windows = [w for w in self.compact_windows if w != window_id]
        if window_id not in self.open_windows:
            self.open_windows.append(window_id)

    def open_window_compact(self, window_id: str):
        if window_id not in self.compact_windows:
            self.compact_windows.append(window_id)
        if window_id not in self.open_windows:
            self.open_windows.append(window_id)

    def close_window(self, window_id: str):
        if window_id in self.open_windows:
            self.open_windows.remove(window_id)

    def toggle_window(self, window_id: str):
        if window_id in self.open_windows:
            self.open_windows.remove(window_id)
        else:
            self.open_windows.append(window_id)
