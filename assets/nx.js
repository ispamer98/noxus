/* NOXUS · Obsidiana — foco de tarjetas, aurora armada y red de nodos.
   Todo es pasivo y la animación se para si la pestaña no se ve o se pide
   menos movimiento. La suscripción anticipada del rediseño nuevo se conserva. */
(function () {
  if (window.__nxObsidiana) return;
  window.__nxObsidiana = true;

  var mediaReducido = window.matchMedia('(prefers-reduced-motion: reduce)');
  var reducido = mediaReducido.matches;
  var armado = { actual: 0, desde: 0, hasta: 0, inicio: 0 };
  var avisosArmado = [];

  function nivelArmado(ahora) {
    if (reducido) {
      armado.actual = armado.hasta;
      return armado.actual;
    }
    var t = Math.min(1, Math.max(0, (ahora - armado.inicio) / 1000));
    /* Curva suave sin trabajo adicional: solo interpola dos colores que el
       lienzo ya iba a calcular en su fotograma normal. */
    t = t * t * (3 - 2 * t);
    armado.actual = armado.desde + (armado.hasta - armado.desde) * t;
    return armado.actual;
  }

  /* La suscripción de avisos de ESTE navegador se prepara mientras conecta el
     panel. Este bloque se conserva sin cambiar su contrato: siempre resuelve
     una cadena y nunca impide que la interfaz arranque. */
  if (!window.__nxSuscripcion) {
    window.__nxSuscripcion = (async function () {
      try {
        if (!('serviceWorker' in navigator)) return '';
        var reg = await navigator.serviceWorker.getRegistration();
        if (!reg) return '';
        if (!reg.active) {
          var espera = new Promise(function (r) { setTimeout(function () { r(null); }, 1500); });
          reg = await Promise.race([navigator.serviceWorker.ready, espera]);
          if (!reg) return '';
        }
        var sub = await reg.pushManager.getSubscription();
        return sub ? sub.endpoint : '';
      } catch (e) {
        return '';
      }
    })();
  }

  /* data-nx-armado vive en la raíz de la página. Copiar solo ese atributo a
     html permite teñir el ambiente sin el selector :has(), caro en el móvil. */
  function copiarArmado() {
    /* Se busca DENTRO del body: este mismo atributo se copia a <html>, y con
       document.querySelector el primer resultado era <html> (leyéndose a sí
       mismo), así que el cambio de armado no llegaba nunca. */
    var raiz = (document.body || document.documentElement).querySelector('[data-nx-armado]');
    if (!raiz) return;
    var nuevo = raiz.getAttribute('data-nx-armado') === 'true' ? 1 : 0;
    if (nuevo !== armado.hasta) {
      armado.desde = nivelArmado(performance.now());
      armado.hasta = nuevo;
      armado.inicio = performance.now();
      avisosArmado.forEach(function (avisar) { avisar(); });
    }
    document.documentElement.setAttribute(
      'data-nx-armado', nuevo ? 'true' : 'false'
    );
  }
  copiarArmado();
  window.setInterval(copiarArmado, 1000);

  /* Solo el cristal bajo el ratón recibe el foco; los dedos no ejecutan este
     camino y por tanto no fuerzan repintados extra en iPhone. */
  var pend = null, ev = null;
  document.addEventListener('pointermove', function (e) {
    if (e.pointerType !== 'mouse') return;
    ev = e;
    if (pend) return;
    pend = requestAnimationFrame(function () {
      pend = null;
      var c = ev.target && ev.target.closest && ev.target.closest('.nx-card, .nx-tile, .nx-family');
      if (!c) return;
      var r = c.getBoundingClientRect();
      c.style.setProperty('--mx', (ev.clientX - r.left) + 'px');
      c.style.setProperty('--my', (ev.clientY - r.top) + 'px');
    });
  }, { passive: true });

  function fondo() {
    if (document.getElementById('nx-nodos')) return;
    var cv = document.createElement('canvas');
    cv.id = 'nx-nodos';
    cv.setAttribute('aria-hidden', 'true');
    document.body.insertBefore(cv, document.body.firstChild);
    var ctx = cv.getContext('2d');
    if (!ctx) return;

    var movil = window.matchMedia('(max-width: 767px)');
    var dpr = Math.min(window.devicePixelRatio || 1, 1.5);
    var ION = [62, 224, 255], PLA = [139, 124, 255];
    var GUARD = [220, 20, 60], PINK = [255, 70, 110];
    var W = 0, H = 0, nodos = [], pulsos = [];
    var raton = { x: 0, y: 0, on: false };
    var raf = 0, ultimo = 0;

    function cuantos() {
      /* En el móvil la pantalla es pequeña y 23 nodos apenas se notaban: más
         densidad (un nodo cada ~6.500 px²) pero con enlaces más cortos (ver
         ENLACE), así que el coste por fotograma sigue siendo mínimo. */
      var max = movil.matches ? 54 : 90;
      var min = movil.matches ? 36 : 24;
      return Math.max(min, Math.min(max, Math.round(W * H / (movil.matches ? 6500 : 14000))));
    }
    function crear() {
      nodos = [];
      for (var i = 0, n = cuantos(); i < n; i++) {
        nodos.push({
          x: Math.random() * W, y: Math.random() * H,
          vx: (Math.random() - 0.5) * 0.16,
          vy: (Math.random() - 0.5) * 0.16,
          /* En móvil cada nodo necesita algo más de cuerpo para destacar. */
          r: (Math.random() * 1.4 + 0.8) * (movil.matches ? 1.4 : 1),
          plasma: Math.random() < 0.3,
          c: ''
        });
      }
    }
    function color(nodo, nivel) {
      var base = nodo && nodo.plasma ? PLA : ION;
      var destino = nodo && nodo.plasma ? PINK : GUARD;
      return [0, 1, 2].map(function (i) {
        return Math.round(base[i] + (destino[i] - base[i]) * nivel);
      }).join(',');
    }
    /* Cuánta luz del foco recibe un punto: el foco armado está en la esquina
       superior izquierda (el mismo sitio que el degradado de nx.css, ~5 % y
       ~2 % de la pantalla) y su alcance es una elipse. 1 junto al foco, 0 fuera. */
    function luz(x, y) {
      var d = Math.hypot((x - W * 0.05) / (W * 0.62), (y - H * 0.02) / (H * 0.55));
      if (d >= 1) return 0;
      var u = 1 - d;
      return u * u * (3 - 2 * u);
    }
    function medir() {
      W = cv.clientWidth;
      H = cv.clientHeight;
      dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      cv.width = Math.round(W * dpr);
      cv.height = Math.round(H * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      crear();
    }
    function pulso() {
      if (nodos.length < 2 || pulsos.length > 5) return;
      var a = nodos[Math.floor(Math.random() * nodos.length)];
      var cerca = [], i, m;
      for (i = 0; i < nodos.length; i++) {
        m = nodos[i];
        if (m !== a && Math.hypot(m.x - a.x, m.y - a.y) < 200) cerca.push(m);
      }
      if (cerca.length) {
        pulsos.push({ a: a, b: cerca[Math.floor(Math.random() * cerca.length)], t: 0 });
      }
    }
    function frame(k) {
      ctx.clearRect(0, 0, W, H);
      var i, j, n, m, d, dx, dy, p;
      var tinte = nivelArmado(performance.now());
      var ENLACE = movil.matches ? 125 : 190;   /* alcance de las líneas */
      var REALCE = movil.matches ? 1.4 : 1;     /* en el móvil se ven más */
      var colorPulso = color(null, tinte);
      ctx.lineWidth = 1;
      for (i = 0; i < nodos.length; i++) {
        n = nodos[i];
        n.c = color(n, tinte);
        n.l = tinte ? luz(n.x, n.y) * tinte : 0;
        if (k) {
          n.x += n.vx * k;
          n.y += n.vy * k;
          if (n.x < -20) n.x = W + 20; else if (n.x > W + 20) n.x = -20;
          if (n.y < -20) n.y = H + 20; else if (n.y > H + 20) n.y = -20;
          if (raton.on) {
            dx = raton.x - n.x;
            dy = raton.y - n.y;
            if (Math.hypot(dx, dy) < 140) {
              n.x -= dx * 0.0025 * k;
              n.y -= dy * 0.0025 * k;
            }
          }
        }
        for (j = i + 1; j < nodos.length; j++) {
          m = nodos[j];
          d = Math.hypot(n.x - m.x, n.y - m.y);
          if (d < ENLACE) {
            /* Armada, las líneas se ven más y las cercanas al foco se encienden. */
            ctx.strokeStyle = 'rgba(' + n.c + ',' +
              ((1 - d / ENLACE) * REALCE * (0.22 + tinte * 0.14 + ((n.l || 0) + (m.l || 0)) * 0.28)) + ')';
            ctx.beginPath();
            ctx.moveTo(n.x, n.y);
            ctx.lineTo(m.x, m.y);
            ctx.stroke();
          }
        }
      }
      for (i = 0; i < nodos.length; i++) {
        n = nodos[i];
        /* Halo de luz: un círculo amplio y muy tenue (sin shadowBlur, que en
           el móvil cuesta demasiado) solo en los nodos que alumbra el foco. */
        if (n.l > 0.04) {
          ctx.fillStyle = 'rgba(' + n.c + ',' + (n.l * 0.16) + ')';
          ctx.beginPath();
          ctx.arc(n.x, n.y, n.r * (3.4 + n.l * 2.6), 0, 6.2832);
          ctx.fill();
        }
        ctx.fillStyle = 'rgba(' + n.c + ',' + (0.8 + tinte * 0.1 + (n.l || 0) * 0.1) + ')';
        ctx.beginPath();
        ctx.arc(n.x, n.y, n.r * (1 + (n.l || 0) * 0.5), 0, 6.2832);
        ctx.fill();
      }
      if (!k) return;
      pulsos = pulsos.filter(function (q) { return q.t < 1; });
      for (i = 0; i < pulsos.length; i++) {
        p = pulsos[i];
        p.t += 0.012 * k;
        ctx.beginPath();
        ctx.fillStyle = 'rgba(' + colorPulso + ',' + Math.max(0, 1 - p.t) + ')';
        /* El halo es bonito en escritorio; en móvil se evita su coste. */
        if (!movil.matches) {
          ctx.shadowColor = 'rgba(' + colorPulso + ',0.9)';
          ctx.shadowBlur = 8;
        }
        ctx.arc(p.a.x + (p.b.x - p.a.x) * p.t,
          p.a.y + (p.b.y - p.a.y) * p.t, 2.2, 0, 6.2832);
        ctx.fill();
        ctx.shadowBlur = 0;
      }
      if (Math.random() < 0.02 * k) pulso();
    }
    function bucle(t) {
      raf = window.requestAnimationFrame(bucle);
      if (t - ultimo < 32) return;
      var k = Math.min(3, (t - ultimo) / 16.67);
      ultimo = t;
      frame(k);
    }
    function arrancar() {
      if (!reducido && !raf && !document.hidden) {
        ultimo = performance.now();
        raf = window.requestAnimationFrame(bucle);
      }
    }
    function parar() {
      if (raf) {
        window.cancelAnimationFrame(raf);
        raf = 0;
      }
    }

    var rz = 0;
    window.addEventListener('resize', function () {
      clearTimeout(rz);
      rz = setTimeout(function () { medir(); if (reducido) frame(0); }, 150);
    });
    window.addEventListener('mousemove', function (e) {
      raton.x = e.clientX;
      raton.y = e.clientY;
      raton.on = true;
    }, { passive: true });
    document.documentElement.addEventListener('mouseleave', function () { raton.on = false; });
    document.addEventListener('visibilitychange', function () {
      if (document.hidden) parar(); else arrancar();
    });
    mediaReducido.addEventListener('change', function (e) {
      reducido = e.matches;
      if (reducido) { parar(); frame(0); } else arrancar();
    });
    avisosArmado.push(function () {
      /* Con movimiento reducido no hay bucle: se repinta una vez y queda
         quieto, pero el estado armado sigue siendo visible. */
      if (reducido) frame(0);
    });

    medir();
    frame(0);
    arrancar();
  }

  if (document.body) fondo(); else document.addEventListener('DOMContentLoaded', fondo);

  /* Matriz de glifos para las superficies que Radix monta en portales. No se
     añade componente por componente: el observador encuentra popovers, menús,
     selectores y tarjetas flotantes al abrirse. Todos comparten un solo bucle,
     limitado a ~6 fps; fuera de pantalla se para y con movimiento reducido se
     dibuja una vez y queda quieto. */
  (function () {
    var NAVEGACION = '.nx-sidebar, .nx-topbar, .nx-dock';
    var SELECTOR = '.rt-PopoverContent, .rt-BaseMenuContent, .rt-DropdownMenuContent, ' +
      '.rt-ContextMenuContent, .rt-SelectContent, .rt-HoverCardContent, ' + NAVEGACION;
    var GLIFOS = '01·+×/\\<>=';
    var matrices = [];
    var raf = 0, ultimo = 0;

    function medir(cv) {
      var w = cv.clientWidth, h = cv.clientHeight;
      if (!w || !h) return;
      var dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      cv.width = Math.round(w * dpr);
      cv.height = Math.round(h * dpr);
      var ctx = cv.getContext('2d');
      if (!ctx) return;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      var cols = Math.ceil(w / 15), filas = Math.ceil(h / 15), total = cols * filas;
      cv.__nx = {
        ctx: ctx, w: w, h: h, cols: cols, filas: filas,
        celdas: Array.from({ length: total }, function () {
          return GLIFOS[Math.floor(Math.random() * GLIFOS.length)];
        }),
        alfas: Array.from({ length: total }, function () {
          return 0.06 + Math.random() * 0.14;
        })
      };
      dibujar(cv);
    }

    function dibujar(cv) {
      var m = cv.__nx;
      if (!m) return;
      var rgb = getComputedStyle(document.documentElement)
        .getPropertyValue('--nx-info-rgb').trim() || '62, 224, 255';
      m.ctx.clearRect(0, 0, m.w, m.h);
      m.ctx.font = '500 10px "Geist Mono", ui-monospace, monospace';
      m.ctx.textBaseline = 'top';
      for (var y = 0; y < m.filas; y++) {
        for (var x = 0; x < m.cols; x++) {
          var i = y * m.cols + x;
          m.ctx.fillStyle = 'rgba(' + rgb + ',' + m.alfas[i] + ')';
          m.ctx.fillText(m.celdas[i], x * 15 + 3, y * 15 + 2);
        }
      }
    }

    function mutar(cv) {
      var m = cv.__nx;
      if (!m) return;
      var cambios = Math.max(1, Math.floor(m.celdas.length * 0.025));
      for (var n = 0; n < cambios; n++) {
        var i = Math.floor(Math.random() * m.celdas.length);
        m.celdas[i] = GLIFOS[Math.floor(Math.random() * GLIFOS.length)];
        m.alfas[i] = 0.06 + Math.random() * 0.14;
      }
      dibujar(cv);
    }

    var redimensionar = new ResizeObserver(function (entradas) {
      entradas.forEach(function (entrada) { medir(entrada.target); });
    });

    function preparar(superficie) {
      if (superficie.getAttribute('data-nx-glyph') === '1') return;
      superficie.setAttribute('data-nx-glyph', '1');
      var cv = document.createElement('canvas');
      cv.className = 'nx-glyph-matrix' +
        (superficie.matches(NAVEGACION) ? ' nx-glyph-navigation' : '');
      cv.setAttribute('aria-hidden', 'true');
      superficie.insertBefore(cv, superficie.firstChild);
      matrices.push(cv);
      redimensionar.observe(cv);
      medir(cv);
      arrancar();
    }

    function buscar(raiz) {
      if (!raiz || raiz.nodeType !== 1) return;
      if (raiz.matches(SELECTOR)) preparar(raiz);
      raiz.querySelectorAll(SELECTOR).forEach(preparar);
    }

    function bucle(t) {
      raf = requestAnimationFrame(bucle);
      if (t - ultimo < 170) return;
      ultimo = t;
      matrices = matrices.filter(function (cv) {
        if (!cv.isConnected) { redimensionar.unobserve(cv); return false; }
        mutar(cv);
        return true;
      });
      if (!matrices.length) parar();
    }

    function arrancar() {
      if (matrices.length && !reducido && !document.hidden && !raf) {
        ultimo = performance.now();
        raf = requestAnimationFrame(bucle);
      }
    }
    function parar() {
      if (raf) { cancelAnimationFrame(raf); raf = 0; }
    }

    new MutationObserver(function (cambios) {
      cambios.forEach(function (cambio) {
        cambio.addedNodes.forEach(buscar);
      });
    }).observe(document.documentElement, { childList: true, subtree: true });
    buscar(document.documentElement);
    document.addEventListener('visibilitychange', function () {
      if (document.hidden) parar(); else arrancar();
    });
    mediaReducido.addEventListener('change', function (e) {
      reducido = e.matches;
      matrices.forEach(dibujar);
      if (reducido) parar(); else arrancar();
    });
    arrancar();
  })();

  /* Háptico al pulsar, solo en las zonas elegidas (ZONAS y VISTAS, abajo).
     iPhone: no existe navigator.vibrate, pero desde iOS 18 Safari da un toque
     háptico cuando un toque de verdad activa un interruptor nativo
     (<input type=checkbox switch>). El clic por código no vale: se probó en el
     iPhone de la casa (haptico.html, variante C) y no vibra.
     Por eso cada elemento con onClick (React guarda las props en el propio
     nodo: __reactProps$…) de esas zonas lleva encima una <label> transparente
     con el interruptor dentro. El dedo toca la ETIQUETA, no el interruptor:
     - el interruptor nativo se reserva el arrastre (le da igual touch-action),
       y cuando cubría las tarjetas un scroll que empezara encima no movía la
       página y al soltar la pulsaba. Una etiqueta no se queda con nada: si hay
       scroll, Safari no genera clic;
     - el clic de la etiqueta burbujea hasta el elemento como un toque normal
       (UNA acción, vibre o no) y, además, la etiqueta activa su interruptor,
       que es el que vibra; ese segundo clic se corta ahí mismo.
     Va como PRIMER hijo, para que un botón dentro de una tarjeta (los tres
     puntos, mover/quitar) quede por encima de la etiqueta de su padre.
     Apagarlo: localStorage.nxHaptico = '0'. Android: navigator.vibrate.
     Solo en pantallas táctiles. */
  (function () {
    if (!window.matchMedia('(pointer: coarse)').matches) return;
    try { if (localStorage.getItem('nxHaptico') === '0') return; } catch (e) { /* sin localStorage: activo */ }
    var ua = navigator.userAgent;
    var ios = /iPhone|iPad|iPod/.test(ua) || (/Mac/.test(ua) && navigator.maxTouchPoints > 1);
    var EXCLUIR = 'input,textarea,select,option,label,video,canvas,iframe,svg,[contenteditable],[data-hap-no]';
    /* Barra de arriba (armado incluido), navegación de abajo y el aviso de armar con algo abierto. */
    var ZONAS = '.nx-topbar,.nx-dock,.nx-arm-blockers';
    /* data-vista de .nx-stage (ui/pages/dashboard.py). Ajustes: la portada
       de tarjetas (settings_hub) y todas sus sub-páginas. */
    var VISTAS = ['overview', 'floor_plan', 'video_wall', 'cctv', 'equipment', 'settings_hub',
      'alarm', 'groups', 'access', 'retardos', 'modos', 'usuarios', 'movimiento',
      'inventario', 'voz', 'pruebas', 'system', 'estancias', 'accesorios',
      'lights', 'ir_remotes', 'automations', 'presencia', 'instalador'];
    function enZona(el) {
      if (el.closest(ZONAS)) return true;
      var v = el.closest('[data-vista]');
      return !!v && VISTAS.indexOf(v.getAttribute('data-vista')) !== -1;
    }
    function conClick(el) {
      var ks = Object.keys(el);
      for (var i = 0; i < ks.length; i++) {
        if (ks[i].indexOf('__reactProps$') === 0) {
          var p = el[ks[i]];
          return !!(p && typeof p.onClick === 'function');
        }
      }
      return false;
    }
    if (!ios) {
      if (!('vibrate' in navigator)) return;
      document.addEventListener('click', function (e) {
        var n = e.target;
        for (var d = 0; n && n.nodeType === 1 && d < 6; d++, n = n.parentElement) {
          if (conClick(n)) { if (enZona(n)) navigator.vibrate(12); return; }
        }
      }, { passive: true, capture: true });
      return;
    }

    function poner(host, estatico) {
      try {
        if (estatico) host.style.position = 'relative';
        host.setAttribute('data-hap', '1');
        var et = document.createElement('label');
        et.className = 'nx-hap';
        et.setAttribute('aria-hidden', 'true');
        var sw = document.createElement('input');
        sw.type = 'checkbox';
        sw.setAttribute('switch', '');
        sw.tabIndex = -1;
        sw.addEventListener('click', function (e) {
          e.stopPropagation();
          setTimeout(function () { sw.checked = false; }, 0);
        });
        /* La etiqueta, al tocarla, le da el foco a su interruptor. Si hay un
           menú o una ventana de Radix abiertos, ese foco "fuera" los cierra
           (así se cerraba la ventana de Editar del menú de tres puntos). El
           foco no sale de aquí y vuelve a quien lo tenía. */
        sw.addEventListener('focusin', function (e) {
          e.stopPropagation();
          var antes = e.relatedTarget;
          if (antes && antes !== sw && antes.isConnected && antes.focus) antes.focus({ preventScroll: true });
          else sw.blur();
        });
        et.appendChild(sw);
        host.insertBefore(et, host.firstChild);
      } catch (e) { /* un elemento raro no puede romper el resto */ }
    }
    function barrer(raiz) {
      if (!raiz || raiz.nodeType !== 1) return;
      var todos = [raiz], sub = raiz.querySelectorAll('*'), i;
      for (i = 0; i < sub.length; i++) todos.push(sub[i]);
      var hosts = [];
      for (i = 0; i < todos.length; i++) {
        var el = todos[i];
        if (el.hasAttribute('data-hap') || el.matches(EXCLUIR) || el.disabled || el.getAttribute('aria-disabled') === 'true') continue;
        if (conClick(el) && enZona(el)) hosts.push(el);
      }
      /* Primero se lee todo y luego se escribe, para no forzar recálculos de estilo por elemento. */
      var pos = hosts.map(function (h) { var c = getComputedStyle(h); return c.display === 'contents' ? null : c.position === 'static'; });
      for (i = 0; i < hosts.length; i++) if (pos[i] !== null) poner(hosts[i], pos[i]);
    }
    var pendiente = false, nuevos = [];
    new MutationObserver(function (muts) {
      muts.forEach(function (m) {
        m.addedNodes.forEach(function (n) { if (n.nodeType === 1) nuevos.push(n); });
        /* React reescribe el texto de un botón con textContent y se lleva la
           etiqueta: si pasa, se libera la marca y se vuelve a poner. */
        m.removedNodes.forEach(function (n) {
          if (n.nodeType === 1 && n.classList && n.classList.contains('nx-hap') && m.target.removeAttribute) {
            m.target.removeAttribute('data-hap');
            nuevos.push(m.target);
          }
        });
      });
      if (pendiente || !nuevos.length) return;
      pendiente = true;
      requestAnimationFrame(function () {
        pendiente = false;
        var lote = nuevos; nuevos = [];
        lote.forEach(barrer);
      });
    }).observe(document.documentElement, { childList: true, subtree: true });
    barrer(document.documentElement);
  })();

  /* Vigilante de conexión: si el panel de casa se cae (reinicio, corte), en vez de
     dejar el aviso rojo de Reflex y el wifi tachado, recarga la página: el VPS
     contesta 502-504 y Traefik sirve «Algo tenemos en proceso…», que se recarga
     sola cuando el panel vuelve. Pide un archivo pequeño cada 1,5 s y recarga
     tras 2 errores 5XX seguidos (~3 s), para no reaccionar a un parpadeo que
     Reflex arregla solo reconectando. Sin red en el propio móvil NO recarga: no
     habría nada que enseñar (la petición falla sin respuesta, no con un 5xx). */
  (function () {
    var fallos = 0, ocupado = false;
    function comprobar() {
      if (ocupado || document.hidden || navigator.onLine === false) return;
      ocupado = true;
      fetch('/manifest.json?hb=' + Date.now(), { cache: 'no-store', credentials: 'omit' })
        .then(function (r) { fallos = r.status >= 500 ? fallos + 1 : 0; })
        .catch(function () { fallos = 0; })
        .then(function () {
          ocupado = false;
          if (fallos < 2) return;
          /* Freno: como mucho una recarga cada 20 s, por si algo devolviera 5xx
             también en la página recargada. */
          try {
            var antes = +sessionStorage.getItem('nxRecarga') || 0;
            if (Date.now() - antes < 20000) return;
            sessionStorage.setItem('nxRecarga', String(Date.now()));
          } catch (e) { /* sin sessionStorage: se recarga igualmente */ }
          location.reload();
        });
    }
    setInterval(comprobar, 1500);
    document.addEventListener('visibilitychange', comprobar);
  })();

  /* Kiosco: la tablet fija de una habitación (ui/pages/kiosco.py).
     No hace nada si la página no es un kiosco (no hay .nx-kiosco).
     - Reloj y fecha en la cabecera y en el reposo.
     - Pantalla siempre encendida con la Screen Wake Lock API (si el navegador la
       tiene; en iPad instalado como app depende de la versión de iOS, y la vía
       segura sigue siendo el Acceso guiado y no dejar que se bloquee).
     - Reposo a los 90 s sin tocar: casi negro con el reloj. Toda la pantalla de
       reposo tapa los controles, así que el primer toque solo despierta (y no pulsa nada).
     - Si aparece un aviso de alarma, despierta sola y no vuelve a dormir mientras
       siga a la vista.
     - Una tablet todavía sin acceso recarga sola cada 10 s hasta que un
       administrador la apruebe, salvo si alguien está escribiendo el nombre. */
  (function () {
    var REPOSO_S = 90, ultimo = Date.now(), luz = null, sinAcceso = 0;
    var dias = { weekday: 'long', day: 'numeric', month: 'long' };
    function kiosco() { return document.querySelector('.nx-kiosco'); }
    function pedirLuz() {
      if (!('wakeLock' in navigator) || luz || document.hidden) return;
      navigator.wakeLock.request('screen').then(function (l) {
        luz = l;
        l.addEventListener('release', function () { luz = null; });
      }).catch(function () { /* sin permiso o sin soporte: se sigue sin ello */ });
    }
    function despertar() {
      var k = kiosco();
      ultimo = Date.now();
      if (k && k.getAttribute('data-reposo') === '1') k.removeAttribute('data-reposo');
    }
    /* El toque que despierta la pantalla NO debe pulsar nada. Despertar quita el
       reposo ya en pointerdown, así que el click que llega al soltar caería sobre
       el control que hubiera debajo: se tragan el toque entero y el click que lo
       sigue (hasta soltar el dedo y un margen). */
    var gestoDeDespertar = 0, bloqueoHasta = 0;
    ['pointerdown', 'keydown', 'touchstart'].forEach(function (nombre) {
      document.addEventListener(nombre, function (e) {
        var k = kiosco();
        if (k && k.getAttribute('data-reposo') === '1') {
          e.stopPropagation();
          if (nombre === 'keydown') bloqueoHasta = Date.now() + 300;
          else gestoDeDespertar = Date.now();
        }
        despertar();
      }, true);
    });
    ['pointerup', 'pointercancel', 'touchend', 'touchcancel'].forEach(function (nombre) {
      document.addEventListener(nombre, function (e) {
        if (gestoDeDespertar) { e.stopPropagation(); gestoDeDespertar = 0; bloqueoHasta = Date.now() + 400; }
      }, true);
    });
    ['click', 'mousedown', 'mouseup', 'dblclick', 'contextmenu'].forEach(function (nombre) {
      document.addEventListener(nombre, function (e) {
        if ((gestoDeDespertar && Date.now() - gestoDeDespertar < 4000) || Date.now() < bloqueoHasta) {
          e.stopPropagation(); e.preventDefault();
        }
      }, true);
    });
    /* Inmersivo: fuera la barra de estado y la de navegación. La API de pantalla
       completa solo la concede un toque, así que se pide con el primer toque y se
       vuelve a pedir al siguiente si el sistema la quita. Además, en una página de
       kiosco el manifest pasa al del kiosco (display: fullscreen, apaisado): así,
       al instalarla como app, arranca a pantalla completa desde el principio. */
    function pantallaCompleta() {
      var el = document.documentElement;
      if (!kiosco() || document.fullscreenElement || !el.requestFullscreen) return;
      try { el.requestFullscreen({ navigationUI: 'hide' }).catch(function () {}); } catch (e) { /* sin soporte (iPad) */ }
    }
    ['pointerup', 'click'].forEach(function (nombre) { document.addEventListener(nombre, pantallaCompleta, true); });
    var manifiestoPuesto = false;
    function manifiestoDeKiosco() {
      if (manifiestoPuesto || !kiosco()) return;
      var m = document.querySelector('link[rel="manifest"]');
      if (m) { m.setAttribute('href', '/manifest-kiosco.json'); manifiestoPuesto = true; }
    }
    document.addEventListener('contextmenu', function (e) { if (kiosco()) e.preventDefault(); });
    document.addEventListener('gesturestart', function (e) { if (kiosco()) e.preventDefault(); });
    document.addEventListener('visibilitychange', function () { if (!document.hidden) { pedirLuz(); despertar(); } });
    /* Mural de cámaras: sin sonido por defecto y con reinicio de la imagen
       congelada. /cam/ es del mismo dominio, así que se puede mirar dentro del
       iframe. Las cámaras Tuya sueltan la sesión cada pocos minutos (go2rtc lo
       registra como «tuya: mqtt: disconnect»): si el vídeo deja de avanzar, se
       recarga SOLO esa celda, con espera creciente para no toparse con el límite
       de peticiones de Tuya. */
    var vigiladas = new WeakMap();
    function videoDe(f) {
      try {
        var d = f.contentDocument, s = d && d.querySelector('video-stream');
        return (s && s.video) || (d && d.querySelector('video')) || null;
      } catch (e) { return null; }
    }
    function reiniciar(f, e, ahora) {
      try { f.contentWindow.location.reload(); } catch (x) { f.src = f.src; }
      e.fallos = Math.min(e.fallos + 1, 4); e.desde = ahora; e.progresa = 0; e.sinVideo = 0;
    }
    function vigilarCamaras() {
      var fs = document.querySelectorAll('.nx-mural-celda iframe'), i, ahora = Date.now();
      for (i = 0; i < fs.length; i++) {
        var f = fs[i], v = videoDe(f), e = vigiladas.get(f);
        if (!e) { e = { t: -1, desde: ahora, fallos: 0, progresa: 0, sinVideo: 0 }; vigiladas.set(f, e); }
        var espera = 12000 * Math.pow(2, e.fallos);
        if (!v) {
          e.sinVideo = e.sinVideo || ahora;
          if (ahora - e.sinVideo > 25000 + espera) reiniciar(f, e, ahora);
          continue;
        }
        e.sinVideo = 0;
        var celda = f.parentNode;
        if (celda.getAttribute('data-sonido') !== '1' && !v.muted) v.muted = true;
        if (v.paused && !document.hidden) { var p = v.play(); if (p && p.catch) p.catch(function () {}); }
        if (v.currentTime !== e.t) {
          e.t = v.currentTime; e.desde = ahora;
          if (!e.progresa) e.progresa = ahora;
          else if (ahora - e.progresa > 30000) e.fallos = 0;
        } else if (!document.hidden && ahora - e.desde > espera) {
          reiniciar(f, e, ahora);
        }
      }
    }
    setInterval(function () { if (kiosco()) vigilarCamaras(); }, 3000);
    document.addEventListener('click', function (ev) {
      var b = ev.target.closest && ev.target.closest('.nx-mural-audio');
      if (!b) return;
      var celda = b.closest('.nx-mural-celda'), f = celda && celda.querySelector('iframe'), v = f && videoDe(f);
      var suena = celda.getAttribute('data-sonido') === '1' ? '0' : '1';
      celda.setAttribute('data-sonido', suena);
      if (v) { v.muted = suena !== '1'; if (suena === '1') { var p = v.play(); if (p && p.catch) p.catch(function () {}); } }
    });

    /* Sirena: la tablet suena mientras haya una alerta de alarma sin confirmar
       (data-alarma, de AlertasState.hay_pendientes) y la sirena esté activada
       (data-sirena). El sonido se genera aquí con Web Audio: no hay ficheros. El
       navegador solo deja sonar tras un toque en la página (o si la app está
       instalada): hasta entonces data-audio="bloqueado" avisa en pantalla. */
    var ctx = null, osc = null, amp = null, cadencia = null, suena = '', inicio = 0, probando = 0;
    function audio() {
      if (!ctx) {
        var C = window.AudioContext || window.webkitAudioContext;
        if (!C) return null;
        try { ctx = new C(); } catch (e) { return null; }
      }
      if (ctx.state === 'suspended') ctx.resume().catch(function () {});
      return ctx;
    }
    ['pointerdown', 'touchstart', 'keydown'].forEach(function (ev) {
      document.addEventListener(ev, function () { if (kiosco()) audio(); }, { passive: true });
    });
    function nota(nombre, t) {
      if (nombre === 'pitido') return [1000, (t % 0.5) < 0.25 ? 1 : 0];
      if (nombre === 'alarma') return [(t % 0.6) < 0.3 ? 880 : 660, 1];
      if (nombre === 'timbre') return [1400, Math.exp(-(t % 1.2) * 5)];
      return [650 + 500 * (0.5 + 0.5 * Math.sin(2 * Math.PI * t / 1.4 - Math.PI / 2)), 1];
    }
    function pararSirena() {
      if (cadencia) { clearInterval(cadencia); cadencia = null; }
      try { if (osc) osc.stop(); } catch (e) {}
      try { if (osc) osc.disconnect(); if (amp) amp.disconnect(); } catch (e) {}
      osc = amp = null; suena = '';
    }
    function arrancarSirena(nombre, vol) {
      var c = audio();
      if (!c || c.state !== 'running') return;
      pararSirena();
      osc = c.createOscillator(); amp = c.createGain();
      osc.type = nombre === 'timbre' ? 'sine' : (nombre === 'sirena' ? 'sawtooth' : 'square');
      amp.gain.value = 0; osc.connect(amp); amp.connect(c.destination); osc.start();
      inicio = c.currentTime; suena = nombre + '|' + vol;
      var techo = Math.max(0.05, Math.min(1, vol / 100)) * 0.9;
      cadencia = setInterval(function () {
        var n = nota(nombre, c.currentTime - inicio);
        osc.frequency.setTargetAtTime(n[0], c.currentTime, 0.01);
        amp.gain.setTargetAtTime(n[1] * techo, c.currentTime, 0.01);
      }, 40);
    }
    var ultimaPrueba = null;
    function sirena(k) {
      var pedida = k.getAttribute('data-prueba');
      if (ultimaPrueba === null) ultimaPrueba = pedida;
      else if (pedida !== ultimaPrueba) { ultimaPrueba = pedida; probando = Date.now() + 3000; audio(); }
      var activa = k.getAttribute('data-sirena') === 'true' && k.getAttribute('data-alarma') === 'true';
      var prueba = Date.now() < probando;
      var nombre = k.getAttribute('data-sonido') || 'sirena', vol = parseInt(k.getAttribute('data-volumen') || '75', 10);
      if (activa || prueba) {
        if (suena !== nombre + '|' + vol) arrancarSirena(nombre, vol);
      } else if (suena) {
        pararSirena();
      }
      k.setAttribute('data-audio', ((activa || k.getAttribute('data-sirena') === 'true') && (!ctx || ctx.state !== 'running')) ? 'bloqueado' : 'ok');
    }
    document.addEventListener('click', function (ev) {
      if (!(ev.target.closest && ev.target.closest('.nx-sirena-probar'))) return;
      probando = Date.now() + 3000; audio();
      var k = kiosco(); if (k) setTimeout(function () { sirena(k); }, 60);
    });

    setInterval(function () {
      var k = kiosco(), i, ahora = new Date();
      if (document.querySelector('[data-kiosco-espera]')) {
        var escribiendo = document.activeElement && /^(INPUT|TEXTAREA)$/.test(document.activeElement.tagName);
        var lleno = Array.prototype.some.call(document.querySelectorAll('input'), function (x) { return x.value; });
        sinAcceso = (escribiendo || lleno) ? 0 : sinAcceso + 1;
        if (sinAcceso >= 10) location.reload();
        return;
      }
      sinAcceso = 0;
      if (!k) return;
      manifiestoDeKiosco();
      pedirLuz();
      var hora = ahora.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' });
      var fecha = ahora.toLocaleDateString('es-ES', dias);
      fecha = fecha.charAt(0).toUpperCase() + fecha.slice(1);
      var h = document.querySelectorAll('.nx-kiosco-hora'), f = document.querySelectorAll('.nx-kiosco-fecha');
      for (i = 0; i < h.length; i++) if (h[i].textContent !== hora) h[i].textContent = hora;
      for (i = 0; i < f.length; i++) if (f[i].textContent !== fecha) f[i].textContent = fecha;
      sirena(k);
      if (document.querySelector('.nx-alert-notice')) despertar();
      else if ((Date.now() - ultimo) / 1000 > REPOSO_S) k.setAttribute('data-reposo', '1');
    }, 1000);
  })();
})();
