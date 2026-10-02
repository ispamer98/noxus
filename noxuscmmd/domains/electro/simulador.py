"""Simulador puro de electrodomésticos.

No conoce Reflex, MQTT ni el almacén. Los instantes persistidos son epoch en
segundos; :func:`vista` expone ``fin`` en epoch milisegundos para el contador
del navegador. Cuando haya hardware real, el adaptador vivirá fuera de este
módulo y traducirá las mismas acciones a su transporte (nunca desde aquí).
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any


TIPOS = ("lavadora", "nevera", "placa", "horno", "extractor", "freidora", "aire")
PROGRAMAS_LAVADORA = {
    "algodón": 180, "sintéticos": 90, "rápido": 30,
    "delicado": 60, "eco": 210, "centrifugado": 15,
}
PROGRAMAS_FREIDORA = {
    "patatas": (200, 20), "pollo": (180, 25), "pescado": (160, 12),
    "verduras": (170, 15), "recalentar": (150, 5),
}
MODOS_AIRE = ("frío", "calor", "seco", "ventilación", "auto")
VENTILADOR_AIRE = ("auto", "1", "2", "3", "turbo")


MODOS_HORNO = (
    "convencional", "aire", "grill", "grill+aire", "solo abajo", "descongelar",
)


def _numero(valor: Any, nombre: str) -> float:
    try:
        return float(valor)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{nombre} no es un número") from exc


def _entero(valor: Any, nombre: str, minimo: int, maximo: int) -> int:
    numero = _numero(valor, nombre)
    if not numero.is_integer() or not minimo <= numero <= maximo:
        raise ValueError(f"{nombre} debe estar entre {minimo} y {maximo}")
    return int(numero)


def _booleano(valor: Any) -> bool:
    if isinstance(valor, bool):
        return valor
    texto = str(valor).strip().lower()
    if texto in ("1", "true", "sí", "si", "on"):
        return True
    if texto in ("0", "false", "no", "off"):
        return False
    raise ValueError("valor booleano inválido")


def _estado(item: dict) -> dict:
    tipo = item.get("tipo")
    if tipo not in TIPOS:
        raise ValueError("tipo de electrodoméstico inválido")
    base = deepcopy(item.get("estado") if isinstance(item.get("estado"), dict) else {})
    defaults = {
        "lavadora": {"programa": "algodón", "temp": "40", "rpm": 1200,
                     "fase": "parada", "inicio": 0.0, "fin": 0.0,
                     "pausado_en": 0.0, "restante_pausa": 0},
        "nevera": {"consigna_nevera": 4, "consigna_congelador": -18,
                   "super_frío": False, "super_congelación": False,
                   "vacaciones": False, "puerta_abierta": False,
                   "puerta_desde": 0.0},
        "placa": {"bloqueo": False, "zonas": [
            {"nivel": 0, "boost": False, "fin": 0.0, "residual_hasta": 0.0}
            for _ in range(4)]},
        "horno": {"encendido": False, "modo": "convencional", "temp": 180,
                  "luz": False, "inicio": 0.0, "temp_inicio": 20.0,
                  "fin": 0.0, "terminado": False},
        "extractor": {"velocidad": 0, "luz": False, "fin": 0.0},
        "aire": {"encendido": False, "modo": "frío", "consigna": 24.0,
                 "ventilador": "auto", "lamas": "fijo", "eco": False, "noche": False,
                 "ambiente": 27.0, "desde": 0.0, "fin": 0.0},
        "freidora": {"encendido": False, "programa": "patatas", "temp": 200,
                     "minutos": 20, "fase": "parada", "inicio": 0.0,
                     "fin": 0.0, "pausado_en": 0.0, "restante_pausa": 0},
    }[tipo]
    return {**deepcopy(defaults), **base}


def _restante(fin: float, ahora: float) -> int:
    return max(0, int(round(fin - ahora)))


def _temporizado(estado: dict, ahora: float) -> tuple[int, int]:
    fin = float(estado.get("fin") or 0)
    return _restante(fin, ahora), int(fin * 1000) if fin else 0


def comando(item: dict, accion: str, valor: Any, ahora: float) -> dict:
    """Valida una orden y devuelve el estado persistible resultante."""
    tipo = item.get("tipo")
    estado = _estado(item)
    handlers = {
        "lavadora": _comando_lavadora, "nevera": _comando_nevera,
        "placa": _comando_placa, "horno": _comando_horno,
        "extractor": _comando_extractor, "freidora": _comando_freidora,
        "aire": _comando_aire,
    }
    return handlers[tipo](estado, accion, valor, float(ahora))


def _comando_lavadora(e: dict, accion: str, valor: Any, ahora: float) -> dict:
    if accion == "elegir_programa":
        if valor not in PROGRAMAS_LAVADORA:
            raise ValueError("programa de lavadora inválido")
        e["programa"] = valor
    elif accion == "temp":
        texto = str(valor).lower()
        if texto not in ("frío", "frio", "30", "40", "60", "90"):
            raise ValueError("temperatura de lavadora inválida")
        e["temp"] = "frío" if texto in ("frío", "frio") else texto
    elif accion == "rpm":
        rpm = _entero(valor, "rpm", 800, 1400)
        if rpm not in (800, 1000, 1200, 1400):
            raise ValueError("rpm inválidas")
        e["rpm"] = rpm
    elif accion == "iniciar":
        segundos = PROGRAMAS_LAVADORA[e["programa"]] * 60
        e.update(fase="lavado", inicio=ahora, fin=ahora + segundos,
                 pausado_en=0.0, restante_pausa=0)
    elif accion == "pausar":
        if e.get("fase") not in ("lavado", "aclarado", "centrifugado"):
            raise ValueError("la lavadora no está en marcha")
        e["restante_pausa"] = _restante(float(e.get("fin") or 0), ahora)
        e.update(fase="pausada", pausado_en=ahora, fin=0.0)
    elif accion == "reanudar":
        if e.get("fase") != "pausada":
            raise ValueError("la lavadora no está pausada")
        restante = max(1, int(e.get("restante_pausa") or 0))
        e.update(fase="lavado", inicio=ahora, fin=ahora + restante, pausado_en=0.0)
    elif accion == "cancelar":
        e.update(fase="parada", inicio=0.0, fin=0.0, pausado_en=0.0,
                 restante_pausa=0)
    else:
        raise ValueError("acción de lavadora inválida")
    return e


def _comando_nevera(e: dict, accion: str, valor: Any, ahora: float) -> dict:
    if accion == "consigna_nevera":
        e["consigna_nevera"] = _entero(valor, "consigna", 1, 8)
    elif accion == "consigna_congelador":
        e["consigna_congelador"] = _entero(valor, "consigna", -24, -16)
    elif accion in ("super_frío", "super_congelación", "vacaciones"):
        e[accion] = _booleano(valor)
    elif accion == "puerta":
        abierta = _booleano(valor)
        e.update(puerta_abierta=abierta,
                 puerta_desde=ahora if abierta and not e.get("puerta_abierta") else
                 (e.get("puerta_desde", ahora) if abierta else 0.0))
    else:
        raise ValueError("acción de nevera inválida")
    return e


def _zona(valor: Any) -> int:
    return _entero(valor, "zona", 1, 4) - 1


def _comando_placa(e: dict, accion: str, valor: Any, ahora: float) -> dict:
    zonas = deepcopy(e.get("zonas") or [])
    if len(zonas) != 4:
        zonas = _estado({"tipo": "placa"})["zonas"]
    if accion == "bloqueo":
        e["bloqueo"] = _booleano(valor)
    elif accion == "apagar_todo":
        for z in zonas:
            if z.get("nivel", 0) > 0:
                z["residual_hasta"] = ahora + 300
            z.update(nivel=0, boost=False, fin=0.0)
    else:
        if e.get("bloqueo"):
            raise ValueError("la placa está bloqueada")
        partes = str(valor).split(":", 1)
        idx = _zona(partes[0])
        z = zonas[idx]
        if accion == "nivel":
            if len(partes) != 2:
                raise ValueError("falta el nivel")
            nuevo = _entero(partes[1], "nivel", 0, 9)
            if z.get("nivel", 0) > 0 and nuevo == 0:
                z["residual_hasta"] = ahora + 300
            z.update(nivel=nuevo, boost=False if nuevo == 0 else z.get("boost", False))
        elif accion in ("subir", "bajar"):
            delta = 1 if accion == "subir" else -1
            nuevo = max(0, min(9, int(z.get("nivel", 0)) + delta))
            if z.get("nivel", 0) > 0 and nuevo == 0:
                z["residual_hasta"] = ahora + 300
            z.update(nivel=nuevo, boost=False if nuevo == 0 else z.get("boost", False))
        elif accion == "boost":
            activo = _booleano(partes[1]) if len(partes) == 2 else True
            z.update(boost=activo, nivel=9 if activo else z.get("nivel", 0))
        elif accion == "temporizador":
            if len(partes) != 2:
                raise ValueError("falta el temporizador")
            minutos = _entero(partes[1], "temporizador", 0, 180)
            z["fin"] = ahora + minutos * 60 if minutos else 0.0
        else:
            raise ValueError("acción de placa inválida")
    e["zonas"] = zonas
    return e


def _comando_horno(e: dict, accion: str, valor: Any, ahora: float) -> dict:
    if accion == "encendido":
        activo = _booleano(valor)
        e.update(encendido=activo, inicio=ahora if activo else 0.0,
                 temp_inicio=20.0 if activo else e.get("temp_inicio", 20.0),
                 fin=e.get("fin", 0.0) if activo else 0.0, terminado=False)
    elif accion == "modo":
        if valor not in MODOS_HORNO:
            raise ValueError("modo de horno inválido")
        e["modo"] = valor
    elif accion == "temp":
        temp = _entero(valor, "temperatura", 50, 250)
        if temp % 5:
            raise ValueError("la temperatura debe avanzar de 5 en 5")
        e.update(temp=temp, inicio=ahora, temp_inicio=20.0, terminado=False)
    elif accion == "temporizador":
        minutos = _entero(valor, "temporizador", 0, 240)
        e.update(fin=ahora + minutos * 60 if minutos else 0.0, terminado=False)
    elif accion == "luz":
        e["luz"] = _booleano(valor)
    else:
        raise ValueError("acción de horno inválida")
    return e


def _comando_extractor(e: dict, accion: str, valor: Any, ahora: float) -> dict:
    if accion == "velocidad":
        e["velocidad"] = _entero(valor, "velocidad", 0, 4)
        if not e["velocidad"]:
            e["fin"] = 0.0
    elif accion == "luz":
        e["luz"] = _booleano(valor)
    elif accion == "temporizador":
        minutos = _entero(valor, "temporizador", 0, 60)
        e["fin"] = ahora + minutos * 60 if minutos else 0.0
    else:
        raise ValueError("acción de extractor inválida")
    return e


def _comando_freidora(e: dict, accion: str, valor: Any, ahora: float) -> dict:
    if accion == "encendido":
        activo = _booleano(valor)
        e.update(encendido=activo, fase="lista" if activo else "parada",
                 fin=0.0, inicio=0.0, terminado=False)
    elif accion == "programa":
        if valor not in PROGRAMAS_FREIDORA:
            raise ValueError("programa de freidora inválido")
        temp, minutos = PROGRAMAS_FREIDORA[valor]
        e.update(programa=valor, temp=temp, minutos=minutos)
    elif accion == "temp":
        e["temp"] = _entero(valor, "temperatura", 80, 200)
    elif accion == "tiempo":
        e["minutos"] = _entero(valor, "tiempo", 1, 60)
    elif accion == "iniciar":
        segundos = int(e["minutos"]) * 60
        e.update(encendido=True, fase="cocinando", inicio=ahora,
                 fin=ahora + segundos, pausado_en=0.0, restante_pausa=0)
    elif accion == "pausar":
        if e.get("fase") != "cocinando":
            raise ValueError("la freidora no está cocinando")
        e.update(fase="pausada", pausado_en=ahora,
                 restante_pausa=_restante(float(e.get("fin") or 0), ahora), fin=0.0)
    elif accion == "reanudar":
        if e.get("fase") != "pausada":
            raise ValueError("la freidora no está pausada")
        restante = max(1, int(e.get("restante_pausa") or 0))
        e.update(fase="cocinando", inicio=ahora, fin=ahora + restante, pausado_en=0.0)
    elif accion == "cancelar":
        e.update(fase="lista" if e.get("encendido") else "parada", inicio=0.0,
                 fin=0.0, pausado_en=0.0, restante_pausa=0)
    else:
        raise ValueError("acción de freidora inválida")
    return e


def vista(item: dict, ahora: float) -> dict:
    """Devuelve una vista ya derivada sin modificar ``item``."""
    tipo = item.get("tipo")
    e = _estado(item)
    ahora = float(ahora)
    derivadores = {
        "lavadora": _vista_lavadora, "nevera": _vista_nevera,
        "placa": _vista_placa, "horno": _vista_horno,
        "extractor": _vista_extractor, "freidora": _vista_freidora,
        "aire": _vista_aire,
    }
    derivado = derivadores[tipo](e, ahora)
    return {**deepcopy(item), "estado": e, **derivado}


def _vista_lavadora(e: dict, ahora: float) -> dict:
    fase = e.get("fase", "parada")
    restante, fin = _temporizado(e, ahora)
    if fase in ("lavado", "aclarado", "centrifugado"):
        if restante <= 0:
            fase, fin = "terminado", 0
        else:
            total = max(1, PROGRAMAS_LAVADORA[e["programa"]] * 60)
            avance = 1 - restante / total
            fase = "lavado" if avance < .65 else ("aclarado" if avance < .88 else "centrifugado")
    if fase == "pausada":
        restante, fin = int(e.get("restante_pausa") or 0), 0
    marcha = fase in ("lavado", "aclarado", "centrifugado")
    return {"fase": fase, "texto": fase.capitalize(), "restante": restante,
            "fin": fin, "en_marcha": marcha, "puerta_bloqueada": marcha,
            "progreso": _progreso(e, ahora, PROGRAMAS_LAVADORA[e["programa"]] * 60)}


def _vista_nevera(e: dict, ahora: float) -> dict:
    abierta = bool(e.get("puerta_abierta"))
    abierta_s = max(0, int(ahora - float(e.get("puerta_desde") or ahora))) if abierta else 0
    subida = min(6.0, abierta_s / 120.0) if abierta else 0.0
    return {"fase": "puerta abierta" if abierta else "enfriando",
            "texto": "Puerta abierta" if abierta else "Temperatura estable",
            "restante": 0, "fin": 0, "en_marcha": True,
            "aviso_puerta": abierta_s > 60, "puerta_abierta_s": abierta_s,
            "temperatura_nevera": round(float(e["consigna_nevera"]) + subida, 1),
            "temperatura_congelador": round(float(e["consigna_congelador"]) + subida / 2, 1),
            "progreso": 0}


def _vista_placa(e: dict, ahora: float) -> dict:
    zonas = []
    finales = []
    for original in e.get("zonas", []):
        z = deepcopy(original)
        fin_z = float(z.get("fin") or 0)
        if fin_z and ahora >= fin_z and z.get("nivel", 0) > 0:
            z.update(nivel=0, boost=False, fin=0.0, residual_hasta=fin_z + 300)
        restante = _restante(float(z.get("fin") or 0), ahora)
        z.update(restante=restante, fin_ms=int(float(z.get("fin") or 0) * 1000),
                 residual=ahora < float(z.get("residual_hasta") or 0))
        if z["fin_ms"]:
            finales.append(z["fin_ms"])
        zonas.append(z)
    activa = any(z.get("nivel", 0) > 0 for z in zonas)
    return {"fase": "cocinando" if activa else "apagada", "texto": "En marcha" if activa else "Apagada",
            "restante": min((z["restante"] for z in zonas if z["restante"]), default=0),
            "fin": min(finales, default=0), "en_marcha": activa, "zonas": zonas,
            "progreso": 0}


def _vista_horno(e: dict, ahora: float) -> dict:
    restante, fin = _temporizado(e, ahora)
    encendido = bool(e.get("encendido"))
    terminado = bool(e.get("terminado")) or bool(fin and restante <= 0)
    if terminado:
        encendido, fin = False, 0
    actual = float(e.get("temp_inicio") or 20)
    if encendido:
        actual = min(float(e["temp"]), actual + max(0, ahora - float(e.get("inicio") or ahora)) / 6)
    precalentando = encendido and actual < float(e["temp"])
    texto = "Terminado" if terminado else ("Precalentando" if precalentando else ("Cocinando" if encendido else "Apagado"))
    return {"fase": texto.lower(), "texto": texto, "restante": restante if encendido else 0,
            "fin": fin if encendido else 0, "en_marcha": encendido,
            "precalentando": precalentando, "temperatura_actual": round(actual),
            "progreso": 0}


def _vista_extractor(e: dict, ahora: float) -> dict:
    restante, fin = _temporizado(e, ahora)
    velocidad = int(e.get("velocidad") or 0)
    if fin and restante <= 0:
        velocidad, fin = 0, 0
    texto = "Intensivo" if velocidad == 4 else (f"Velocidad {velocidad}" if velocidad else "Apagado")
    return {"fase": texto.lower(), "texto": texto, "restante": restante if velocidad else 0,
            "fin": fin if velocidad else 0, "en_marcha": velocidad > 0, "velocidad": velocidad,
            "progreso": 0}


def _vista_freidora(e: dict, ahora: float) -> dict:
    fase = e.get("fase", "parada")
    restante, fin = _temporizado(e, ahora)
    total = max(1, int(e.get("minutos") or 1) * 60)
    if fase == "cocinando" and restante <= 0:
        fase, fin = "terminado", 0
    if fase == "pausada":
        restante, fin = int(e.get("restante_pausa") or 0), 0
    avance = max(0, min(1, 1 - restante / total)) if fase in ("cocinando", "pausada") else 0
    return {"fase": fase, "texto": fase.capitalize(), "restante": restante, "fin": fin,
            "en_marcha": fase == "cocinando", "agitar": fase == "cocinando" and .5 <= avance < .6,
            "progreso": round(avance * 100)}


def _ambiente_aire(e: dict, ahora: float) -> float:
    """La habitación se acerca a la consigna ~1 °C cada 3 min con el aire en marcha
    (más rápido en turbo, más lento en eco o noche)."""
    base = float(e.get("ambiente") or 27)
    if not e.get("encendido") or e.get("modo") in ("ventilación", "seco"):
        return base
    ritmo = 1 / 180 * (1.6 if e.get("ventilador") == "turbo" else 1) * (0.6 if (e.get("eco") or e.get("noche")) else 1)
    paso = max(0.0, ahora - float(e.get("desde") or ahora)) * ritmo
    objetivo = float(e["consigna"])
    return objetivo if abs(objetivo - base) <= paso else base + paso * (1 if objetivo > base else -1)


def _comando_aire(e: dict, accion: str, valor: Any, ahora: float) -> dict:
    # Cada cambio fija la temperatura ambiente alcanzada hasta ahora y empieza
    # un tramo nuevo: así la simulación no salta al cambiar la consigna.
    e["ambiente"] = round(_ambiente_aire(e, ahora), 2)
    e["desde"] = ahora
    if accion == "encendido":
        e["encendido"] = _booleano(valor)
        if not e["encendido"]:
            e["fin"] = 0.0
    elif accion == "modo":
        if valor not in MODOS_AIRE:
            raise ValueError("modo de aire inválido")
        e["modo"] = valor
    elif accion == "consigna":
        consigna = _numero(valor, "temperatura")
        if not 16 <= consigna <= 30 or (consigna * 2) % 1:
            raise ValueError("temperatura entre 16 y 30 °C en pasos de 0,5")
        e["consigna"] = consigna
    elif accion == "ventilador":
        if valor not in VENTILADOR_AIRE:
            raise ValueError("velocidad de ventilador inválida")
        e["ventilador"] = valor
    elif accion == "lamas":
        if valor not in ("fijo", "oscilar"):
            raise ValueError("lamas inválidas")
        e["lamas"] = valor
    elif accion in ("eco", "noche"):
        e[accion] = _booleano(valor)
    elif accion == "temporizador":
        minutos = _entero(valor, "temporizador", 0, 480)
        e["fin"] = ahora + minutos * 60 if minutos else 0.0
    else:
        raise ValueError("acción de aire inválida")
    return e


def _vista_aire(e: dict, ahora: float) -> dict:
    restante, fin = _temporizado(e, ahora)
    encendido = bool(e.get("encendido")) and not (fin and restante <= 0)
    ambiente = round(_ambiente_aire({**e, "encendido": encendido}, ahora), 1)
    texto = (e["modo"].capitalize() + f" · {e['consigna']:g} °C") if encendido else "Apagado"
    return {"fase": "encendido" if encendido else "apagado", "texto": texto,
            "restante": restante if encendido else 0, "fin": fin if encendido else 0,
            "en_marcha": encendido, "temperatura_ambiente": ambiente,
            "consigna_texto": f"{e['consigna']:g}", "progreso": 0}


def _progreso(e: dict, ahora: float, total: int) -> int:
    fin = float(e.get("fin") or 0)
    if not fin:
        return 0
    return round(max(0, min(1, 1 - (fin - ahora) / max(1, total))) * 100)
