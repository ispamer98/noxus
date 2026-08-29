"""
Catálogo de avisos "de sistema": los que dispara el propio panel sin que nadie
escriba el texto a mano (movimiento, alarma, dispositivo desconocido). Se
declaran aquí, en un solo sitio, para que el filtro por dispositivo
(auth/store.categorias_desactivadas) y la pantalla de Ajustes hablen del mismo
vocabulario en vez de cada uno inventarse el suyo.

Lo que NO entra aquí: una alerta escrita a mano (widget "Enviar alerta"), el
botón de pánico, o el aviso de una regla de automatización. Esos ya eligen su
destino en el momento de mandarlos —a mano o en la propia regla—, así que
filtrarlos otra vez por categoría sería una segunda decisión encima de la
primera, y silenciosa además: nadie esperaría que un aviso que acaba de elegir
a quién mandar se recortara solo por una preferencia de hace meses.
"""

MOVIMIENTO = "movimiento"
ALARMA = "alarma"
DESCONOCIDO = "desconocido"

CATEGORIAS = {
    MOVIMIENTO: "Detección de movimiento",
    ALARMA: "Alarma (un sensor se abre con la casa armada)",
    DESCONOCIDO: "Dispositivo desconocido pidiendo entrar",
}
