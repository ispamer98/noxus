#!/usr/bin/env bash
#
# Prueba el circuito entero SIN tocar la lamparita: se le manda a n8n un evento
# igual que el que emitiria Noxus al encenderla.
#
# Recorre: webhook (token) → filtro → registro → vuelta a Noxus → aviso al movil.
# El aviso que llega al telefono es REAL, que es justo lo que se quiere ver.
#
#   bash integrations/n8n/probar.sh "iPhone Ruben"
#   bash integrations/n8n/probar.sh "iPhone Ruben" apagar
#   bash integrations/n8n/probar.sh "iPhone Ruben" encender --test
#
# Con --test se llama a /webhook-test/ en vez de a /webhook/: es la URL que
# escucha n8n cuando has pulsado «Execute workflow» en el lienzo, y sirve
# para VER pasar los datos nodo a nodo sin tener que activar el workflow.
# Solo vale para UNA ejecucion: hay que volver a pulsar el boton cada vez.
#
set -euo pipefail

DESTINO="${1:-}"
QUE="${2:-encender}"
MODO="${3:-}"

if [[ -z "$DESTINO" ]]; then
  echo "Uso: bash integrations/n8n/probar.sh \"<nombre del dispositivo>\" [encender|apagar]" >&2
  echo >&2
  echo "El nombre tiene que ser el de un dispositivo con avisos activados." >&2
  echo "Salen en Ajustes → Dispositivos, y son los que aparecen en Registros." >&2
  exit 1
fi

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TOKEN="$(grep -E '^N8N_TOKEN=' "$RAIZ/.env" | head -1 | cut -d= -f2- | tr -d '"'"'"' \r')"
URL="$(grep -E '^N8N_WEBHOOK_URL=' "$RAIZ/.env" | head -1 | cut -d= -f2- | tr -d '"'"'"' \r')"
[[ -n "$TOKEN" && -n "$URL" ]] || { echo "❌ Falta N8N_TOKEN o N8N_WEBHOOK_URL en $RAIZ/.env" >&2; exit 1; }

if [[ "$MODO" == "--test" ]]; then
  URL="${URL/\/webhook\//\/webhook-test\/}"
  echo "· modo prueba: pulsa «Execute workflow» en n8n ANTES de seguir."
  read -r -p "  Cuando el lienzo diga que esta escuchando, pulsa Intro..." _
fi

if [[ "$QUE" == "apagar" ]]; then
  ACCION="LUZ_APAGADA"; LEGIBLE="Luz apagada"
else
  ACCION="LUZ_ENCENDIDA"; LEGIBLE="Luz encendida"
fi

AHORA="$(date '+%Y-%m-%d %H:%M:%S')"
CUERPO=$(cat <<EOF
{
  "origen": "noxus",
  "evento_id": 0,
  "ts": $(date +%s),
  "fecha": "$(date '+%Y-%m-%d')",
  "hora": "$(date '+%H:%M:%S')",
  "timestamp": "$AHORA",
  "categoria": "luces",
  "accion": "$ACCION",
  "accion_legible": "$LEGIBLE",
  "usuario": "$DESTINO",
  "elemento": "Habitación",
  "detalle_extra": "",
  "detalle": "Habitación",
  "entidad": "light_78c43ca9",
  "grupo": ""
}
EOF
)

echo "→ mandando a n8n un «$ACCION» de «Habitación» hecho por «$DESTINO»"
echo "  $URL"
echo
RESP="$(curl -s -w '\n%{http_code}' -X POST "$URL" \
        -H "X-Noxus-Token: $TOKEN" -H 'Content-Type: application/json' \
        -d "$CUERPO")"
CODIGO="$(tail -1 <<<"$RESP")"
echo "respuesta de n8n (HTTP $CODIGO):"
sed '$d' <<<"$RESP"
echo

case "$CODIGO" in
  200) echo "✅ n8n lo ha procesado. Mira el movil, y Executions en https://n8n.noxuscmmd.uk" ;;
  404) if [[ "$MODO" == "--test" ]]; then
         echo "❌ 404: n8n no estaba escuchando."
         echo "   Pulsa «Execute workflow» en el lienzo y vuelve a lanzar esto."
       else
         echo "❌ 404: el workflow «Noxus · Luces» no esta ACTIVO."
         echo "   Abrelo en https://n8n.noxuscmmd.uk y dale al interruptor «Active»."
       fi ;;
  403) echo "❌ 403: el token del webhook no coincide."
       echo "   Vuelve a lanzar: bash integrations/n8n/instalar.sh" ;;
  *)   echo "⚠️  Codigo inesperado. Revisa Executions en n8n." ;;
esac
