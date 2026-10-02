#!/usr/bin/env bash
# Alta y baja de un nodo físico (Raspberry, ESP32...) en el broker de casa.
#
#   scripts/mqtt_nodo.sh alta <nodo>      crea usuario + ACL y recarga el broker
#   scripts/mqtt_nodo.sh quitar <nodo>    borra usuario y ACL
#   scripts/mqtt_nodo.sh listar
#
# <nodo> es el slug del nombre del nodo en el panel (store.slugify): «ESP32
# Salón» → esp32_salon. El usuario del broker TIENE que llamarse igual que el
# slug: la ACL solo le deja tocar casa/<nodo>/#, que es de donde el panel saca
# los topics. Recarga con SIGHUP: no corta a nadie. Ver
# docs/runbooks/anadir-equipo-sin-romper-seguridad.md
set -euo pipefail
PASSWD=/etc/mosquitto/passwd
ACL=/etc/mosquitto/acl
CLAVES="$HOME/.agents/keys"

nodo="${2:-}"
validar() { [[ "$nodo" =~ ^[a-z0-9_]{2,32}$ ]] || { echo "nodo inválido: usa el slug (a-z, 0-9, _)"; exit 2; }; }

case "${1:-}" in
  alta)
    validar
    clave=$(openssl rand -base64 24 | tr -d '/+=' | cut -c1-28)
    sudo mosquitto_passwd -b "$PASSWD" "$nodo" "$clave"
    if ! sudo grep -qx "user $nodo" "$ACL"; then
      printf '\nuser %s\ntopic readwrite casa/%s/#\n' "$nodo" "$nodo" | sudo tee -a "$ACL" >/dev/null
    fi
    # El broker corre como «mosquitto» y debe poder leerlos (el aviso de
    # mosquitto_passwd pidiendo root es solo de la herramienta, no del broker).
    sudo chown mosquitto:mosquitto "$PASSWD" "$ACL"; sudo chmod 640 "$PASSWD" "$ACL"
    sudo systemctl reload mosquitto
    umask 077; mkdir -p "$CLAVES"; printf '%s\n' "$clave" > "$CLAVES/mqtt_$nodo"
    echo "Nodo '$nodo' dado de alta (si ya existía, su contraseña ha cambiado)."
    echo "  broker : 100.98.98.1:1883   usuario: $nodo   topics: casa/$nodo/#"
    echo "  clave  : $CLAVES/mqtt_$nodo   (cat ese fichero; no la pegues en el repo)"
    ;;
  quitar)
    validar
    sudo mosquitto_passwd -D "$PASSWD" "$nodo" || true
    sudo python3 - "$nodo" <<'PY'
import re, sys
nodo, ruta = sys.argv[1], "/etc/mosquitto/acl"
s = open(ruta).read()
s = re.sub(rf"\n?user {re.escape(nodo)}\n(?:topic [^\n]*\n)*", "\n", s)
open(ruta, "w").write(s.rstrip("\n") + "\n")
PY
    # El broker corre como «mosquitto» y debe poder leerlos (el aviso de
    # mosquitto_passwd pidiendo root es solo de la herramienta, no del broker).
    sudo chown mosquitto:mosquitto "$PASSWD" "$ACL"; sudo chmod 640 "$PASSWD" "$ACL"
    sudo systemctl reload mosquitto
    rm -f "$CLAVES/mqtt_$nodo"
    echo "Nodo '$nodo' dado de baja."
    ;;
  listar)
    echo "Usuarios del broker:"; sudo cut -d: -f1 "$PASSWD" | sed 's/^/  /'
    echo "ACL:"; sudo grep -vE '^\s*(#|$)' "$ACL" | sed 's/^/  /'
    ;;
  *) sed -n 2,11p "$0"; exit 1 ;;
esac
