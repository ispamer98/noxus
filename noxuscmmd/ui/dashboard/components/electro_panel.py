"""Paneles de actuación de los seis electrodomésticos simulados."""
import reflex as rx

from ....domains.electro.state import ElectroState
from .panel_control import (anillo, boton_control, panel, panel_cabecera,
                            segmentado, stepper)


ICONOS = {
    "lavadora": "washing-machine", "nevera": "refrigerator",
    "placa": "flame", "horno": "microwave",
    "extractor": "fan", "freidora": "cooking-pot", "aire": "air-vent",
}


def _cmd(eid, accion: str, valor=""):
    return ElectroState.electro_cmd(eid, accion, valor)


def _acciones_ciclo(eid, fase) -> rx.Component:
    return rx.el.div(
        rx.cond(fase == "pausada",
                boton_control("play", "Reanudar", _cmd(eid, "reanudar"), "safe"),
                rx.cond((fase == "lavado") | (fase == "aclarado") |
                        (fase == "centrifugado") | (fase == "cocinando"),
                        boton_control("pause", "Pausar", _cmd(eid, "pausar"), "warn"),
                        boton_control("play", "Iniciar", _cmd(eid, "iniciar"), "safe"))),
        boton_control("square", "Cancelar", _cmd(eid, "cancelar")),
        class_name="nx-control-acciones",
    )


def _lavadora(e, eid) -> rx.Component:
    s = e["estado"].to(dict)
    return panel(
        panel_cabecera("washing-machine", e["name"], e["texto"], e["en_marcha"]),
        rx.el.div(
            anillo(e["progreso"], e["restante"], e["fin"]),
            rx.el.div(
                segmentado((("algodón", "Algodón"), ("sintéticos", "Sintéticos"),
                            ("rápido", "Rápido"), ("delicado", "Delicado"),
                            ("eco", "Eco"), ("centrifugado", "Centrifugado")),
                           s["programa"], lambda v: _cmd(eid, "elegir_programa", v), "Programa"),
                segmentado((("frío", "Frío"), ("30", "30°"), ("40", "40°"),
                            ("60", "60°"), ("90", "90°")), s["temp"],
                           lambda v: _cmd(eid, "temp", v), "Temperatura"),
                segmentado((("800", "800"), ("1000", "1000"), ("1200", "1200"),
                            ("1400", "1400")), s["rpm"].to(str),
                           lambda v: _cmd(eid, "rpm", v), "Centrifugado"),
                class_name="nx-control-ajustes",
            ),
            class_name="nx-control-principal",
        ),
        _acciones_ciclo(eid, e["fase"]),
    )


def _nevera(e, eid) -> rx.Component:
    s = e["estado"].to(dict)
    return panel(
        panel_cabecera("refrigerator", e["name"], e["texto"], e["aviso_puerta"]),
        rx.el.div(
            stepper("Nevera", e["temperatura_nevera"], " °C",
                    _cmd(eid, "consigna_nevera", (s["consigna_nevera"].to(int) - 1).to(str)),
                    _cmd(eid, "consigna_nevera", (s["consigna_nevera"].to(int) + 1).to(str))),
            stepper("Congelador", e["temperatura_congelador"], " °C",
                    _cmd(eid, "consigna_congelador", (s["consigna_congelador"].to(int) - 1).to(str)),
                    _cmd(eid, "consigna_congelador", (s["consigna_congelador"].to(int) + 1).to(str)),),
            class_name="nx-control-doble",
        ),
        rx.el.div(
            boton_control("snowflake", "Superfrío", _cmd(eid, "super_frío", (~s["super_frío"].to(bool)).to(str)), "info", s["super_frío"]),
            boton_control("snowflake", "Supercongelación", _cmd(eid, "super_congelación", (~s["super_congelación"].to(bool)).to(str)), "info", s["super_congelación"]),
            boton_control("plane", "Vacaciones", _cmd(eid, "vacaciones", (~s["vacaciones"].to(bool)).to(str)), "warn", s["vacaciones"]),
            boton_control("door-open", "Puerta", _cmd(eid, "puerta", (~s["puerta_abierta"].to(bool)).to(str)), "guard", s["puerta_abierta"]),
            class_name="nx-control-acciones nx-control-wrap",
        ),
    )


def _zona(eid, z, numero: int) -> rx.Component:
    nivel = z["nivel"].to(int)
    return rx.el.div(
        rx.el.span(rx.cond(z["residual"].to(bool), "H", nivel), class_name="nx-placa-nivel"),
        rx.el.div(
            rx.el.button(rx.icon("minus", size=18), on_click=_cmd(eid, "bajar", str(numero)), type="button", aria_label=f"Bajar zona {numero}"),
            rx.el.button(rx.icon("plus", size=18), on_click=_cmd(eid, "subir", str(numero)), type="button", aria_label=f"Subir zona {numero}"),
            class_name="nx-placa-mini",
        ),
        class_name="nx-placa-zona",
        custom_attrs={"data-nivel": nivel, "data-activa": nivel > 0},
    )


def _placa(e, eid) -> rx.Component:
    zonas = e["zonas"].to(list[dict])
    return panel(
        panel_cabecera("flame", e["name"], e["texto"], e["en_marcha"]),
        rx.el.div(*[_zona(eid, zonas[i], i + 1) for i in range(4)], class_name="nx-placa"),
        rx.el.div(
            boton_control("lock-keyhole", "Bloqueo", _cmd(eid, "bloqueo", (~e["estado"].to(dict)["bloqueo"].to(bool)).to(str)), "warn", e["estado"].to(dict)["bloqueo"]),
            boton_control("power-off", "Apagar todo", _cmd(eid, "apagar_todo"), "guard"),
            class_name="nx-control-acciones",
        ),
    )


def _horno(e, eid) -> rx.Component:
    s = e["estado"].to(dict)
    return panel(
        panel_cabecera("microwave", e["name"], e["texto"], e["en_marcha"]),
        rx.cond(e["fin"].to(int) > 0, anillo(0, e["restante"], e["fin"])),
        segmentado((("convencional", "Convencional"), ("aire", "Aire"),
                    ("grill", "Grill"), ("grill+aire", "Grill + aire"),
                    ("solo abajo", "Solo abajo"), ("descongelar", "Descongelar")),
                   s["modo"], lambda v: _cmd(eid, "modo", v), "Modo"),
        stepper("Temperatura", s["temp"], " °C",
                _cmd(eid, "temp", (s["temp"].to(int) - 5).to(str)),
                _cmd(eid, "temp", (s["temp"].to(int) + 5).to(str))),
        segmentado((("0", "Sin tiempo"), ("15", "15 min"), ("30", "30 min"),
                    ("60", "60 min"), ("90", "90 min")), "",
                   lambda v: _cmd(eid, "temporizador", v), "Temporizador"),
        rx.el.div(
            boton_control("power", rx.cond(s["encendido"], "Apagar", "Encender"),
                          _cmd(eid, "encendido", (~s["encendido"].to(bool)).to(str)), "safe", s["encendido"]),
            boton_control("lightbulb", "Luz", _cmd(eid, "luz", (~s["luz"].to(bool)).to(str)), "lamp", s["luz"]),
            class_name="nx-control-acciones"),
    )


def _extractor(e, eid) -> rx.Component:
    s = e["estado"].to(dict)
    return panel(
        panel_cabecera("fan", e["name"], e["texto"], e["en_marcha"]),
        rx.cond(e["fin"].to(int) > 0, anillo(0, e["restante"], e["fin"])),
        segmentado(tuple((str(i), "Intensivo" if i == 4 else str(i)) for i in range(5)),
                   e["velocidad"].to(str), lambda v: _cmd(eid, "velocidad", v), "Velocidad"),
        segmentado((("0", "Sin tiempo"), ("5", "5 min"), ("15", "15 min"),
                    ("30", "30 min")), "", lambda v: _cmd(eid, "temporizador", v), "Apagado"),
        boton_control("lightbulb", "Luz", _cmd(eid, "luz", (~s["luz"].to(bool)).to(str)), "lamp", s["luz"]),
    )


def _freidora(e, eid) -> rx.Component:
    s = e["estado"].to(dict)
    return panel(
        panel_cabecera("cooking-pot", e["name"], rx.cond(e["agitar"], "Agita la cesta", e["texto"]), e["en_marcha"]),
        rx.el.div(
            anillo(e["progreso"], e["restante"], e["fin"]),
            rx.el.div(
                segmentado((("patatas", "Patatas"), ("pollo", "Pollo"),
                            ("pescado", "Pescado"), ("verduras", "Verduras"),
                            ("recalentar", "Recalentar")), s["programa"],
                           lambda v: _cmd(eid, "programa", v), "Programa"),
                stepper("Temperatura", s["temp"], " °C",
                        _cmd(eid, "temp", (s["temp"].to(int) - 5).to(str)),
                        _cmd(eid, "temp", (s["temp"].to(int) + 5).to(str))),
                stepper("Tiempo", s["minutos"], " min",
                        _cmd(eid, "tiempo", (s["minutos"].to(int) - 1).to(str)),
                        _cmd(eid, "tiempo", (s["minutos"].to(int) + 1).to(str))),
                class_name="nx-control-ajustes"),
            class_name="nx-control-principal"),
        _acciones_ciclo(eid, e["fase"]),
    )


def _aire(e, eid) -> rx.Component:
    """Como el mando de pared de un split: termostato grande en el centro."""
    s = e["estado"].to(dict)
    consigna = s["consigna"].to(float)
    encendido = s["encendido"].to(bool)
    return panel(
        panel_cabecera("air-vent", e["name"], e["texto"], e["en_marcha"]),
        rx.el.div(
            rx.el.button(rx.icon("minus", size=26), type="button", class_name="nx-control-step",
                         on_click=_cmd(eid, "consigna", (consigna - 0.5).to(str)),
                         aria_label="Bajar temperatura"),
            rx.el.div(
                rx.el.span(e["consigna_texto"].to(str), rx.el.small("°C"),
                           class_name="nx-aire-consigna"),
                rx.el.span("Ambiente " + e["temperatura_ambiente"].to(str) + " °C",
                           class_name="nx-aire-ambiente"),
                class_name="nx-aire-dial",
            ),
            rx.el.button(rx.icon("plus", size=26), type="button", class_name="nx-control-step",
                         on_click=_cmd(eid, "consigna", (consigna + 0.5).to(str)),
                         aria_label="Subir temperatura"),
            class_name="nx-aire-termostato",
        ),
        segmentado((("frío", "Frío"), ("calor", "Calor"), ("seco", "Seco"),
                    ("ventilación", "Ventilar"), ("auto", "Auto")),
                   s["modo"], lambda v: _cmd(eid, "modo", v), "Modo"),
        rx.el.div(
            segmentado((("auto", "Auto"), ("1", "1"), ("2", "2"), ("3", "3"), ("turbo", "Turbo")),
                       s["ventilador"], lambda v: _cmd(eid, "ventilador", v), "Ventilador"),
            segmentado((("fijo", "Fijas"), ("oscilar", "Oscilar")), s["lamas"],
                       lambda v: _cmd(eid, "lamas", v), "Lamas"),
            class_name="nx-control-doble",
        ),
        segmentado((("0", "Sin"), ("30", "30 min"), ("60", "1 h"), ("120", "2 h"),
                    ("240", "4 h"), ("480", "8 h")), "",
                   lambda v: _cmd(eid, "temporizador", v), "Apagado automático"),
        rx.cond(e["fin"].to(int) > 0,
                rx.el.p("Se apaga en ", rx.el.span(e["restante"], class_name="nx-cuenta",
                                                    custom_attrs={"data-fin": e["fin"]}),
                        class_name="nx-control-nota")),
        rx.el.div(
            boton_control("power", rx.cond(encendido, "Apagar", "Encender"),
                          _cmd(eid, "encendido", (~encendido).to(str)), "safe", encendido),
            boton_control("leaf", "Eco", _cmd(eid, "eco", (~s["eco"].to(bool)).to(str)), "safe", s["eco"]),
            boton_control("moon", "Noche", _cmd(eid, "noche", (~s["noche"].to(bool)).to(str)), "info", s["noche"]),
            class_name="nx-control-acciones",
        ),
        clase="nx-aire",
        modo=rx.cond(encendido, s["modo"].to(str), "apagado"),
    )


def electro_panel(e: rx.Var) -> rx.Component:
    eid = e["id"].to(str)
    return rx.match(
        e["tipo"].to(str),
        ("lavadora", _lavadora(e, eid)), ("nevera", _nevera(e, eid)),
        ("placa", _placa(e, eid)), ("horno", _horno(e, eid)),
        ("extractor", _extractor(e, eid)), ("freidora", _freidora(e, eid)),
        ("aire", _aire(e, eid)),
        rx.el.p("Tipo de electrodoméstico desconocido."),
    )
