#!/usr/bin/env bash
#
# Mete el workflow "Noxus · Luces" y su credencial dentro del n8n de esta
# maquina, que corre como servicio Docker Swarm (n8n_n8n).
#
# Se hace por la CLI de n8n dentro del contenedor y no por su API publica
# porque la API pide una API key que hay que crear a mano en Ajustes: por aqui
# no hace falta nada previo.
#
# Es idempotente: el workflow y la credencial llevan un id fijo, asi que
# volver a lanzarlo ACTUALIZA los que ya haya en vez de duplicarlos.
#
#   bash integrations/n8n/instalar.sh                    credencial + workflow
#   bash integrations/n8n/instalar.sh --solo-credencial  solo la credencial
#
# El segundo modo es para importar el workflow A MANO desde la web de n8n
# (Workflows → ⋯ → Import from File, o pegando el JSON en el lienzo). La
# credencial se crea con un id FIJO, y como el JSON la referencia por ese
# id, al pegarlo aparece ya enlazada en los dos nodos que la usan: no hay
# que elegir nada en ningun desplegable.
#
set -euo pipefail

SOLO_CREDENCIAL=0
[[ "${1:-}" == "--solo-credencial" ]] && SOLO_CREDENCIAL=1

AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RAIZ="$(cd "$AQUI/../.." && pwd)"
WORKFLOW="$AQUI/noxus-luces.json"
CRED_ID="noxusTokenCred001"

# ── El token, del .env de Noxus ────────────────────────────────────────────
if [[ ! -f "$RAIZ/.env" ]]; then
  echo "❌ No encuentro $RAIZ/.env" >&2; exit 1
fi
TOKEN="$(grep -E '^N8N_TOKEN=' "$RAIZ/.env" | head -1 | cut -d= -f2- | tr -d '"'"'"' \r')"
if [[ -z "$TOKEN" ]]; then
  echo "❌ Falta N8N_TOKEN en $RAIZ/.env" >&2; exit 1
fi

# ── El contenedor de n8n ───────────────────────────────────────────────────
# Se busca cada vez: swarm le cambia el id en cada redespliegue.
CID="$(sudo docker ps --filter 'name=n8n_n8n.' --format '{{.ID}} {{.Names}}' \
        | grep -Ev 'runner|\-db' | head -1 | awk '{print $1}')"
if [[ -z "$CID" ]]; then
  echo "❌ No encuentro el contenedor de n8n (docker ps | grep n8n)" >&2; exit 1
fi
echo "→ contenedor n8n: $CID"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"; sudo docker exec "$CID" rm -f /tmp/noxus-cred.json /tmp/noxus-wf.json 2>/dev/null || true' EXIT

# ── La credencial (Header Auth con el token compartido) ────────────────────
# Se escribe en claro y n8n la cifra al importarla con su clave interna.
cat > "$TMP/noxus-cred.json" <<EOF
[
  {
    "id": "$CRED_ID",
    "name": "Noxus token",
    "type": "httpHeaderAuth",
    "data": { "name": "X-Noxus-Token", "value": "$TOKEN" }
  }
]
EOF
chmod 644 "$TMP/noxus-cred.json"

sudo docker cp "$TMP/noxus-cred.json" "$CID:/tmp/noxus-cred.json" >/dev/null
sudo docker cp "$WORKFLOW"            "$CID:/tmp/noxus-wf.json"   >/dev/null
sudo docker exec -u root "$CID" chown node:node /tmp/noxus-cred.json /tmp/noxus-wf.json

echo "→ importando la credencial «Noxus token»..."
sudo docker exec "$CID" n8n import:credentials --input=/tmp/noxus-cred.json

if [[ "$SOLO_CREDENCIAL" == "1" ]]; then
  echo
  echo "✅ Credencial «Noxus token» lista. El workflow lo importas tu:"
  echo "   1. Abre https://n8n.noxuscmmd.uk"
  echo "   2. Workflows → ⋯ → Import from File → integrations/n8n/noxus-luces.json"
  echo "      (o abre el fichero, copia el JSON y pegalo en un lienzo vacio)"
  echo "   3. La credencial ya sale enlazada en los dos nodos que la usan."
  echo "   4. Guarda (Ctrl+S) y dale al interruptor «Active»."
  exit 0
fi

echo "→ importando el workflow «Noxus · Luces»..."
sudo docker exec "$CID" n8n import:workflow --input=/tmp/noxus-wf.json

echo
echo "✅ Listo. Ahora, en https://n8n.noxuscmmd.uk :"
echo "   1. Recarga la pagina (F5) — los workflows importados por CLI no salen hasta recargar."
echo "   2. Abre «Noxus · Luces» y dale al interruptor «Active» de arriba a la derecha."
echo "   3. Enciende la lamparita en https://panel.noxuscmmd.uk y mira Executions."
