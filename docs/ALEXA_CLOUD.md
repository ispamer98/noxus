# Alexa Smart Home oficial para Noxus

Esta integración sustituye la dependencia de rutinas por dispositivos Smart
Home reales. Tras la única vinculación inicial, Noxus envía a Alexa altas,
cambios de nombre y bajas automáticamente. Los dos Echo de la misma cuenta
verán los mismos dispositivos: Alexa los asocia a la cuenta, no a un Echo.

## Qué publica Noxus

Solo lo que el propietario crea en **Ajustes → Alexa y voz**. Dar de alta una
luz, equipo, mando o botón en otra pestaña lo hace seleccionable, pero no lo
publica por sorpresa. Cada ficha Alexa tiene un identificador estable y uno de
estos comportamientos:

- **Dispositivo con encender y apagar** (`PowerController`): nombre, categoría
  y dos acciones independientes. Sirve para un PC (WOL/apagado), un relé o un
  aparato con teclas separadas. Si la TV usa la misma tecla para alternar, se
  puede elegir esa misma acción en ambos campos; Noxus no fingirá conocer su
  estado físico.
- **Acción de un solo disparo** (`SceneController`): una acción concreta del
  panel, como Netflix, Home, subir volumen, velocidad del ventilador, un botón
  de equipo o una automatización completa. Las teclas de mando pueden repetirse
  hasta 50 veces, con una pausa configurable entre pulsos. La ficha permite
  elegir si se invoca con **enciende/activa** o con **apaga/desactiva**. Así,
  una secuencia de apagado no tiene que fingir que es un interruptor ni llamarse
  `Apaga habitación`: se llama `Habitación` y se publica para `Deactivate`.

Las puertas, el armado y las acciones que indirectamente los utilicen se
excluyen del selector porque Amazon no permite controlarlas como escenas.

Al guardar o editar se envía `AddOrUpdateReport`; al borrar se envía
`DeleteReport`. Los antiguos endpoints que Noxus publicaba automáticamente se
retiran en la primera sincronización del servicio.

Alexa Smart Home admite hasta 300 elementos por cuenta. Noxus aplica ese mismo
tope y divide automáticamente los informes para respetar también el tamaño
máximo del Event Gateway.

## Lo que debes hacer una sola vez

No compartas aquí las claves ni las subas al repositorio. Van únicamente en
`.env` y en las variables de la Lambda.

1. Entra en [Alexa Developer Console](https://developer.amazon.com/alexa/console/ask)
   con la misma cuenta Amazon de tus Echo y crea una **Smart Home** Skill
   llamada `Noxus` para España.
2. En *Account Linking*, elige **Authorization Code Grant** y activa PKCE
   `S256`. Amazon muestra una o varias *Redirect URLs*: cópialas literalmente.
   Elige un `Client ID` (por ejemplo `noxus-alexa`) y genera un secreto largo
   y aleatorio. Configura estas dos URLs públicas de Noxus:

   ```text
   Authorization URI: https://panel.noxuscmmd.uk/api/alexa/authorize
   Access Token URI:  https://panel.noxuscmmd.uk/api/alexa/token
   ```

   Si tu dominio público no es `panel.noxuscmmd.uk`, sustituye las dos URLs por
   el que ya usa tu panel. Debe tener HTTPS con un certificado válido.
3. Crea en AWS una función Lambda Python 3.11. Sube
   `integrations/alexa/lambda_function.py`, selecciona su ARN como endpoint de
   la Skill y deja que Lambda tenga salida HTTPS a Internet.
   El adaptador debe conservar su `User-Agent` explícito: Cloudflare rechaza el
   genérico de `urllib` con HTTP 403 aunque la firma HMAC sea correcta.
4. Genera un secreto aleatorio de al menos 32 bytes. En la Lambda define:

   ```text
   NOXUS_ALEXA_URL=https://panel.noxuscmmd.uk/api/alexa/directive
   NOXUS_ALEXA_PROXY_SECRET=<el secreto aleatorio>
   ```

5. En la Skill habilita **Send Alexa Events**. Amazon te dará el Client ID y el
   Client Secret del Event Gateway. Añade a `.env` del panel, con los datos de
   los pasos anteriores:

   ```dotenv
   ALEXA_OAUTH_CLIENT_ID=noxus-alexa
   ALEXA_OAUTH_CLIENT_SECRET=<secreto-de-account-linking>
   ALEXA_OAUTH_REDIRECT_URIS=<las-redirect-urls-de-amazon-separadas-por-comas>
   ALEXA_PROXY_SECRET=<el-mismo-secreto-de-la-lambda>
   ALEXA_EVENT_CLIENT_ID=<client-id-del-event-gateway>
   ALEXA_EVENT_CLIENT_SECRET=<client-secret-del-event-gateway>
   ```

6. Reinicia `noxus-panel` cuando hayas guardado esas variables. Entonces
   habilita la Skill y pulsa **Link account** una vez. El navegador abrirá
   Noxus: inicia sesión como administrador y confirma *Autorizar Alexa*.
   Amazon entrega después el permiso de eventos; Noxus guarda sus testigos en
   `alexa_cloud.json` con permisos de archivo `0600`.
7. En Noxus abre **Ajustes → Alexa y voz**, crea un elemento no crítico y
   guárdalo. Debe aparecer en Alexa sin abrir su app ni pedir descubrir
   dispositivos.

## Operación después del enlace

Para añadir, cambiar o retirar controles ya no se crea una rutina ni se vuelve
a la app Alexa. Todo se hace en **Alexa y voz**:

1. Pulsa **Crear elemento para Alexa**.
2. Escribe el nombre que Alexa debe oír.
3. Elige dispositivo o acción.
4. Selecciona las actuaciones existentes del panel con el buscador.
5. Guarda. Noxus publica el cambio de forma proactiva.

Smart Home permite nombres dinámicos, pero no verbos arbitrarios. Los
dispositivos aceptan «Alexa, enciende NOMBRE» y «Alexa, apaga NOMBRE»; las
acciones se publican en la dirección elegida y aceptan
«enciende/activa NOMBRE» o «apaga/desactiva NOMBRE». Por ejemplo, `Netflix`
puede usar «Alexa, activa Netflix», mientras que una secuencia `Habitación`
puede usar «Alexa, apaga Habitación».

El nombre debe ir sin verbo. Además, Amazon puede interpretar «apaga todo»
como su propia orden global antes de consultar la Skill. Para una secuencia de
Noxus conviene usar un nombre inequívoco, por ejemplo `Todo Noxus`, y decir
«Alexa, apaga Todo Noxus». No se puede registrar dinámicamente una frase
completamente libre como «lanza Netflix» sin añadir un modelo Custom a la Skill.

El antiguo puente Hue local se apaga automáticamente cuando están configurados
los eventos de la Skill oficial, evitando publicar dos veces las frases locales.
Puede forzarse solo para diagnóstico con `ALEXA_HUE_ENABLED=1`.

Para revocar el acceso se deshabilita la Skill y se elimina `alexa_cloud.json`
con el servicio parado; eso obliga a vincular de nuevo.

Para publicar la Skill para otras personas, Amazon exige completar su proceso
de certificación y páginas públicas de privacidad/condiciones. Para tu propia
cuenta basta probarla desde la fase de desarrollo.
