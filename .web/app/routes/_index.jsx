import {Fragment,useCallback,useContext,useEffect} from "react"
import {Badge as RadixThemesBadge,Box as RadixThemesBox,Button as RadixThemesButton,Card as RadixThemesCard,Code as RadixThemesCode,Dialog as RadixThemesDialog,Flex as RadixThemesFlex,Grid as RadixThemesGrid,Heading as RadixThemesHeading,Popover as RadixThemesPopover,Separator as RadixThemesSeparator,Switch as RadixThemesSwitch,Text as RadixThemesText,TextField as RadixThemesTextField} from "@radix-ui/themes"
import {ClientSide,EventLoopContext,StateContexts} from "$/utils/context"
import {ReflexEvent,isNotNullOrUndefined,isTrue} from "$/utils/state"
import {Activity as LucideActivity,Bell as LucideBell,Cctv as LucideCctv,Cpu as LucideCpu,Grape as LucideGrape,Laptop as LucideLaptop,Microchip as LucideMicrochip,Monitor as LucideMonitor,Network as LucideNetwork,PowerOff as LucidePowerOff,RefreshCw as LucideRefreshCw,RotateCw as LucideRotateCw,Smartphone as LucideSmartphone,Star as LucideStar,Tablet as LucideTablet,Thermometer as LucideThermometer,TriangleAlert as LucideTriangleAlert,Video as LucideVideo} from "lucide-react"
import {DynamicIcon} from "lucide-react/dynamic.mjs"
import {Badge_71e9a74001b2b3cb765f1218d44c7c03,Button_13d098fee24bcb1de97f8df2b2c719b9,Button_2747309f36bc9b7a24274549c2c850c2,Button_a397f95e192af40e10d13c7a5f34fab8,Button_bcb4fa1b3209c320edc5ea6d0901bdd8,Button_ce8938bada235488ecdaa7adc0c3279b,Button_cfb7c0dc3db1f366d309143cfc793645,Button_de8c4a731c4b018ce8f7caf8325f48e1,Iframe_222959a15c6cbea95102493c53b504ae,Iframe_b53914305b29756db0ab6667df718368,Switch_351e774a3f5408ef6b62c3ff767950f3,Switch_8660adb7ce8bc363fb963cc43e3eb67c,Text_f3ac6b1e71fcb3e1875f4c1124179851} from "$/utils/stateful_components"
import DebounceInput from "react-debounce-input"
import {jsx} from "@emotion/react"

const Moment = ClientSide(() => import('react-moment').then((mod) => mod.default.default ?? mod.default))


function Moment_429c094c5102ae8d52c7184a8a3a0888 () {
  const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_change_2d21f97941b54f886082b3f0691165d0 = useCallback(((_ev_0) => (addEvents([(ReflexEvent("reflex___state____state.noxuscmmd___state____state.actualizar_estados", ({  }), ({  })))], [_ev_0], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(Moment,{interval:8000,onChange:on_change_2d21f97941b54f886082b3f0691165d0},)
  )
}


function Button_1bf0f5f0266a2dd2307020c841f3b725 () {
  const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_click_fcf232ea9226b6f3e8cb7cbcbcf44e48 = useCallback(((_e) => (addEvents([(ReflexEvent("_redirect", ({ ["path"] : "/upload", ["external"] : false, ["popup"] : false, ["replace"] : false }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(RadixThemesButton,{css:({ ["opacity"] : "0.0000001", ["marginBottom"] : "-2em", ["marginTop"] : "-5em" }),onClick:on_click_fcf232ea9226b6f3e8cb7cbcbcf44e48},"Ir a Subida")
  )
}


function Dynamicicon_9b61213f8953e8b80f690a16edf4dde8 () {
  const reflex___state____state__noxuscmmd___state____state = useContext(StateContexts.reflex___state____state__noxuscmmd___state____state)



  return (
    jsx(DynamicIcon,{css:({ ["color"] : (reflex___state____state__noxuscmmd___state____state.sistema_armado_rx_state_ ? "#ff4d4d" : "#64748b") }),name:(reflex___state____state__noxuscmmd___state____state.sistema_armado_rx_state_ ? "shield-check" : "shield-off").replaceAll("_", "-")},)
  )
}


function Badge_323f2bfe8bf89ce5ff40ca665c0918b4 () {
  const reflex___state____state__noxuscmmd___state____state = useContext(StateContexts.reflex___state____state__noxuscmmd___state____state)



  return (
    jsx(RadixThemesBadge,{color:(reflex___state____state__noxuscmmd___state____state.puerta_abierta_rx_state_ ? "red" : "green"),variant:"surface"},(reflex___state____state__noxuscmmd___state____state.puerta_abierta_rx_state_ ? "PUERTA ABIERTA" : "CERRADA"))
  )
}


function Button_0b407949a87f4e8e362a4e7e64d2719c () {
  const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_click_0cdb9dd65b58ab23b0a524a9cdaa355c = useCallback(((_e) => (addEvents([(ReflexEvent("_call_script", ({ ["javascript_code"] : "\n                        (async function() {\n                            // 1. Obtener la suscripci\u00f3n activa del service worker\n                            let sub = null;\n                            try {\n                                const reg = await navigator.serviceWorker.ready;\n                                const pushSub = await reg.pushManager.getSubscription();\n                                if (pushSub) {\n                                    sub = {\n                                        endpoint: pushSub.endpoint,\n                                        keys: {\n                                            p256dh: btoa(String.fromCharCode.apply(null, new Uint8Array(pushSub.getKey('p256dh')))),\n                                            auth: btoa(String.fromCharCode.apply(null, new Uint8Array(pushSub.getKey('auth')))),\n                                        }\n                                    };\n                                }\n                            } catch(e) {\n                                console.warn('No se pudo obtener la suscripci\u00f3n:', e);\n                            }\n                            \n                            // 2. Llamar al m\u00e9todo de Reflex pasando la suscripci\u00f3n (o null)\n                            const subscription = sub ? JSON.stringify(sub) : 'null';\n                            // Llamar al evento de Reflex\n                            // Asumimos que State.lanzar_alerta_global espera un argumento\n                            // Usamos el mecanismo de eventos de Reflex\n                            return subscription;\n                        })();\n                        ", ["callback"] : "(_result) => {queueEvents([ReflexEvent(\"reflex___state____state.noxuscmmd___state____state.lanzar_alerta_global_con_subscripcion\", {subscription_json:_result})], socket, false, navigate, params);processEvent(socket, navigate, params);}" }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(RadixThemesButton,{onClick:on_click_0cdb9dd65b58ab23b0a524a9cdaa355c,size:"1",title:"Enviar alerta a todos",variant:"ghost"},jsx(LucideTriangleAlert,{css:({ ["color"] : "#f97316" }),size:18},))
  )
}


function Button_ac1f2726bf7c1ce3feaf8b80acc14de7 () {
  const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_click_8d6221c1636ea3a923b1fb4c3400d1fe = useCallback(((_e) => (addEvents([(ReflexEvent("_call_script", ({ ["javascript_code"] : "\n                        (async function() {\n                            try {\n                                let nombre = window.prompt(\"Nombre para este dispositivo (ej: Mi iPhone, PC Oficina):\", \"\");\n                                if (nombre === null) {\n                                    return \"USER_CANCEL\";\n                                }\n                                nombre = nombre.trim();\n                                if (nombre === \"\") {\n                                    alert(\"El nombre no puede estar vac\u00edo. Cancelado.\");\n                                    return \"USER_CANCEL\";\n                                }\n                                \n                                let reg;\n                                for (let intentos = 0; intentos < 3; intentos++) {\n                                    try {\n                                        reg = await navigator.serviceWorker.register('/sw.js');\n                                        await navigator.serviceWorker.ready;\n                                        break;\n                                    } catch (e) {\n                                        console.warn(\"Intento \" + (intentos+1) + \" fallido\", e);\n                                        await new Promise(r => setTimeout(r, 500));\n                                    }\n                                }\n                                if (!reg) throw new Error(\"No se pudo registrar el Service Worker\");\n                                \n                                const publicKey = 'BJkNTTmSZ9dLe1dt8nMyGYaL2Ip0_Z4LnwQzAG5kO9MjtvzInmmc-QbuksVCnb93VRmi82FLv8vtdnKAxiB8_Lg';\n                                const toUint8 = (b) => {\n                                    const pad = '='.repeat((4 - b.length % 4) % 4);\n                                    const b64 = (b + pad).replace(/-/g, '+').replace(/_/g, '/');\n                                    const raw = window.atob(b64);\n                                    const out = new Uint8Array(raw.length);\n                                    for (let i = 0; i < raw.length; ++i) out[i] = raw.charCodeAt(i);\n                                    return out;\n                                };\n                                \n                                const perm = await Notification.requestPermission();\n                                if (perm !== 'granted') return \"PERMISO_DENEGADO\";\n                                \n                                const sub = await reg.pushManager.subscribe({\n                                    userVisibleOnly: true,\n                                    applicationServerKey: toUint8(publicKey)\n                                });\n                                \n                                return JSON.stringify({\n                                    subscription: sub,\n                                    nombre: nombre\n                                });\n                            } catch (err) {\n                                if (err.name === \"NotAllowedError\") return \"PERMISO_BLOQUEADO\";\n                                return \"ERROR_\" + err.message;\n                            }\n                        })();\n                        ", ["callback"] : "(_result) => {queueEvents([ReflexEvent(\"reflex___state____state.noxuscmmd___state____state.guardar_subscripcion\", {js_result:_result})], socket, false, navigate, params);processEvent(socket, navigate, params);}" }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(RadixThemesButton,{onClick:on_click_8d6221c1636ea3a923b1fb4c3400d1fe,size:"1",title:"Suscribirse a notificaciones push",variant:"ghost"},jsx(LucideBell,{size:18},))
  )
}


function Button_972ed594066f4dfce53abd5b6e796d9a () {
  const reflex___state____state__noxuscmmd___state____state = useContext(StateContexts.reflex___state____state__noxuscmmd___state____state)
const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_click_aaf1b18ed356f32d838fe3e356da3f07 = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.noxuscmmd___state____state.conmutar_alarma", ({  }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(RadixThemesButton,{color:(reflex___state____state__noxuscmmd___state____state.sistema_armado_rx_state_ ? "red" : "green"),onClick:on_click_aaf1b18ed356f32d838fe3e356da3f07,size:"2",variant:(reflex___state____state__noxuscmmd___state____state.sistema_armado_rx_state_ ? "solid" : "surface")},(reflex___state____state__noxuscmmd___state____state.sistema_armado_rx_state_ ? "DESARMAR" : "ARMAR"))
  )
}


function Card_1392d3f84c8dacff4b72922fdb15e441 () {
  const reflex___state____state__noxuscmmd___state____state = useContext(StateContexts.reflex___state____state__noxuscmmd___state____state)



  return (
    jsx(RadixThemesCard,{css:({ ["width"] : "100%", ["background"] : "rgba(255, 255, 255, 0.03)", ["backdropFilter"] : "blur(10px)", ["border"] : (reflex___state____state__noxuscmmd___state____state.sistema_armado_rx_state_ ? "1px solid rgba(255, 77, 77, 0.3)" : "1px solid rgba(255, 255, 255, 0.1)"), ["padding"] : "4" })},jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",direction:"column",gap:"3"},jsx(RadixThemesFlex,{align:"center",className:"rx-Stack",css:({ ["width"] : "100%" }),direction:"row",gap:"3"},jsx(Dynamicicon_9b61213f8953e8b80f690a16edf4dde8,{},),jsx(RadixThemesHeading,{css:({ ["letterSpacing"] : "0.05em" }),size:"3"},"SEGURIDAD"),jsx(RadixThemesFlex,{css:({ ["flex"] : 1, ["justifySelf"] : "stretch", ["alignSelf"] : "stretch" })},),jsx(Badge_323f2bfe8bf89ce5ff40ca665c0918b4,{},),jsx(Button_0b407949a87f4e8e362a4e7e64d2719c,{},),jsx(Button_ac1f2726bf7c1ce3feaf8b80acc14de7,{},)),jsx(RadixThemesSeparator,{css:({ ["opacity"] : "0.1" }),size:"4"},),jsx(RadixThemesFlex,{align:"center",className:"rx-Stack",css:({ ["width"] : "100%" }),direction:"row",gap:"3"},jsx(RadixThemesText,{as:"p",css:({ ["color"] : "#94a3b8" }),size:"2"},"Monitoreo de Intrusi\u00f3n"),jsx(RadixThemesFlex,{css:({ ["flex"] : 1, ["justifySelf"] : "stretch", ["alignSelf"] : "stretch" })},),jsx(Button_972ed594066f4dfce53abd5b6e796d9a,{},))))
  )
}


function Flex_1a463b29c822ecd8c3fff73ee95cf1b3 () {
  const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_click_e9b5bf090bc97268e88cb73ecdd13e4a = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.noxuscmmd___state____state.toggle_fija_stream", ({  }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(RadixThemesFlex,{align:"center",className:"rx-Stack",css:({ ["cursor"] : "pointer" }),direction:"column",onClick:on_click_e9b5bf090bc97268e88cb73ecdd13e4a,gap:"0"},jsx(RadixThemesText,{as:"p",css:({ ["color"] : "gray" }),size:"1"},"H.Ppal"),jsx(LucideCctv,{css:({ ["color"] : "#38bdf8" }),size:20},))
  )
}


function Flex_0c924e4d22a095fb334c72ace196bf71 () {
  const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_click_db7b96222ed8fe4cce67700705f06d70 = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.noxuscmmd___state____state.toggle_ptz_stream", ({  }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(RadixThemesFlex,{align:"center",className:"rx-Stack",css:({ ["cursor"] : "pointer" }),direction:"column",onClick:on_click_db7b96222ed8fe4cce67700705f06d70,gap:"0"},jsx(RadixThemesText,{as:"p",css:({ ["color"] : "gray" }),size:"1"},"PTZ"),jsx(LucideRotateCw,{css:({ ["color"] : "#a78bfa" }),size:20},))
  )
}


function Network_3b6f19d448aaa99f005c5af690acbfbc () {
  const reflex___state____state__noxuscmmd___state____state = useContext(StateContexts.reflex___state____state__noxuscmmd___state____state)



  return (
    jsx(LucideNetwork,{css:({ ["transition"] : "transform 0.2s", ["&:hover"] : ({ ["transform"] : "scale(1.4)" }), ["color"] : (reflex___state____state__noxuscmmd___state____state.server_online_rx_state_ ? "green" : "red") })},)
  )
}


function Text_7e51451ee8b539e6b71d46b64e1e8fac () {
  const reflex___state____state__noxuscmmd___state____state = useContext(StateContexts.reflex___state____state__noxuscmmd___state____state)



  return (
    jsx(RadixThemesText,{as:"p",size:"1"},(reflex___state____state__noxuscmmd___state____state.server_online_rx_state_ ? "\ud83d\udfe2" : "\ud83d\udd34"))
  )
}


function Text_81938da8cf018dc8c036ae8494a85481 () {
  const reflex___state____state__noxuscmmd___state____state = useContext(StateContexts.reflex___state____state__noxuscmmd___state____state)



  return (
    jsx(RadixThemesText,{as:"p",css:({ ["color"] : (reflex___state____state__noxuscmmd___state____state.server_online_rx_state_ ? "green" : "red"), ["@media screen and (min-width: 0)"] : ({ ["display"] : "none" }), ["@media screen and (min-width: 30em)"] : ({ ["display"] : "none" }), ["@media screen and (min-width: 48em)"] : ({ ["display"] : "block" }), ["whiteSpace"] : "nowrap" })},(reflex___state____state__noxuscmmd___state____state.server_online_rx_state_ ? "\u202fEn l\u00ednea" : "\u202fSin conexi\u00f3n"))
  )
}


function Popover__trigger_8ed1217c5198f66ce20c0f7030913f47 () {
  const reflex___state____state__noxuscmmd___state____state = useContext(StateContexts.reflex___state____state__noxuscmmd___state____state)



  return (
    jsx(RadixThemesPopover.Trigger,{},jsx(RadixThemesBox,{css:({ ["width"] : "100%" })},jsx(RadixThemesFlex,{align:"center",className:"rx-Stack",css:({ ["cursor"] : "pointer", ["width"] : "100%" }),direction:"row",gap:"3"},jsx(LucideMonitor,{css:({ ["transition"] : "transform 0.2s", ["&:hover"] : ({ ["transform"] : "scale(1.4)" }), ["color"] : (reflex___state____state__noxuscmmd___state____state.pc_online_rx_state_ ? "green" : "red") })},),jsx(RadixThemesText,{as:"p",weight:"medium"},"PC"),jsx(RadixThemesFlex,{css:({ ["flex"] : 1, ["justifySelf"] : "stretch", ["alignSelf"] : "stretch" })},),jsx(RadixThemesFlex,{align:"center",className:"rx-Stack",direction:"row",gap:"2"},jsx(RadixThemesText,{as:"p",size:"1"},(reflex___state____state__noxuscmmd___state____state.pc_online_rx_state_ ? "\ud83d\udfe2" : "\ud83d\udd34")),jsx(RadixThemesText,{as:"p",css:({ ["color"] : (reflex___state____state__noxuscmmd___state____state.pc_online_rx_state_ ? "green" : "red"), ["@media screen and (min-width: 0)"] : ({ ["display"] : "none" }), ["@media screen and (min-width: 30em)"] : ({ ["display"] : "none" }), ["@media screen and (min-width: 48em)"] : ({ ["display"] : "block" }), ["whiteSpace"] : "nowrap" })},(reflex___state____state__noxuscmmd___state____state.pc_online_rx_state_ ? "\u202fEn l\u00ednea" : "\u202fSin conexi\u00f3n")),jsx(RadixThemesText,{as:"p",css:({ ["color"] : "gray.300", ["whiteSpace"] : "nowrap" }),size:"2"},"100.98.98.2")))))
  )
}


function Button_3c28cddf3ccbb95b4d59b05334ae6048 () {
  const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_click_532ac62784f1073a1c654024b178a391 = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.noxuscmmd___state____state.rdp_pc", ({  }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(RadixThemesButton,{css:({ ["border"] : "3px solid #000000", ["borderRadius"] : "12px", ["padding"] : "8px 16px", ["cursor"] : "pointer" }),onClick:on_click_532ac62784f1073a1c654024b178a391,variant:"soft"},"Conectar con PC \u2318")
  )
}


function Popover__trigger_8fc52d5406c3c1e6aaf473ac65d2aec2 () {
  const reflex___state____state__noxuscmmd___state____state = useContext(StateContexts.reflex___state____state__noxuscmmd___state____state)



  return (
    jsx(RadixThemesPopover.Trigger,{},jsx(RadixThemesBox,{css:({ ["width"] : "100%" })},jsx(RadixThemesFlex,{align:"center",className:"rx-Stack",css:({ ["cursor"] : "pointer", ["width"] : "100%" }),direction:"row",gap:"3"},jsx(LucideLaptop,{css:({ ["transition"] : "transform 0.2s", ["&:hover"] : ({ ["transform"] : "scale(1.4)" }), ["color"] : (reflex___state____state__noxuscmmd___state____state.portatil_online_rx_state_ ? "green" : "red") })},),jsx(RadixThemesText,{as:"p",weight:"medium"},"Port\u00e1til"),jsx(RadixThemesFlex,{css:({ ["flex"] : 1, ["justifySelf"] : "stretch", ["alignSelf"] : "stretch" })},),jsx(RadixThemesFlex,{align:"center",className:"rx-Stack",direction:"row",gap:"2"},jsx(RadixThemesText,{as:"p",size:"1"},(reflex___state____state__noxuscmmd___state____state.portatil_online_rx_state_ ? "\ud83d\udfe2" : "\ud83d\udd34")),jsx(RadixThemesText,{as:"p",css:({ ["color"] : (reflex___state____state__noxuscmmd___state____state.portatil_online_rx_state_ ? "green" : "red"), ["@media screen and (min-width: 0)"] : ({ ["display"] : "none" }), ["@media screen and (min-width: 30em)"] : ({ ["display"] : "none" }), ["@media screen and (min-width: 48em)"] : ({ ["display"] : "block" }), ["whiteSpace"] : "nowrap" })},(reflex___state____state__noxuscmmd___state____state.portatil_online_rx_state_ ? "\u202fEn l\u00ednea" : "\u202fSin conexi\u00f3n")),jsx(RadixThemesText,{as:"p",css:({ ["color"] : "gray.300", ["whiteSpace"] : "nowrap" }),size:"2"},"100.98.98.3")))))
  )
}


function Button_e38cc380e60d5cb13fd98507104dea0c () {
  const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_click_f2d031ab2bc9eccc08b043c5d7062429 = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.noxuscmmd___state____state.rdp_portatil", ({  }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(RadixThemesButton,{css:({ ["border"] : "3px solid #000000", ["borderRadius"] : "12px", ["padding"] : "8px 16px", ["cursor"] : "pointer" }),onClick:on_click_f2d031ab2bc9eccc08b043c5d7062429,variant:"soft"},"Conectar con Port\u00e1til \u2318")
  )
}


function Popover__trigger_5dcb7f6f6ca42f80fc5eee3db78cb130 () {
  const reflex___state____state__noxuscmmd___state____state = useContext(StateContexts.reflex___state____state__noxuscmmd___state____state)



  return (
    jsx(RadixThemesPopover.Trigger,{},jsx(RadixThemesBox,{css:({ ["width"] : "100%" })},jsx(RadixThemesFlex,{align:"center",className:"rx-Stack",css:({ ["cursor"] : "pointer", ["width"] : "100%" }),direction:"row",gap:"3"},jsx(LucideGrape,{css:({ ["transition"] : "transform 0.2s", ["&:hover"] : ({ ["transform"] : "scale(1.4)" }), ["color"] : (reflex___state____state__noxuscmmd___state____state.raspberry_online_rx_state_ ? "green" : "red") })},),jsx(RadixThemesText,{as:"p",weight:"medium"},"Raspberry"),jsx(RadixThemesFlex,{css:({ ["flex"] : 1, ["justifySelf"] : "stretch", ["alignSelf"] : "stretch" })},),jsx(RadixThemesFlex,{align:"center",className:"rx-Stack",direction:"row",gap:"2"},jsx(RadixThemesText,{as:"p",size:"1"},(reflex___state____state__noxuscmmd___state____state.raspberry_online_rx_state_ ? "\ud83d\udfe2" : "\ud83d\udd34")),jsx(RadixThemesText,{as:"p",css:({ ["color"] : (reflex___state____state__noxuscmmd___state____state.raspberry_online_rx_state_ ? "green" : "red"), ["@media screen and (min-width: 0)"] : ({ ["display"] : "none" }), ["@media screen and (min-width: 30em)"] : ({ ["display"] : "none" }), ["@media screen and (min-width: 48em)"] : ({ ["display"] : "block" }), ["whiteSpace"] : "nowrap" })},(reflex___state____state__noxuscmmd___state____state.raspberry_online_rx_state_ ? "\u202fEn l\u00ednea" : "\u202fSin conexi\u00f3n")),jsx(RadixThemesText,{as:"p",css:({ ["color"] : "gray.300", ["whiteSpace"] : "nowrap" }),size:"2"},"100.98.98.4")))))
  )
}


function Button_0bf533ffbd377012bbb9187c2d625a83 () {
  const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_click_ca7fddf2754bb7758a54167d0e5dfa38 = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.noxuscmmd___state____state.rdp_raspberry", ({  }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(RadixThemesButton,{css:({ ["border"] : "3px solid #000000", ["borderRadius"] : "12px", ["padding"] : "8px 16px", ["cursor"] : "pointer" }),onClick:on_click_ca7fddf2754bb7758a54167d0e5dfa38,variant:"soft"},"Conectar con Raspberry \u2318")
  )
}


function Microchip_517fc6202f1dc12b9752095c3324464f () {
  const reflex___state____state__noxuscmmd___state____state = useContext(StateContexts.reflex___state____state__noxuscmmd___state____state)



  return (
    jsx(LucideMicrochip,{css:({ ["transition"] : "transform 0.2s", ["&:hover"] : ({ ["transform"] : "scale(1.4)" }), ["color"] : (reflex___state____state__noxuscmmd___state____state.pi_zero_online_rx_state_ ? "green" : "red") })},)
  )
}


function Text_5bd62279cc0239c5ad3ffce6da7a071d () {
  const reflex___state____state__noxuscmmd___state____state = useContext(StateContexts.reflex___state____state__noxuscmmd___state____state)



  return (
    jsx(RadixThemesText,{as:"p",size:"1"},(reflex___state____state__noxuscmmd___state____state.pi_zero_online_rx_state_ ? "\ud83d\udfe2" : "\ud83d\udd34"))
  )
}


function Text_0cca01f0eafe464b9fb47832c9162412 () {
  const reflex___state____state__noxuscmmd___state____state = useContext(StateContexts.reflex___state____state__noxuscmmd___state____state)



  return (
    jsx(RadixThemesText,{as:"p",css:({ ["color"] : (reflex___state____state__noxuscmmd___state____state.pi_zero_online_rx_state_ ? "green" : "red"), ["@media screen and (min-width: 0)"] : ({ ["display"] : "none" }), ["@media screen and (min-width: 30em)"] : ({ ["display"] : "none" }), ["@media screen and (min-width: 48em)"] : ({ ["display"] : "block" }), ["whiteSpace"] : "nowrap" })},(reflex___state____state__noxuscmmd___state____state.pi_zero_online_rx_state_ ? "\u202fEn l\u00ednea" : "\u202fSin conexi\u00f3n"))
  )
}


function Smartphone_8fcd377e0c3148594b587b5c70046364 () {
  const reflex___state____state__noxuscmmd___state____state = useContext(StateContexts.reflex___state____state__noxuscmmd___state____state)



  return (
    jsx(LucideSmartphone,{css:({ ["transition"] : "transform 0.2s", ["&:hover"] : ({ ["transform"] : "scale(1.4)" }), ["color"] : (reflex___state____state__noxuscmmd___state____state.iphone_online_rx_state_ ? "green" : "red") })},)
  )
}


function Text_8d06d72142637555e74fcd7b9adf1a49 () {
  const reflex___state____state__noxuscmmd___state____state = useContext(StateContexts.reflex___state____state__noxuscmmd___state____state)



  return (
    jsx(RadixThemesText,{as:"p",size:"1"},(reflex___state____state__noxuscmmd___state____state.iphone_online_rx_state_ ? "\ud83d\udfe2" : "\ud83d\udd34"))
  )
}


function Text_e729cc855521ca75a7c17dcf6ba18173 () {
  const reflex___state____state__noxuscmmd___state____state = useContext(StateContexts.reflex___state____state__noxuscmmd___state____state)



  return (
    jsx(RadixThemesText,{as:"p",css:({ ["color"] : (reflex___state____state__noxuscmmd___state____state.iphone_online_rx_state_ ? "green" : "red"), ["@media screen and (min-width: 0)"] : ({ ["display"] : "none" }), ["@media screen and (min-width: 30em)"] : ({ ["display"] : "none" }), ["@media screen and (min-width: 48em)"] : ({ ["display"] : "block" }), ["whiteSpace"] : "nowrap" })},(reflex___state____state__noxuscmmd___state____state.iphone_online_rx_state_ ? "\u202fEn l\u00ednea" : "\u202fSin conexi\u00f3n"))
  )
}


function Tablet_e54126ee30779eadeef551eff4854f5c () {
  const reflex___state____state__noxuscmmd___state____state = useContext(StateContexts.reflex___state____state__noxuscmmd___state____state)



  return (
    jsx(LucideTablet,{css:({ ["transition"] : "transform 0.2s", ["&:hover"] : ({ ["transform"] : "scale(1.4)" }), ["color"] : (reflex___state____state__noxuscmmd___state____state.tablet_online_rx_state_ ? "green" : "red") })},)
  )
}


function Text_ad256b825972f849c7dec0a1f19cfdc5 () {
  const reflex___state____state__noxuscmmd___state____state = useContext(StateContexts.reflex___state____state__noxuscmmd___state____state)



  return (
    jsx(RadixThemesText,{as:"p",size:"1"},(reflex___state____state__noxuscmmd___state____state.tablet_online_rx_state_ ? "\ud83d\udfe2" : "\ud83d\udd34"))
  )
}


function Text_af01df48bd18ef0ef496fa59d2c0a432 () {
  const reflex___state____state__noxuscmmd___state____state = useContext(StateContexts.reflex___state____state__noxuscmmd___state____state)



  return (
    jsx(RadixThemesText,{as:"p",css:({ ["color"] : (reflex___state____state__noxuscmmd___state____state.tablet_online_rx_state_ ? "green" : "red"), ["@media screen and (min-width: 0)"] : ({ ["display"] : "none" }), ["@media screen and (min-width: 30em)"] : ({ ["display"] : "none" }), ["@media screen and (min-width: 48em)"] : ({ ["display"] : "block" }), ["whiteSpace"] : "nowrap" })},(reflex___state____state__noxuscmmd___state____state.tablet_online_rx_state_ ? "\u202fEn l\u00ednea" : "\u202fSin conexi\u00f3n"))
  )
}


function Popover__trigger_5dfab2a2601a2f5dcfbc3ece3ab2a887 () {
  const reflex___state____state__noxuscmmd___state____state = useContext(StateContexts.reflex___state____state__noxuscmmd___state____state)



  return (
    jsx(RadixThemesPopover.Trigger,{},jsx(RadixThemesButton,{size:"3",title:"Servidor",variant:"ghost"},jsx(LucideNetwork,{css:({ ["color"] : (reflex___state____state__noxuscmmd___state____state.server_online_rx_state_ ? "#4ade80" : "#64748b") }),size:28},)))
  )
}


function Button_6ed95d9b240756108db4873d58032614 () {
  const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_click_9320853e5fd6e700a2e1a604a421260b = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.noxuscmmd___state____state.accion_apagar", ({ ["device_key"] : "server" }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(RadixThemesButton,{color:"red",css:({ ["width"] : "100%" }),onClick:on_click_9320853e5fd6e700a2e1a604a421260b,size:"2",variant:"surface"},jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",direction:"row",gap:"3"},jsx(LucidePowerOff,{size:16},),jsx(RadixThemesText,{as:"p",size:"2"},"Apagar")))
  )
}


function Button_f11c4b7eefd92199c26340feca21833b () {
  const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_click_61270dd889f8a85021056588af8dcd81 = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.noxuscmmd___state____state.accion_reiniciar", ({ ["device_key"] : "server" }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(RadixThemesButton,{color:"orange",css:({ ["width"] : "100%" }),onClick:on_click_61270dd889f8a85021056588af8dcd81,size:"2",variant:"surface"},jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",direction:"row",gap:"3"},jsx(LucideRefreshCw,{size:16},),jsx(RadixThemesText,{as:"p",size:"2"},"Reiniciar")))
  )
}


function Button_c0b86d7d16d880825fa9b7aca7534fc4 () {
  const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_click_daae533ff3537b4c76b96a1b6621f0c0 = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.noxuscmmd___state____state.accion_temperatura", ({ ["device_key"] : "server" }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(RadixThemesButton,{color:"blue",css:({ ["width"] : "100%" }),onClick:on_click_daae533ff3537b4c76b96a1b6621f0c0,size:"2",variant:"surface"},jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",direction:"row",gap:"3"},jsx(LucideThermometer,{size:16},),jsx(RadixThemesText,{as:"p",size:"2"},"Temperatura")))
  )
}


function Debounceinput_a84c72c6259092d41309430ac658c731 () {
  const reflex___state____state__noxuscmmd___state____state = useContext(StateContexts.reflex___state____state__noxuscmmd___state____state)
const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_change_39aef66c15c52203c7296dc85f9c63d1 = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.noxuscmmd___state____state.set_custom_command", ({ ["device_key"] : "server", ["value"] : _e?.["target"]?.["value"] }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(DebounceInput,{css:({ ["width"] : "150px" }),debounceTimeout:300,element:RadixThemesTextField.Root,onChange:on_change_39aef66c15c52203c7296dc85f9c63d1,placeholder:"ls -la",size:"1",value:(isNotNullOrUndefined((isTrue(reflex___state____state__noxuscmmd___state____state.custom_command_rx_state_?.["server"]) ? reflex___state____state__noxuscmmd___state____state.custom_command_rx_state_?.["server"] : "")) ? (isTrue(reflex___state____state__noxuscmmd___state____state.custom_command_rx_state_?.["server"]) ? reflex___state____state__noxuscmmd___state____state.custom_command_rx_state_?.["server"] : "") : "")},)
  )
}


function Button_c7472fa5185ea34e01843530b6f49296 () {
  const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_click_4a84671b756d5e5acb12a8592a86965e = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.noxuscmmd___state____state.ejecutar_comando_personalizado", ({ ["device_key"] : "server" }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(RadixThemesButton,{onClick:on_click_4a84671b756d5e5acb12a8592a86965e,size:"1"},"Enviar")
  )
}


function Code_d130d2ca3ae5f73e47493af106ac65b0 () {
  const reflex___state____state__noxuscmmd___state____state = useContext(StateContexts.reflex___state____state__noxuscmmd___state____state)



  return (
    jsx(RadixThemesCode,{css:({ ["language"] : "bash", ["width"] : "100%" })},(isTrue(reflex___state____state__noxuscmmd___state____state.custom_output_rx_state_?.["server"]) ? reflex___state____state__noxuscmmd___state____state.custom_output_rx_state_?.["server"] : ""))
  )
}


function Fragment_3c43efab4e47b1d428f2286494b023f6 () {
  const reflex___state____state__noxuscmmd___state____state = useContext(StateContexts.reflex___state____state__noxuscmmd___state____state)



  return (
    jsx(Fragment,{},(!(((isTrue(reflex___state____state__noxuscmmd___state____state.custom_output_rx_state_?.["server"]) ? reflex___state____state__noxuscmmd___state____state.custom_output_rx_state_?.["server"] : "")?.valueOf?.() === ""?.valueOf?.()))?(jsx(Fragment,{},jsx(RadixThemesBox,{css:({ ["width"] : "100%", ["maxHeight"] : "150px", ["overflowY"] : "auto", ["background"] : "#1a1a1a", ["padding"] : "8px", ["borderRadius"] : "4px" })},jsx(Code_d130d2ca3ae5f73e47493af106ac65b0,{},)))):(jsx(Fragment,{},))))
  )
}


function Popover__trigger_51fdda2291ac772fef62563aaeff3a0b () {
  const reflex___state____state__noxuscmmd___state____state = useContext(StateContexts.reflex___state____state__noxuscmmd___state____state)



  return (
    jsx(RadixThemesPopover.Trigger,{},jsx(RadixThemesButton,{size:"3",title:"PC",variant:"ghost"},jsx(LucideMonitor,{css:({ ["color"] : (reflex___state____state__noxuscmmd___state____state.pc_online_rx_state_ ? "#4ade80" : "#64748b") }),size:28},)))
  )
}


function Button_310038ddfebb0f44143ccaae80d2bac7 () {
  const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_click_0bd49b20d39f59a6d25f81264897251d = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.noxuscmmd___state____state.accion_apagar", ({ ["device_key"] : "pc" }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(RadixThemesButton,{color:"red",css:({ ["width"] : "100%" }),onClick:on_click_0bd49b20d39f59a6d25f81264897251d,size:"2",variant:"surface"},jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",direction:"row",gap:"3"},jsx(LucidePowerOff,{size:16},),jsx(RadixThemesText,{as:"p",size:"2"},"Apagar")))
  )
}


function Button_070b922c537de1b0d4bce2a71126e979 () {
  const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_click_5781e2d89214be39c5a735ba8ac7e10f = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.noxuscmmd___state____state.accion_reiniciar", ({ ["device_key"] : "pc" }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(RadixThemesButton,{color:"orange",css:({ ["width"] : "100%" }),onClick:on_click_5781e2d89214be39c5a735ba8ac7e10f,size:"2",variant:"surface"},jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",direction:"row",gap:"3"},jsx(LucideRefreshCw,{size:16},),jsx(RadixThemesText,{as:"p",size:"2"},"Reiniciar")))
  )
}


function Button_ce52b76f300a58b9e7b39b4b6a1c1a9d () {
  const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_click_0fda317aae08913de8aa223f528c74c3 = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.noxuscmmd___state____state.accion_temperatura", ({ ["device_key"] : "pc" }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(RadixThemesButton,{color:"blue",css:({ ["width"] : "100%" }),onClick:on_click_0fda317aae08913de8aa223f528c74c3,size:"2",variant:"surface"},jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",direction:"row",gap:"3"},jsx(LucideThermometer,{size:16},),jsx(RadixThemesText,{as:"p",size:"2"},"Temperatura")))
  )
}


function Button_65f4c70b694db59097c14e51da2fa530 () {
  const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_click_6f2a812f237fb619c713e75c6dfa08b4 = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.noxuscmmd___state____state.wake_pc", ({  }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(RadixThemesButton,{color:"purple",css:({ ["width"] : "100%" }),onClick:on_click_6f2a812f237fb619c713e75c6dfa08b4,size:"2",variant:"surface"},jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",direction:"row",gap:"3"},jsx(LucideStar,{size:16},),jsx(RadixThemesText,{as:"p",size:"2"},"Wake on LAN")))
  )
}


function Button_c36c2d714823a648d88b55639160b45d () {
  const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_click_532ac62784f1073a1c654024b178a391 = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.noxuscmmd___state____state.rdp_pc", ({  }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(RadixThemesButton,{color:"purple",css:({ ["width"] : "100%" }),onClick:on_click_532ac62784f1073a1c654024b178a391,size:"2",variant:"surface"},jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",direction:"row",gap:"3"},jsx(LucideStar,{size:16},),jsx(RadixThemesText,{as:"p",size:"2"},"RDP")))
  )
}


function Debounceinput_f001d15bafbbbe05ef46731bf9581fbb () {
  const reflex___state____state__noxuscmmd___state____state = useContext(StateContexts.reflex___state____state__noxuscmmd___state____state)
const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_change_16a72b664f6fc0f32f5c49a8d79a3a85 = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.noxuscmmd___state____state.set_custom_command", ({ ["device_key"] : "pc", ["value"] : _e?.["target"]?.["value"] }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(DebounceInput,{css:({ ["width"] : "150px" }),debounceTimeout:300,element:RadixThemesTextField.Root,onChange:on_change_16a72b664f6fc0f32f5c49a8d79a3a85,placeholder:"ls -la",size:"1",value:(isNotNullOrUndefined((isTrue(reflex___state____state__noxuscmmd___state____state.custom_command_rx_state_?.["pc"]) ? reflex___state____state__noxuscmmd___state____state.custom_command_rx_state_?.["pc"] : "")) ? (isTrue(reflex___state____state__noxuscmmd___state____state.custom_command_rx_state_?.["pc"]) ? reflex___state____state__noxuscmmd___state____state.custom_command_rx_state_?.["pc"] : "") : "")},)
  )
}


function Button_86b5b99b7c1ea301c758f79396e978a4 () {
  const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_click_78b3b75d033d94e6a84ea3470b6587ae = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.noxuscmmd___state____state.ejecutar_comando_personalizado", ({ ["device_key"] : "pc" }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(RadixThemesButton,{onClick:on_click_78b3b75d033d94e6a84ea3470b6587ae,size:"1"},"Enviar")
  )
}


function Code_f879501465c9b68f0f9aa57bfa96d93e () {
  const reflex___state____state__noxuscmmd___state____state = useContext(StateContexts.reflex___state____state__noxuscmmd___state____state)



  return (
    jsx(RadixThemesCode,{css:({ ["language"] : "bash", ["width"] : "100%" })},(isTrue(reflex___state____state__noxuscmmd___state____state.custom_output_rx_state_?.["pc"]) ? reflex___state____state__noxuscmmd___state____state.custom_output_rx_state_?.["pc"] : ""))
  )
}


function Fragment_6e45bd8c265dacce9a47d5b361bcee03 () {
  const reflex___state____state__noxuscmmd___state____state = useContext(StateContexts.reflex___state____state__noxuscmmd___state____state)



  return (
    jsx(Fragment,{},(!(((isTrue(reflex___state____state__noxuscmmd___state____state.custom_output_rx_state_?.["pc"]) ? reflex___state____state__noxuscmmd___state____state.custom_output_rx_state_?.["pc"] : "")?.valueOf?.() === ""?.valueOf?.()))?(jsx(Fragment,{},jsx(RadixThemesBox,{css:({ ["width"] : "100%", ["maxHeight"] : "150px", ["overflowY"] : "auto", ["background"] : "#1a1a1a", ["padding"] : "8px", ["borderRadius"] : "4px" })},jsx(Code_f879501465c9b68f0f9aa57bfa96d93e,{},)))):(jsx(Fragment,{},))))
  )
}


function Popover__trigger_444090a467eb5f3bb14e826a4b87198d () {
  const reflex___state____state__noxuscmmd___state____state = useContext(StateContexts.reflex___state____state__noxuscmmd___state____state)



  return (
    jsx(RadixThemesPopover.Trigger,{},jsx(RadixThemesButton,{size:"3",title:"Port\u00e1til",variant:"ghost"},jsx(LucideLaptop,{css:({ ["color"] : (reflex___state____state__noxuscmmd___state____state.portatil_online_rx_state_ ? "#4ade80" : "#64748b") }),size:28},)))
  )
}


function Button_90238aa155f0a2e07636e4f6b35ae40a () {
  const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_click_e6a4203e64e8432e3756d2cebce5056b = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.noxuscmmd___state____state.accion_apagar", ({ ["device_key"] : "portatil" }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(RadixThemesButton,{color:"red",css:({ ["width"] : "100%" }),onClick:on_click_e6a4203e64e8432e3756d2cebce5056b,size:"2",variant:"surface"},jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",direction:"row",gap:"3"},jsx(LucidePowerOff,{size:16},),jsx(RadixThemesText,{as:"p",size:"2"},"Apagar")))
  )
}


function Button_93f1954b6197a1b5ab93b6c21bb1b07d () {
  const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_click_14297e01320ff8e392def27982af03d7 = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.noxuscmmd___state____state.accion_reiniciar", ({ ["device_key"] : "portatil" }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(RadixThemesButton,{color:"orange",css:({ ["width"] : "100%" }),onClick:on_click_14297e01320ff8e392def27982af03d7,size:"2",variant:"surface"},jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",direction:"row",gap:"3"},jsx(LucideRefreshCw,{size:16},),jsx(RadixThemesText,{as:"p",size:"2"},"Reiniciar")))
  )
}


function Button_277299bb39fef251727834f1c456401e () {
  const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_click_0363bc6e64f08f1df301abaaab8adaef = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.noxuscmmd___state____state.accion_temperatura", ({ ["device_key"] : "portatil" }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(RadixThemesButton,{color:"blue",css:({ ["width"] : "100%" }),onClick:on_click_0363bc6e64f08f1df301abaaab8adaef,size:"2",variant:"surface"},jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",direction:"row",gap:"3"},jsx(LucideThermometer,{size:16},),jsx(RadixThemesText,{as:"p",size:"2"},"Temperatura")))
  )
}


function Button_d02b738b29ac68fc7321f42cb1a8fb65 () {
  const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_click_f2d031ab2bc9eccc08b043c5d7062429 = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.noxuscmmd___state____state.rdp_portatil", ({  }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(RadixThemesButton,{color:"purple",css:({ ["width"] : "100%" }),onClick:on_click_f2d031ab2bc9eccc08b043c5d7062429,size:"2",variant:"surface"},jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",direction:"row",gap:"3"},jsx(LucideStar,{size:16},),jsx(RadixThemesText,{as:"p",size:"2"},"RDP")))
  )
}


function Debounceinput_e2bb32741d05bae98ba4e627ce5ad120 () {
  const reflex___state____state__noxuscmmd___state____state = useContext(StateContexts.reflex___state____state__noxuscmmd___state____state)
const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_change_145df5627f7502d6c60106598dc0ef5f = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.noxuscmmd___state____state.set_custom_command", ({ ["device_key"] : "portatil", ["value"] : _e?.["target"]?.["value"] }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(DebounceInput,{css:({ ["width"] : "150px" }),debounceTimeout:300,element:RadixThemesTextField.Root,onChange:on_change_145df5627f7502d6c60106598dc0ef5f,placeholder:"ls -la",size:"1",value:(isNotNullOrUndefined((isTrue(reflex___state____state__noxuscmmd___state____state.custom_command_rx_state_?.["portatil"]) ? reflex___state____state__noxuscmmd___state____state.custom_command_rx_state_?.["portatil"] : "")) ? (isTrue(reflex___state____state__noxuscmmd___state____state.custom_command_rx_state_?.["portatil"]) ? reflex___state____state__noxuscmmd___state____state.custom_command_rx_state_?.["portatil"] : "") : "")},)
  )
}


function Button_d5d5a27d36c21df7b3862c3f176ade26 () {
  const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_click_c3eaffd3705f841e6d86c58b946bc0e9 = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.noxuscmmd___state____state.ejecutar_comando_personalizado", ({ ["device_key"] : "portatil" }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(RadixThemesButton,{onClick:on_click_c3eaffd3705f841e6d86c58b946bc0e9,size:"1"},"Enviar")
  )
}


function Code_f85043e3609c256148a9849613b8fd28 () {
  const reflex___state____state__noxuscmmd___state____state = useContext(StateContexts.reflex___state____state__noxuscmmd___state____state)



  return (
    jsx(RadixThemesCode,{css:({ ["language"] : "bash", ["width"] : "100%" })},(isTrue(reflex___state____state__noxuscmmd___state____state.custom_output_rx_state_?.["portatil"]) ? reflex___state____state__noxuscmmd___state____state.custom_output_rx_state_?.["portatil"] : ""))
  )
}


function Fragment_390726caad2235dd0c9f52b2dd5e1bcb () {
  const reflex___state____state__noxuscmmd___state____state = useContext(StateContexts.reflex___state____state__noxuscmmd___state____state)



  return (
    jsx(Fragment,{},(!(((isTrue(reflex___state____state__noxuscmmd___state____state.custom_output_rx_state_?.["portatil"]) ? reflex___state____state__noxuscmmd___state____state.custom_output_rx_state_?.["portatil"] : "")?.valueOf?.() === ""?.valueOf?.()))?(jsx(Fragment,{},jsx(RadixThemesBox,{css:({ ["width"] : "100%", ["maxHeight"] : "150px", ["overflowY"] : "auto", ["background"] : "#1a1a1a", ["padding"] : "8px", ["borderRadius"] : "4px" })},jsx(Code_f85043e3609c256148a9849613b8fd28,{},)))):(jsx(Fragment,{},))))
  )
}


function Popover__trigger_b1cdfe01dea1a0a2ecdbaaf079109d98 () {
  const reflex___state____state__noxuscmmd___state____state = useContext(StateContexts.reflex___state____state__noxuscmmd___state____state)



  return (
    jsx(RadixThemesPopover.Trigger,{},jsx(RadixThemesButton,{size:"3",title:"Raspberry",variant:"ghost"},jsx(LucideGrape,{css:({ ["color"] : (reflex___state____state__noxuscmmd___state____state.raspberry_online_rx_state_ ? "#4ade80" : "#64748b") }),size:28},)))
  )
}


function Button_9d9c7bdf032a2a3fec83106fb6001da9 () {
  const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_click_7c6a61702d21f28d44f12ee65ab15426 = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.noxuscmmd___state____state.accion_apagar", ({ ["device_key"] : "raspberry" }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(RadixThemesButton,{color:"red",css:({ ["width"] : "100%" }),onClick:on_click_7c6a61702d21f28d44f12ee65ab15426,size:"2",variant:"surface"},jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",direction:"row",gap:"3"},jsx(LucidePowerOff,{size:16},),jsx(RadixThemesText,{as:"p",size:"2"},"Apagar")))
  )
}


function Button_9a12dfa3390b160a2a7fe6cfad01a545 () {
  const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_click_bbee1501b90cc381e02dbc6fd14e0e86 = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.noxuscmmd___state____state.accion_reiniciar", ({ ["device_key"] : "raspberry" }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(RadixThemesButton,{color:"orange",css:({ ["width"] : "100%" }),onClick:on_click_bbee1501b90cc381e02dbc6fd14e0e86,size:"2",variant:"surface"},jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",direction:"row",gap:"3"},jsx(LucideRefreshCw,{size:16},),jsx(RadixThemesText,{as:"p",size:"2"},"Reiniciar")))
  )
}


function Button_1225e323dd80622b62605bbd3b27e6d7 () {
  const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_click_f551b87d7c16b2a237d22bcf168750ee = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.noxuscmmd___state____state.accion_temperatura", ({ ["device_key"] : "raspberry" }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(RadixThemesButton,{color:"blue",css:({ ["width"] : "100%" }),onClick:on_click_f551b87d7c16b2a237d22bcf168750ee,size:"2",variant:"surface"},jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",direction:"row",gap:"3"},jsx(LucideThermometer,{size:16},),jsx(RadixThemesText,{as:"p",size:"2"},"Temperatura")))
  )
}


function Button_1339dec2cb5520e5e9850e4a9f1544c5 () {
  const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_click_b2099434464f470d7d730f670d11ac41 = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.noxuscmmd___state____state.accion_gpio", ({ ["device_key"] : "raspberry", ["pin"] : "17", ["estado"] : "on" }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(RadixThemesButton,{color:"green",onClick:on_click_b2099434464f470d7d730f670d11ac41,size:"1"},"ON")
  )
}


function Button_9863869f2c0ef74ce9c0add6e682ae76 () {
  const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_click_c7aea7b308b8d2834054531092b2236c = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.noxuscmmd___state____state.accion_gpio", ({ ["device_key"] : "raspberry", ["pin"] : "17", ["estado"] : "off" }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(RadixThemesButton,{color:"red",onClick:on_click_c7aea7b308b8d2834054531092b2236c,size:"1"},"OFF")
  )
}


function Button_275183e2baefb3074fcdeb20d8fb92b6 () {
  const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_click_cfe4e09fa7e1aecffa180a4431a9277c = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.noxuscmmd___state____state.gpio_17_test", ({  }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(RadixThemesButton,{color:"purple",css:({ ["width"] : "100%" }),onClick:on_click_cfe4e09fa7e1aecffa180a4431a9277c,size:"2",variant:"surface"},jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",direction:"row",gap:"3"},jsx(LucideStar,{size:16},),jsx(RadixThemesText,{as:"p",size:"2"},"Test Ventilador")))
  )
}


function Button_63aa688472d2bf433c194b1034848c51 () {
  const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_click_ca7fddf2754bb7758a54167d0e5dfa38 = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.noxuscmmd___state____state.rdp_raspberry", ({  }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(RadixThemesButton,{color:"purple",css:({ ["width"] : "100%" }),onClick:on_click_ca7fddf2754bb7758a54167d0e5dfa38,size:"2",variant:"surface"},jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",direction:"row",gap:"3"},jsx(LucideStar,{size:16},),jsx(RadixThemesText,{as:"p",size:"2"},"RDP")))
  )
}


function Button_055952fc777b3f8e12a4f403afb9c14c () {
  const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_click_5d89d46f2d6b460b5d6083241feb5569 = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.noxuscmmd___state____state.tomar_foto_raspberry", ({  }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(RadixThemesButton,{color:"purple",css:({ ["width"] : "100%" }),onClick:on_click_5d89d46f2d6b460b5d6083241feb5569,size:"2",variant:"surface"},jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",direction:"row",gap:"3"},jsx(LucideStar,{size:16},),jsx(RadixThemesText,{as:"p",size:"2"},"Foto (Pi Zero)")))
  )
}


function Debounceinput_11e44fdb7cddc7e309e10b373ec84d24 () {
  const reflex___state____state__noxuscmmd___state____state = useContext(StateContexts.reflex___state____state__noxuscmmd___state____state)
const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_change_b00a40a062a072b857bdb5ecedc98b1e = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.noxuscmmd___state____state.set_custom_command", ({ ["device_key"] : "raspberry", ["value"] : _e?.["target"]?.["value"] }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(DebounceInput,{css:({ ["width"] : "150px" }),debounceTimeout:300,element:RadixThemesTextField.Root,onChange:on_change_b00a40a062a072b857bdb5ecedc98b1e,placeholder:"ls -la",size:"1",value:(isNotNullOrUndefined((isTrue(reflex___state____state__noxuscmmd___state____state.custom_command_rx_state_?.["raspberry"]) ? reflex___state____state__noxuscmmd___state____state.custom_command_rx_state_?.["raspberry"] : "")) ? (isTrue(reflex___state____state__noxuscmmd___state____state.custom_command_rx_state_?.["raspberry"]) ? reflex___state____state__noxuscmmd___state____state.custom_command_rx_state_?.["raspberry"] : "") : "")},)
  )
}


function Button_a293889d2b6c1f6db62511ef78a7c7bc () {
  const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_click_7fc25e94651df18f0bd18897245fb2d4 = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.noxuscmmd___state____state.ejecutar_comando_personalizado", ({ ["device_key"] : "raspberry" }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(RadixThemesButton,{onClick:on_click_7fc25e94651df18f0bd18897245fb2d4,size:"1"},"Enviar")
  )
}


function Code_6d02a4fac64184f0a0cc891ac962f5ea () {
  const reflex___state____state__noxuscmmd___state____state = useContext(StateContexts.reflex___state____state__noxuscmmd___state____state)



  return (
    jsx(RadixThemesCode,{css:({ ["language"] : "bash", ["width"] : "100%" })},(isTrue(reflex___state____state__noxuscmmd___state____state.custom_output_rx_state_?.["raspberry"]) ? reflex___state____state__noxuscmmd___state____state.custom_output_rx_state_?.["raspberry"] : ""))
  )
}


function Fragment_4da39fc4814bd1549e1ae720f94e724b () {
  const reflex___state____state__noxuscmmd___state____state = useContext(StateContexts.reflex___state____state__noxuscmmd___state____state)



  return (
    jsx(Fragment,{},(!(((isTrue(reflex___state____state__noxuscmmd___state____state.custom_output_rx_state_?.["raspberry"]) ? reflex___state____state__noxuscmmd___state____state.custom_output_rx_state_?.["raspberry"] : "")?.valueOf?.() === ""?.valueOf?.()))?(jsx(Fragment,{},jsx(RadixThemesBox,{css:({ ["width"] : "100%", ["maxHeight"] : "150px", ["overflowY"] : "auto", ["background"] : "#1a1a1a", ["padding"] : "8px", ["borderRadius"] : "4px" })},jsx(Code_6d02a4fac64184f0a0cc891ac962f5ea,{},)))):(jsx(Fragment,{},))))
  )
}


function Popover__trigger_f95cdfcbf16810ed0cb807cc307c5ccd () {
  const reflex___state____state__noxuscmmd___state____state = useContext(StateContexts.reflex___state____state__noxuscmmd___state____state)



  return (
    jsx(RadixThemesPopover.Trigger,{},jsx(RadixThemesButton,{size:"3",title:"Pi Zero",variant:"ghost"},jsx(LucideMicrochip,{css:({ ["color"] : (reflex___state____state__noxuscmmd___state____state.pi_zero_online_rx_state_ ? "#4ade80" : "#64748b") }),size:28},)))
  )
}


function Button_85a0ea8a5e1bf0098d97666f7a18916e () {
  const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_click_983791d062a83993c12a0a20d359df59 = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.noxuscmmd___state____state.accion_apagar", ({ ["device_key"] : "pi_zero" }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(RadixThemesButton,{color:"red",css:({ ["width"] : "100%" }),onClick:on_click_983791d062a83993c12a0a20d359df59,size:"2",variant:"surface"},jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",direction:"row",gap:"3"},jsx(LucidePowerOff,{size:16},),jsx(RadixThemesText,{as:"p",size:"2"},"Apagar")))
  )
}


function Button_d4158f9dcf354c81ce50ab35b83033dd () {
  const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_click_e73054565f10a210788489bc62cbdbf2 = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.noxuscmmd___state____state.accion_reiniciar", ({ ["device_key"] : "pi_zero" }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(RadixThemesButton,{color:"orange",css:({ ["width"] : "100%" }),onClick:on_click_e73054565f10a210788489bc62cbdbf2,size:"2",variant:"surface"},jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",direction:"row",gap:"3"},jsx(LucideRefreshCw,{size:16},),jsx(RadixThemesText,{as:"p",size:"2"},"Reiniciar")))
  )
}


function Button_9c1cf15786ed833697e94dafe73b2385 () {
  const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_click_142ed80ad7debfd14283a4f31bfe1f7d = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.noxuscmmd___state____state.accion_temperatura", ({ ["device_key"] : "pi_zero" }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(RadixThemesButton,{color:"blue",css:({ ["width"] : "100%" }),onClick:on_click_142ed80ad7debfd14283a4f31bfe1f7d,size:"2",variant:"surface"},jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",direction:"row",gap:"3"},jsx(LucideThermometer,{size:16},),jsx(RadixThemesText,{as:"p",size:"2"},"Temperatura")))
  )
}


function Button_4b17f9acb95f5093f50f611d83069276 () {
  const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_click_5d89d46f2d6b460b5d6083241feb5569 = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.noxuscmmd___state____state.tomar_foto_raspberry", ({  }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(RadixThemesButton,{color:"purple",css:({ ["width"] : "100%" }),onClick:on_click_5d89d46f2d6b460b5d6083241feb5569,size:"2",variant:"surface"},jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",direction:"row",gap:"3"},jsx(LucideStar,{size:16},),jsx(RadixThemesText,{as:"p",size:"2"},"Capturar Foto")))
  )
}


function Debounceinput_7144ebc5a62e510825c4d06a7dfd3f2d () {
  const reflex___state____state__noxuscmmd___state____state = useContext(StateContexts.reflex___state____state__noxuscmmd___state____state)
const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_change_d372350ecf3b50b1b98d4400d66837f0 = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.noxuscmmd___state____state.set_custom_command", ({ ["device_key"] : "pi_zero", ["value"] : _e?.["target"]?.["value"] }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(DebounceInput,{css:({ ["width"] : "150px" }),debounceTimeout:300,element:RadixThemesTextField.Root,onChange:on_change_d372350ecf3b50b1b98d4400d66837f0,placeholder:"ls -la",size:"1",value:(isNotNullOrUndefined((isTrue(reflex___state____state__noxuscmmd___state____state.custom_command_rx_state_?.["pi_zero"]) ? reflex___state____state__noxuscmmd___state____state.custom_command_rx_state_?.["pi_zero"] : "")) ? (isTrue(reflex___state____state__noxuscmmd___state____state.custom_command_rx_state_?.["pi_zero"]) ? reflex___state____state__noxuscmmd___state____state.custom_command_rx_state_?.["pi_zero"] : "") : "")},)
  )
}


function Button_0e3d554822f998fb740aebaecca6957c () {
  const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_click_1f75957201f1cf945314af7342d88cb2 = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.noxuscmmd___state____state.ejecutar_comando_personalizado", ({ ["device_key"] : "pi_zero" }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(RadixThemesButton,{onClick:on_click_1f75957201f1cf945314af7342d88cb2,size:"1"},"Enviar")
  )
}


function Code_814eb1194759acdb4ddd79c30a9b2149 () {
  const reflex___state____state__noxuscmmd___state____state = useContext(StateContexts.reflex___state____state__noxuscmmd___state____state)



  return (
    jsx(RadixThemesCode,{css:({ ["language"] : "bash", ["width"] : "100%" })},(isTrue(reflex___state____state__noxuscmmd___state____state.custom_output_rx_state_?.["pi_zero"]) ? reflex___state____state__noxuscmmd___state____state.custom_output_rx_state_?.["pi_zero"] : ""))
  )
}


function Fragment_7db6b5037693c19634bfc997f396839d () {
  const reflex___state____state__noxuscmmd___state____state = useContext(StateContexts.reflex___state____state__noxuscmmd___state____state)



  return (
    jsx(Fragment,{},(!(((isTrue(reflex___state____state__noxuscmmd___state____state.custom_output_rx_state_?.["pi_zero"]) ? reflex___state____state__noxuscmmd___state____state.custom_output_rx_state_?.["pi_zero"] : "")?.valueOf?.() === ""?.valueOf?.()))?(jsx(Fragment,{},jsx(RadixThemesBox,{css:({ ["width"] : "100%", ["maxHeight"] : "150px", ["overflowY"] : "auto", ["background"] : "#1a1a1a", ["padding"] : "8px", ["borderRadius"] : "4px" })},jsx(Code_814eb1194759acdb4ddd79c30a9b2149,{},)))):(jsx(Fragment,{},))))
  )
}


function Text_d7d51ebff63a56b28318d1c5a56f7e4d () {
  const reflex___state____state__noxuscmmd___state____state = useContext(StateContexts.reflex___state____state__noxuscmmd___state____state)



  return (
    jsx(RadixThemesText,{as:"p",css:({ ["color"] : "#94a3b8", ["italic"] : true }),size:"2"},reflex___state____state__noxuscmmd___state____state.status_rx_state_)
  )
}


function Box_a0968e21994258c3e93c052634fbe866 () {
  const reflex___state____state__noxuscmmd___state____state = useContext(StateContexts.reflex___state____state__noxuscmmd___state____state)



  return (
    jsx(RadixThemesBox,{css:({ ["width"] : "100%", ["textAlign"] : "center", ["paddingTop"] : "1em" })},jsx(Text_d7d51ebff63a56b28318d1c5a56f7e4d,{},),Array.prototype.map.call(reflex___state____state__noxuscmmd___state____state.temperaturas_rx_state_ ?? [],((t_rx_state_,index_c25cb9fedab8bc3683d1f3268048e332)=>(jsx(RadixThemesText,{as:"p",css:({ ["color"] : "orange.200", ["fontSize"] : "2" }),key:index_c25cb9fedab8bc3683d1f3268048e332},t_rx_state_)))))
  )
}


function Text_009720a8e415212a64925f6b827e964e () {
  const reflex___state____state__noxuscmmd___state____state = useContext(StateContexts.reflex___state____state__noxuscmmd___state____state)



  return (
    jsx(RadixThemesText,{as:"p",css:({ ["color"] : "gray", ["truncate"] : true }),size:"1"},("URL: "+reflex___state____state__noxuscmmd___state____state.url_fija_stream_rx_state_))
  )
}


function Button_775f0c7103c08aa341a0a8d752d9d015 () {
  const reflex___state____state__noxuscmmd___state____state = useContext(StateContexts.reflex___state____state__noxuscmmd___state____state)
const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_click_0d9f5173a32691eaf136a6a47364923b = useCallback(((_e) => (addEvents([(ReflexEvent("_call_script", ({ ["javascript_code"] : ("window.open('"+reflex___state____state__noxuscmmd___state____state.url_fija_stream_rx_state_+"', '_blank')"), ["callback"] : null }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent, reflex___state____state__noxuscmmd___state____state])

  return (
    jsx(RadixThemesButton,{color:"green",onClick:on_click_0d9f5173a32691eaf136a6a47364923b,size:"2",variant:"solid"},"\ud83d\udcfa Abrir en navegador")
  )
}


function Fragment_88538a4c16f4a7b16aaea86fd3a17b46 () {
  const reflex___state____state__noxuscmmd___state____state = useContext(StateContexts.reflex___state____state__noxuscmmd___state____state)



  return (
    jsx(Fragment,{},((reflex___state____state__noxuscmmd___state____state.cam_mode_rx_state_?.valueOf?.() === "mobile"?.valueOf?.())?(jsx(Fragment,{},jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",css:({ ["width"] : "100%" }),direction:"column",gap:"3"},jsx(RadixThemesText,{as:"p",css:({ ["color"] : "gray" }),size:"1"},"Modo m\u00f3vil: usa el reproductor nativo si no se ve."),jsx(RadixThemesBox,{css:({ ["width"] : "100%", ["aspectRatio"] : "16 / 9", ["borderRadius"] : "8px", ["background"] : "#000", ["overflow"] : "hidden" })},jsx(Iframe_b53914305b29756db0ab6667df718368,{},)),jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",css:({ ["width"] : "100%" }),direction:"row",gap:"2"},jsx(Button_a397f95e192af40e10d13c7a5f34fab8,{},),jsx(Button_775f0c7103c08aa341a0a8d752d9d015,{},))))):(jsx(Fragment,{},jsx(RadixThemesBox,{css:({ ["width"] : "100%", ["aspectRatio"] : "16 / 9", ["borderRadius"] : "8px", ["background"] : "#000", ["overflow"] : "hidden" })},jsx(Iframe_b53914305b29756db0ab6667df718368,{},))))))
  )
}


function Switch_2aee2f2703dc54737e9a84734446ad27 () {
  const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_change_40b7a06944820ba066415980d4b25390 = useCallback(((_ev_0) => (addEvents([(ReflexEvent("reflex___state____state.noxuscmmd___state____state.toggle_privacy", ({ ["device_id"] : "bfc560d51d22c6a73d9khg", ["enable"] : _ev_0 }), ({  })))], [_ev_0], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(RadixThemesSwitch,{onCheckedChange:on_change_40b7a06944820ba066415980d4b25390},)
  )
}


function Button_7b7d3a9da8c7b37ca050dd35f7ef7429 () {
  const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_click_e9b5bf090bc97268e88cb73ecdd13e4a = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.noxuscmmd___state____state.toggle_fija_stream", ({  }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(RadixThemesButton,{css:({ ["width"] : "100%" }),onClick:on_click_e9b5bf090bc97268e88cb73ecdd13e4a,size:"2",variant:"ghost"},"CERRAR")
  )
}


function Dialog__root_369d1cc74fe32176dc8859a183da5fee () {
  const reflex___state____state__noxuscmmd___state____state = useContext(StateContexts.reflex___state____state__noxuscmmd___state____state)



  return (
    jsx(RadixThemesDialog.Root,{open:reflex___state____state__noxuscmmd___state____state.show_fija_stream_rx_state_},jsx(RadixThemesDialog.Trigger,{},jsx(RadixThemesBox,{},)),jsx(RadixThemesDialog.Content,{css:({ ["maxWidth"] : "800px", ["background"] : "#0f172a", ["padding"] : "20px" })},jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",css:({ ["width"] : "100%" }),direction:"column",gap:"3"},jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",direction:"row",gap:"3"},jsx(RadixThemesText,{as:"p",size:"3",weight:"bold"},"C\u00e1mara Fija"),jsx(RadixThemesFlex,{css:({ ["flex"] : 1, ["justifySelf"] : "stretch", ["alignSelf"] : "stretch" })},),jsx(Badge_71e9a74001b2b3cb765f1218d44c7c03,{},),jsx(Button_13d098fee24bcb1de97f8df2b2c719b9,{},)),jsx(Text_009720a8e415212a64925f6b827e964e,{},),jsx(Fragment_88538a4c16f4a7b16aaea86fd3a17b46,{},),jsx(RadixThemesSeparator,{size:"4"},),jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",css:({ ["width"] : "100%" }),direction:"row",gap:"3"},jsx(RadixThemesText,{as:"p",size:"2"},"\ud83d\udd12 Modo privacidad:"),jsx(Switch_2aee2f2703dc54737e9a84734446ad27,{},)),jsx(Button_7b7d3a9da8c7b37ca050dd35f7ef7429,{},))))
  )
}


function Text_90f6f87c384955f80e32d2c4e9bdadf5 () {
  const reflex___state____state__noxuscmmd___state____state = useContext(StateContexts.reflex___state____state__noxuscmmd___state____state)



  return (
    jsx(RadixThemesText,{as:"p",css:({ ["color"] : "gray", ["truncate"] : true }),size:"1"},("URL: "+reflex___state____state__noxuscmmd___state____state.url_ptz_stream_rx_state_))
  )
}


function Button_84eb31b246d33b4ee35ef84ef7c4cbc6 () {
  const reflex___state____state__noxuscmmd___state____state = useContext(StateContexts.reflex___state____state__noxuscmmd___state____state)
const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_click_95c0ad2101d016c714007d89b4ead496 = useCallback(((_e) => (addEvents([(ReflexEvent("_call_script", ({ ["javascript_code"] : ("window.open('"+reflex___state____state__noxuscmmd___state____state.url_ptz_stream_rx_state_+"', '_blank')"), ["callback"] : null }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent, reflex___state____state__noxuscmmd___state____state])

  return (
    jsx(RadixThemesButton,{color:"green",onClick:on_click_95c0ad2101d016c714007d89b4ead496,size:"2",variant:"solid"},"\ud83d\udcfa Abrir en navegador")
  )
}


function Fragment_f79e80055f8506e74aae4bb3056e8a5e () {
  const reflex___state____state__noxuscmmd___state____state = useContext(StateContexts.reflex___state____state__noxuscmmd___state____state)



  return (
    jsx(Fragment,{},((reflex___state____state__noxuscmmd___state____state.cam_mode_rx_state_?.valueOf?.() === "mobile"?.valueOf?.())?(jsx(Fragment,{},jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",css:({ ["width"] : "100%" }),direction:"column",gap:"3"},jsx(RadixThemesText,{as:"p",css:({ ["color"] : "gray" }),size:"1"},"Modo m\u00f3vil: usa el reproductor nativo si no se ve."),jsx(RadixThemesBox,{css:({ ["width"] : "100%", ["aspectRatio"] : "16 / 9", ["borderRadius"] : "8px", ["background"] : "#000", ["overflow"] : "hidden" })},jsx(Iframe_222959a15c6cbea95102493c53b504ae,{},)),jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",css:({ ["width"] : "100%" }),direction:"row",gap:"2"},jsx(Button_a397f95e192af40e10d13c7a5f34fab8,{},),jsx(Button_84eb31b246d33b4ee35ef84ef7c4cbc6,{},))))):(jsx(Fragment,{},jsx(RadixThemesBox,{css:({ ["width"] : "100%", ["aspectRatio"] : "16 / 9", ["borderRadius"] : "8px", ["background"] : "#000", ["overflow"] : "hidden" })},jsx(Iframe_222959a15c6cbea95102493c53b504ae,{},))))))
  )
}


function Switch_8611ec006aefae8ca5014a1e71ac89e4 () {
  const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_change_b34d1c3148047e2083cf2e744bdd03c3 = useCallback(((_ev_0) => (addEvents([(ReflexEvent("reflex___state____state.noxuscmmd___state____state.toggle_privacy", ({ ["device_id"] : "bf5b184f7dd3d48c45avop", ["enable"] : _ev_0 }), ({  })))], [_ev_0], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(RadixThemesSwitch,{onCheckedChange:on_change_b34d1c3148047e2083cf2e744bdd03c3},)
  )
}


function Button_002c9cf59f98a2778b5fb2392540ad88 () {
  const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_click_db7b96222ed8fe4cce67700705f06d70 = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.noxuscmmd___state____state.toggle_ptz_stream", ({  }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(RadixThemesButton,{css:({ ["width"] : "100%" }),onClick:on_click_db7b96222ed8fe4cce67700705f06d70,size:"2",variant:"ghost"},"CERRAR")
  )
}


function Dialog__root_a88eef067660f5ed30d5b66ff125450a () {
  const reflex___state____state__noxuscmmd___state____state = useContext(StateContexts.reflex___state____state__noxuscmmd___state____state)



  return (
    jsx(RadixThemesDialog.Root,{open:reflex___state____state__noxuscmmd___state____state.show_ptz_stream_rx_state_},jsx(RadixThemesDialog.Trigger,{},jsx(RadixThemesBox,{},)),jsx(RadixThemesDialog.Content,{css:({ ["maxWidth"] : "800px", ["background"] : "#0f172a", ["padding"] : "20px" })},jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",css:({ ["width"] : "100%" }),direction:"column",gap:"3"},jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",direction:"row",gap:"3"},jsx(RadixThemesText,{as:"p",size:"3",weight:"bold"},"C\u00e1mara PTZ"),jsx(RadixThemesFlex,{css:({ ["flex"] : 1, ["justifySelf"] : "stretch", ["alignSelf"] : "stretch" })},),jsx(Badge_71e9a74001b2b3cb765f1218d44c7c03,{},),jsx(Button_13d098fee24bcb1de97f8df2b2c719b9,{},)),jsx(Text_90f6f87c384955f80e32d2c4e9bdadf5,{},),jsx(Fragment_f79e80055f8506e74aae4bb3056e8a5e,{},),jsx(RadixThemesSeparator,{size:"4"},),jsx(RadixThemesText,{as:"p",size:"2",weight:"bold"},"\ud83c\udfae Control PTZ:"),jsx(RadixThemesGrid,{columns:"3",css:({ ["width"] : "100%" }),justify:"center",gap:"1"},jsx(RadixThemesBox,{},),jsx(Button_cfb7c0dc3db1f366d309143cfc793645,{},),jsx(RadixThemesBox,{},),jsx(Button_bcb4fa1b3209c320edc5ea6d0901bdd8,{},),jsx(Button_ce8938bada235488ecdaa7adc0c3279b,{},),jsx(Button_2747309f36bc9b7a24274549c2c850c2,{},),jsx(RadixThemesBox,{},),jsx(Button_de8c4a731c4b018ce8f7caf8325f48e1,{},),jsx(RadixThemesBox,{},)),jsx(Text_f3ac6b1e71fcb3e1875f4c1124179851,{},),jsx(RadixThemesSeparator,{size:"4"},),jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",css:({ ["width"] : "100%" }),direction:"row",gap:"3"},jsx(RadixThemesText,{as:"p",size:"2"},"\ud83d\udd12 Modo privacidad:"),jsx(Switch_8611ec006aefae8ca5014a1e71ac89e4,{},)),jsx(Button_002c9cf59f98a2778b5fb2392540ad88,{},))))
  )
}


function Img_16aeaa5db9820a322be165c965cff183 () {
  const reflex___state____state__noxuscmmd___state____state = useContext(StateContexts.reflex___state____state__noxuscmmd___state____state)



  return (
    jsx("img",{css:({ ["width"] : "100%" }),src:reflex___state____state__noxuscmmd___state____state.last_rpi_photo_rx_state_},)
  )
}


function Fragment_88e73164b73eae525cc3c27869ff0e46 () {
  const reflex___state____state__noxuscmmd___state____state = useContext(StateContexts.reflex___state____state__noxuscmmd___state____state)



  return (
    jsx(Fragment,{},(!((reflex___state____state__noxuscmmd___state____state.last_rpi_photo_rx_state_?.valueOf?.() === ""?.valueOf?.()))?(jsx(Fragment,{},jsx(Img_16aeaa5db9820a322be165c965cff183,{},))):(jsx(Fragment,{},jsx(RadixThemesText,{as:"p"},"Cargando captura...")))))
  )
}


function Button_b7504af73597d1e51ee8a60f762f24b4 () {
  const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_click_f6321abe8fe610cbad777212ff3bfdcd = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.noxuscmmd___state____state.toggle_dialog", ({  }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(RadixThemesButton,{css:({ ["mt"] : "4" }),onClick:on_click_f6321abe8fe610cbad777212ff3bfdcd},"Cerrar")
  )
}


function Dialog__root_6b05289e16ada28c50453fe6b6ceaff9 () {
  const reflex___state____state__noxuscmmd___state____state = useContext(StateContexts.reflex___state____state__noxuscmmd___state____state)



  return (
    jsx(RadixThemesDialog.Root,{open:reflex___state____state__noxuscmmd___state____state.dialog_foto_abierto_rx_state_},jsx(RadixThemesDialog.Content,{},jsx(RadixThemesDialog.Title,{},"C\u00e1mara Pi Zero"),jsx(Fragment_88e73164b73eae525cc3c27869ff0e46,{},),jsx(RadixThemesDialog.Close,{},jsx(RadixThemesFlex,{},jsx(Button_b7504af73597d1e51ee8a60f762f24b4,{},)))))
  )
}


function Box_f5c2672316e03e4879329dcc42261640 () {
  
                useEffect(() => {
                    ((...args) => (addEvents([(ReflexEvent("reflex___state____state.noxuscmmd___state____state.on_load", ({  }), ({  })))], args, ({  }))))()
                    return () => {
                        
                    }
                }, []);
const [addEvents, connectErrors] = useContext(EventLoopContext);



  return (
    jsx(RadixThemesBox,{css:({ ["minHeight"] : "100vh", ["background"] : "radial-gradient(circle at center, #0f172a 0%, #000000 100%)" })},jsx(RadixThemesBox,{css:({ ["display"] : "none" })},jsx(Moment_429c094c5102ae8d52c7184a8a3a0888,{},)),jsx(RadixThemesFlex,{css:({ ["display"] : "flex", ["alignItems"] : "center", ["justifyContent"] : "center" })},jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",css:({ ["width"] : "100%", ["maxWidth"] : "450px", ["paddingTop"] : "4em", ["paddingBottom"] : "4em", ["paddingInlineStart"] : "1.5em", ["paddingInlineEnd"] : "1.5em" }),direction:"column",gap:"6"},jsx(Button_1bf0f5f0266a2dd2307020c841f3b725,{},),jsx(RadixThemesFlex,{align:"center",className:"rx-Stack",css:({ ["width"] : "100%", ["mb"] : "4" }),direction:"column",justify:"center",gap:"1"},),jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",css:({ ["width"] : "100%" }),direction:"column",gap:"3"},jsx(Card_1392d3f84c8dacff4b72922fdb15e441,{},),jsx(RadixThemesCard,{css:({ ["width"] : "100%", ["background"] : "rgba(255, 255, 255, 0.03)", ["backdropFilter"] : "blur(10px)", ["border"] : "1px solid rgba(255, 255, 255, 0.1)", ["padding"] : "4" })},jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",direction:"column",gap:"3"},jsx(RadixThemesFlex,{align:"center",className:"rx-Stack",css:({ ["width"] : "100%" }),direction:"row",gap:"3"},jsx(LucideVideo,{css:({ ["color"] : "#818cf8" }),size:20},),jsx(RadixThemesHeading,{css:({ ["letterSpacing"] : "0.05em" }),size:"3"},"CCTV"),jsx(RadixThemesFlex,{css:({ ["flex"] : 1, ["justifySelf"] : "stretch", ["alignSelf"] : "stretch" })},),jsx(Flex_1a463b29c822ecd8c3fff73ee95cf1b3,{},),jsx(Flex_0c924e4d22a095fb334c72ace196bf71,{},)))),jsx(RadixThemesFlex,{align:"center",className:"rx-Stack",css:({ ["width"] : "100%", ["px"] : "2", ["pt"] : "2" }),direction:"row",gap:"3"},jsx(LucideActivity,{css:({ ["color"] : "#38bdf8" }),size:20},),jsx(RadixThemesHeading,{css:({ ["letterSpacing"] : "0.05em" }),size:"3"},"INFRAESTRUCTURA"),jsx(RadixThemesFlex,{css:({ ["flex"] : 1, ["justifySelf"] : "stretch", ["alignSelf"] : "stretch" })},)),jsx(RadixThemesCard,{css:({ ["width"] : "100%", ["background"] : "rgba(255, 255, 255, 0.03)", ["backdropFilter"] : "blur(10px)", ["border"] : "1px solid rgba(255, 255, 255, 0.1)", ["padding"] : "4" })},jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",css:({ ["width"] : "100%" }),direction:"column",gap:"2"},jsx(RadixThemesFlex,{align:"center",className:"rx-Stack",css:({ ["width"] : "100%" }),direction:"row",gap:"3"},jsx(Network_3b6f19d448aaa99f005c5af690acbfbc,{},),jsx(RadixThemesText,{as:"p",weight:"medium"},"Servidor"),jsx(RadixThemesFlex,{css:({ ["flex"] : 1, ["justifySelf"] : "stretch", ["alignSelf"] : "stretch" })},),jsx(RadixThemesFlex,{align:"center",className:"rx-Stack",direction:"row",gap:"2"},jsx(Text_7e51451ee8b539e6b71d46b64e1e8fac,{},),jsx(Text_81938da8cf018dc8c036ae8494a85481,{},),jsx(RadixThemesText,{as:"p",css:({ ["color"] : "gray.300", ["whiteSpace"] : "nowrap" }),size:"2"},"100.98.98.1"))),jsx(RadixThemesPopover.Root,{},jsx(Popover__trigger_8ed1217c5198f66ce20c0f7030913f47,{},),jsx(RadixThemesPopover.Content,{css:({ ["padding"] : "0", ["margin"] : "0", ["boxShadow"] : "none", ["border"] : "none", ["minWidth"] : "auto", ["minHeight"] : "auto" })},jsx(Button_3c28cddf3ccbb95b4d59b05334ae6048,{},))),jsx(RadixThemesPopover.Root,{},jsx(Popover__trigger_8fc52d5406c3c1e6aaf473ac65d2aec2,{},),jsx(RadixThemesPopover.Content,{css:({ ["padding"] : "0", ["margin"] : "0", ["boxShadow"] : "none", ["border"] : "none", ["minWidth"] : "auto", ["minHeight"] : "auto" })},jsx(Button_e38cc380e60d5cb13fd98507104dea0c,{},))),jsx(RadixThemesPopover.Root,{},jsx(Popover__trigger_5dcb7f6f6ca42f80fc5eee3db78cb130,{},),jsx(RadixThemesPopover.Content,{css:({ ["padding"] : "0", ["margin"] : "0", ["boxShadow"] : "none", ["border"] : "none", ["minWidth"] : "auto", ["minHeight"] : "auto" })},jsx(Button_0bf533ffbd377012bbb9187c2d625a83,{},))),jsx(RadixThemesFlex,{align:"center",className:"rx-Stack",css:({ ["width"] : "100%" }),direction:"row",gap:"3"},jsx(Microchip_517fc6202f1dc12b9752095c3324464f,{},),jsx(RadixThemesText,{as:"p",weight:"medium"},"Pi Zero"),jsx(RadixThemesFlex,{css:({ ["flex"] : 1, ["justifySelf"] : "stretch", ["alignSelf"] : "stretch" })},),jsx(RadixThemesFlex,{align:"center",className:"rx-Stack",direction:"row",gap:"2"},jsx(Text_5bd62279cc0239c5ad3ffce6da7a071d,{},),jsx(Text_0cca01f0eafe464b9fb47832c9162412,{},),jsx(RadixThemesText,{as:"p",css:({ ["color"] : "gray.300", ["whiteSpace"] : "nowrap" }),size:"2"},"100.98.98.5"))),jsx(RadixThemesFlex,{align:"center",className:"rx-Stack",css:({ ["width"] : "100%" }),direction:"row",gap:"3"},jsx(Smartphone_8fcd377e0c3148594b587b5c70046364,{},),jsx(RadixThemesText,{as:"p",weight:"medium"},"iPhone"),jsx(RadixThemesFlex,{css:({ ["flex"] : 1, ["justifySelf"] : "stretch", ["alignSelf"] : "stretch" })},),jsx(RadixThemesFlex,{align:"center",className:"rx-Stack",direction:"row",gap:"2"},jsx(Text_8d06d72142637555e74fcd7b9adf1a49,{},),jsx(Text_e729cc855521ca75a7c17dcf6ba18173,{},),jsx(RadixThemesText,{as:"p",css:({ ["color"] : "gray.300", ["whiteSpace"] : "nowrap" }),size:"2"},"100.98.98.6"))),jsx(RadixThemesFlex,{align:"center",className:"rx-Stack",css:({ ["width"] : "100%" }),direction:"row",gap:"3"},jsx(Tablet_e54126ee30779eadeef551eff4854f5c,{},),jsx(RadixThemesText,{as:"p",weight:"medium"},"Tablet"),jsx(RadixThemesFlex,{css:({ ["flex"] : 1, ["justifySelf"] : "stretch", ["alignSelf"] : "stretch" })},),jsx(RadixThemesFlex,{align:"center",className:"rx-Stack",direction:"row",gap:"2"},jsx(Text_ad256b825972f849c7dec0a1f19cfdc5,{},),jsx(Text_af01df48bd18ef0ef496fa59d2c0a432,{},),jsx(RadixThemesText,{as:"p",css:({ ["color"] : "gray.300", ["whiteSpace"] : "nowrap" }),size:"2"},"100.98.98.7")))))),jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",css:({ ["width"] : "100%" }),direction:"column",gap:"3"},jsx(RadixThemesFlex,{align:"center",className:"rx-Stack",css:({ ["width"] : "100%" }),direction:"row",gap:"3"},jsx(LucideCpu,{css:({ ["color"] : "#38bdf8" }),size:20},),jsx(RadixThemesHeading,{css:({ ["letterSpacing"] : "0.05em" }),size:"3"},"CONTROL POR EQUIPO")),jsx(RadixThemesSeparator,{css:({ ["opacity"] : "0.1" }),size:"4"},),jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",css:({ ["width"] : "100%" }),direction:"row",justify:"between",gap:"4"},jsx(RadixThemesPopover.Root,{},jsx(Popover__trigger_5dfab2a2601a2f5dcfbc3ece3ab2a887,{},),jsx(RadixThemesPopover.Content,{},jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",css:({ ["width"] : "250px" }),direction:"column",gap:"2"},jsx(Button_6ed95d9b240756108db4873d58032614,{},),jsx(Button_f11c4b7eefd92199c26340feca21833b,{},),jsx(Button_c0b86d7d16d880825fa9b7aca7534fc4,{},),jsx(Fragment,{},(false?(jsx(Fragment,{},jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",css:({ ["width"] : "100%" }),direction:"column",gap:"2"},jsx(RadixThemesSeparator,{size:"4"},),jsx(RadixThemesText,{as:"p",size:"1",weight:"bold"},"\ud83c\udfa5 CONTROL PTZ"),jsx(RadixThemesGrid,{columns:"3",css:({ ["width"] : "100%" }),justify:"center",gap:"1"},jsx(RadixThemesBox,{},),jsx(Button_cfb7c0dc3db1f366d309143cfc793645,{},),jsx(RadixThemesBox,{},),jsx(Button_bcb4fa1b3209c320edc5ea6d0901bdd8,{},),jsx(Button_ce8938bada235488ecdaa7adc0c3279b,{},),jsx(Button_2747309f36bc9b7a24274549c2c850c2,{},),jsx(RadixThemesBox,{},),jsx(Button_de8c4a731c4b018ce8f7caf8325f48e1,{},),jsx(RadixThemesBox,{},)),jsx(Text_f3ac6b1e71fcb3e1875f4c1124179851,{},),jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",direction:"row",gap:"2"},jsx(RadixThemesText,{as:"p",size:"1"},"\ud83d\udd12 Privacidad:"),jsx(Switch_351e774a3f5408ef6b62c3ff767950f3,{},))))):(jsx(Fragment,{},)))),jsx(Fragment,{},(false?(jsx(Fragment,{},jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",css:({ ["width"] : "100%" }),direction:"column",gap:"2"},jsx(RadixThemesSeparator,{size:"4"},),jsx(RadixThemesText,{as:"p",size:"1",weight:"bold"},"\ud83d\udcf7 C\u00c1MARA FIJA"),jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",direction:"row",gap:"2"},jsx(RadixThemesText,{as:"p",size:"1"},"\ud83d\udd12 Privacidad:"),jsx(Switch_8660adb7ce8bc363fb963cc43e3eb67c,{},))))):(jsx(Fragment,{},)))),jsx(RadixThemesSeparator,{size:"4"},),jsx(RadixThemesText,{as:"p",size:"1",weight:"bold"},"Comando SSH:"),jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",direction:"row",gap:"2"},jsx(Debounceinput_a84c72c6259092d41309430ac658c731,{},),jsx(Button_c7472fa5185ea34e01843530b6f49296,{},)),jsx(Fragment_3c43efab4e47b1d428f2286494b023f6,{},)))),jsx(RadixThemesPopover.Root,{},jsx(Popover__trigger_51fdda2291ac772fef62563aaeff3a0b,{},),jsx(RadixThemesPopover.Content,{},jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",css:({ ["width"] : "250px" }),direction:"column",gap:"2"},jsx(Button_310038ddfebb0f44143ccaae80d2bac7,{},),jsx(Button_070b922c537de1b0d4bce2a71126e979,{},),jsx(Button_ce52b76f300a58b9e7b39b4b6a1c1a9d,{},),jsx(Button_65f4c70b694db59097c14e51da2fa530,{},),jsx(Button_c36c2d714823a648d88b55639160b45d,{},),jsx(Fragment,{},(false?(jsx(Fragment,{},jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",css:({ ["width"] : "100%" }),direction:"column",gap:"2"},jsx(RadixThemesSeparator,{size:"4"},),jsx(RadixThemesText,{as:"p",size:"1",weight:"bold"},"\ud83c\udfa5 CONTROL PTZ"),jsx(RadixThemesGrid,{columns:"3",css:({ ["width"] : "100%" }),justify:"center",gap:"1"},jsx(RadixThemesBox,{},),jsx(Button_cfb7c0dc3db1f366d309143cfc793645,{},),jsx(RadixThemesBox,{},),jsx(Button_bcb4fa1b3209c320edc5ea6d0901bdd8,{},),jsx(Button_ce8938bada235488ecdaa7adc0c3279b,{},),jsx(Button_2747309f36bc9b7a24274549c2c850c2,{},),jsx(RadixThemesBox,{},),jsx(Button_de8c4a731c4b018ce8f7caf8325f48e1,{},),jsx(RadixThemesBox,{},)),jsx(Text_f3ac6b1e71fcb3e1875f4c1124179851,{},),jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",direction:"row",gap:"2"},jsx(RadixThemesText,{as:"p",size:"1"},"\ud83d\udd12 Privacidad:"),jsx(Switch_351e774a3f5408ef6b62c3ff767950f3,{},))))):(jsx(Fragment,{},)))),jsx(Fragment,{},(false?(jsx(Fragment,{},jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",css:({ ["width"] : "100%" }),direction:"column",gap:"2"},jsx(RadixThemesSeparator,{size:"4"},),jsx(RadixThemesText,{as:"p",size:"1",weight:"bold"},"\ud83d\udcf7 C\u00c1MARA FIJA"),jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",direction:"row",gap:"2"},jsx(RadixThemesText,{as:"p",size:"1"},"\ud83d\udd12 Privacidad:"),jsx(Switch_8660adb7ce8bc363fb963cc43e3eb67c,{},))))):(jsx(Fragment,{},)))),jsx(RadixThemesSeparator,{size:"4"},),jsx(RadixThemesText,{as:"p",size:"1",weight:"bold"},"Comando SSH:"),jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",direction:"row",gap:"2"},jsx(Debounceinput_f001d15bafbbbe05ef46731bf9581fbb,{},),jsx(Button_86b5b99b7c1ea301c758f79396e978a4,{},)),jsx(Fragment_6e45bd8c265dacce9a47d5b361bcee03,{},)))),jsx(RadixThemesPopover.Root,{},jsx(Popover__trigger_444090a467eb5f3bb14e826a4b87198d,{},),jsx(RadixThemesPopover.Content,{},jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",css:({ ["width"] : "250px" }),direction:"column",gap:"2"},jsx(Button_90238aa155f0a2e07636e4f6b35ae40a,{},),jsx(Button_93f1954b6197a1b5ab93b6c21bb1b07d,{},),jsx(Button_277299bb39fef251727834f1c456401e,{},),jsx(Button_d02b738b29ac68fc7321f42cb1a8fb65,{},),jsx(Fragment,{},(false?(jsx(Fragment,{},jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",css:({ ["width"] : "100%" }),direction:"column",gap:"2"},jsx(RadixThemesSeparator,{size:"4"},),jsx(RadixThemesText,{as:"p",size:"1",weight:"bold"},"\ud83c\udfa5 CONTROL PTZ"),jsx(RadixThemesGrid,{columns:"3",css:({ ["width"] : "100%" }),justify:"center",gap:"1"},jsx(RadixThemesBox,{},),jsx(Button_cfb7c0dc3db1f366d309143cfc793645,{},),jsx(RadixThemesBox,{},),jsx(Button_bcb4fa1b3209c320edc5ea6d0901bdd8,{},),jsx(Button_ce8938bada235488ecdaa7adc0c3279b,{},),jsx(Button_2747309f36bc9b7a24274549c2c850c2,{},),jsx(RadixThemesBox,{},),jsx(Button_de8c4a731c4b018ce8f7caf8325f48e1,{},),jsx(RadixThemesBox,{},)),jsx(Text_f3ac6b1e71fcb3e1875f4c1124179851,{},),jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",direction:"row",gap:"2"},jsx(RadixThemesText,{as:"p",size:"1"},"\ud83d\udd12 Privacidad:"),jsx(Switch_351e774a3f5408ef6b62c3ff767950f3,{},))))):(jsx(Fragment,{},)))),jsx(Fragment,{},(false?(jsx(Fragment,{},jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",css:({ ["width"] : "100%" }),direction:"column",gap:"2"},jsx(RadixThemesSeparator,{size:"4"},),jsx(RadixThemesText,{as:"p",size:"1",weight:"bold"},"\ud83d\udcf7 C\u00c1MARA FIJA"),jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",direction:"row",gap:"2"},jsx(RadixThemesText,{as:"p",size:"1"},"\ud83d\udd12 Privacidad:"),jsx(Switch_8660adb7ce8bc363fb963cc43e3eb67c,{},))))):(jsx(Fragment,{},)))),jsx(RadixThemesSeparator,{size:"4"},),jsx(RadixThemesText,{as:"p",size:"1",weight:"bold"},"Comando SSH:"),jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",direction:"row",gap:"2"},jsx(Debounceinput_e2bb32741d05bae98ba4e627ce5ad120,{},),jsx(Button_d5d5a27d36c21df7b3862c3f176ade26,{},)),jsx(Fragment_390726caad2235dd0c9f52b2dd5e1bcb,{},)))),jsx(RadixThemesPopover.Root,{},jsx(Popover__trigger_b1cdfe01dea1a0a2ecdbaaf079109d98,{},),jsx(RadixThemesPopover.Content,{},jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",css:({ ["width"] : "250px" }),direction:"column",gap:"2"},jsx(Button_9d9c7bdf032a2a3fec83106fb6001da9,{},),jsx(Button_9a12dfa3390b160a2a7fe6cfad01a545,{},),jsx(Button_1225e323dd80622b62605bbd3b27e6d7,{},),jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",direction:"row",gap:"2"},jsx(RadixThemesText,{as:"p",css:({ ["width"] : "80px" }),size:"1"},"GPIO17 (Ventilador)"),jsx(Button_1339dec2cb5520e5e9850e4a9f1544c5,{},),jsx(Button_9863869f2c0ef74ce9c0add6e682ae76,{},)),jsx(Button_275183e2baefb3074fcdeb20d8fb92b6,{},),jsx(Button_63aa688472d2bf433c194b1034848c51,{},),jsx(Button_055952fc777b3f8e12a4f403afb9c14c,{},),jsx(Fragment,{},(true?(jsx(Fragment,{},jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",css:({ ["width"] : "100%" }),direction:"column",gap:"2"},jsx(RadixThemesSeparator,{size:"4"},),jsx(RadixThemesText,{as:"p",size:"1",weight:"bold"},"\ud83c\udfa5 CONTROL PTZ"),jsx(RadixThemesGrid,{columns:"3",css:({ ["width"] : "100%" }),justify:"center",gap:"1"},jsx(RadixThemesBox,{},),jsx(Button_cfb7c0dc3db1f366d309143cfc793645,{},),jsx(RadixThemesBox,{},),jsx(Button_bcb4fa1b3209c320edc5ea6d0901bdd8,{},),jsx(Button_ce8938bada235488ecdaa7adc0c3279b,{},),jsx(Button_2747309f36bc9b7a24274549c2c850c2,{},),jsx(RadixThemesBox,{},),jsx(Button_de8c4a731c4b018ce8f7caf8325f48e1,{},),jsx(RadixThemesBox,{},)),jsx(Text_f3ac6b1e71fcb3e1875f4c1124179851,{},),jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",direction:"row",gap:"2"},jsx(RadixThemesText,{as:"p",size:"1"},"\ud83d\udd12 Privacidad:"),jsx(Switch_351e774a3f5408ef6b62c3ff767950f3,{},))))):(jsx(Fragment,{},)))),jsx(Fragment,{},(false?(jsx(Fragment,{},jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",css:({ ["width"] : "100%" }),direction:"column",gap:"2"},jsx(RadixThemesSeparator,{size:"4"},),jsx(RadixThemesText,{as:"p",size:"1",weight:"bold"},"\ud83d\udcf7 C\u00c1MARA FIJA"),jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",direction:"row",gap:"2"},jsx(RadixThemesText,{as:"p",size:"1"},"\ud83d\udd12 Privacidad:"),jsx(Switch_8660adb7ce8bc363fb963cc43e3eb67c,{},))))):(jsx(Fragment,{},)))),jsx(RadixThemesSeparator,{size:"4"},),jsx(RadixThemesText,{as:"p",size:"1",weight:"bold"},"Comando SSH:"),jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",direction:"row",gap:"2"},jsx(Debounceinput_11e44fdb7cddc7e309e10b373ec84d24,{},),jsx(Button_a293889d2b6c1f6db62511ef78a7c7bc,{},)),jsx(Fragment_4da39fc4814bd1549e1ae720f94e724b,{},)))),jsx(RadixThemesPopover.Root,{},jsx(Popover__trigger_f95cdfcbf16810ed0cb807cc307c5ccd,{},),jsx(RadixThemesPopover.Content,{},jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",css:({ ["width"] : "250px" }),direction:"column",gap:"2"},jsx(Button_85a0ea8a5e1bf0098d97666f7a18916e,{},),jsx(Button_d4158f9dcf354c81ce50ab35b83033dd,{},),jsx(Button_9c1cf15786ed833697e94dafe73b2385,{},),jsx(Button_4b17f9acb95f5093f50f611d83069276,{},),jsx(Fragment,{},(false?(jsx(Fragment,{},jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",css:({ ["width"] : "100%" }),direction:"column",gap:"2"},jsx(RadixThemesSeparator,{size:"4"},),jsx(RadixThemesText,{as:"p",size:"1",weight:"bold"},"\ud83c\udfa5 CONTROL PTZ"),jsx(RadixThemesGrid,{columns:"3",css:({ ["width"] : "100%" }),justify:"center",gap:"1"},jsx(RadixThemesBox,{},),jsx(Button_cfb7c0dc3db1f366d309143cfc793645,{},),jsx(RadixThemesBox,{},),jsx(Button_bcb4fa1b3209c320edc5ea6d0901bdd8,{},),jsx(Button_ce8938bada235488ecdaa7adc0c3279b,{},),jsx(Button_2747309f36bc9b7a24274549c2c850c2,{},),jsx(RadixThemesBox,{},),jsx(Button_de8c4a731c4b018ce8f7caf8325f48e1,{},),jsx(RadixThemesBox,{},)),jsx(Text_f3ac6b1e71fcb3e1875f4c1124179851,{},),jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",direction:"row",gap:"2"},jsx(RadixThemesText,{as:"p",size:"1"},"\ud83d\udd12 Privacidad:"),jsx(Switch_351e774a3f5408ef6b62c3ff767950f3,{},))))):(jsx(Fragment,{},)))),jsx(Fragment,{},(true?(jsx(Fragment,{},jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",css:({ ["width"] : "100%" }),direction:"column",gap:"2"},jsx(RadixThemesSeparator,{size:"4"},),jsx(RadixThemesText,{as:"p",size:"1",weight:"bold"},"\ud83d\udcf7 C\u00c1MARA FIJA"),jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",direction:"row",gap:"2"},jsx(RadixThemesText,{as:"p",size:"1"},"\ud83d\udd12 Privacidad:"),jsx(Switch_8660adb7ce8bc363fb963cc43e3eb67c,{},))))):(jsx(Fragment,{},)))),jsx(RadixThemesSeparator,{size:"4"},),jsx(RadixThemesText,{as:"p",size:"1",weight:"bold"},"Comando SSH:"),jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",direction:"row",gap:"2"},jsx(Debounceinput_7144ebc5a62e510825c4d06a7dfd3f2d,{},),jsx(Button_0e3d554822f998fb740aebaecca6957c,{},)),jsx(Fragment_7db6b5037693c19634bfc997f396839d,{},))))),jsx(RadixThemesSeparator,{css:({ ["opacity"] : "0.2" }),size:"4"},),jsx(Box_a0968e21994258c3e93c052634fbe866,{},)),null,jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",css:({ ["width"] : "100%" }),direction:"column",gap:"0"},jsx(Dialog__root_369d1cc74fe32176dc8859a183da5fee,{},),jsx(Dialog__root_a88eef067660f5ed30d5b66ff125450a,{},)),jsx(Dialog__root_6b05289e16ada28c50453fe6b6ceaff9,{},))))
  )
}


export default function Component() {





  return (
    jsx(Fragment,{},jsx(Box_f5c2672316e03e4879329dcc42261640,{},),jsx("title",{},"Noxus Pro"),jsx("meta",{content:"favicon.ico",property:"og:image"},))
  )
}