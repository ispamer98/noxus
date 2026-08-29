"""Adaptador AWS Lambda para la Smart Home Skill de Noxus.

Se despliega como endpoint de la Skill. Alexa invoca Lambda con una directiva
ya autenticada por AWS; esta función únicamente la firma de nuevo para Noxus y
devuelve la respuesta. No contiene dispositivos, contraseñas ni lógica de la
casa: toda la fuente de verdad sigue en el panel.

Variables Lambda necesarias:
  NOXUS_ALEXA_URL=https://panel.ejemplo.es/api/alexa/directive
  NOXUS_ALEXA_PROXY_SECRET=<secreto aleatorio de al menos 32 bytes>
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from urllib.request import Request, urlopen


URL = os.environ["NOXUS_ALEXA_URL"]
SECRETO = os.environ["NOXUS_ALEXA_PROXY_SECRET"]
TIMEOUT = 7


def lambda_handler(event, _context):
    cuerpo = json.dumps(event, separators=(",", ":")).encode()
    instante = str(int(time.time()))
    firma = hmac.new(SECRETO.encode(), instante.encode() + b"." + cuerpo,
                      hashlib.sha256).hexdigest()
    request = Request(URL, data=cuerpo, method="POST", headers={
        "content-type": "application/json",
        # Cloudflare bloquea el User-Agent genérico de urllib con el error
        # 1010. Una identidad explícita permite el paso; la autenticación real
        # sigue siendo la firma HMAC de debajo, no esta cabecera.
        "user-agent": "Noxus-Alexa-Lambda/1.0",
        "x-noxus-alexa-timestamp": instante,
        "x-noxus-alexa-signature": firma,
    })
    with urlopen(request, timeout=TIMEOUT) as response:  # nosec B310: deployment config
        return json.loads(response.read())
