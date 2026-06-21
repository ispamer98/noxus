import {Badge as RadixThemesBadge,Button as RadixThemesButton,Switch as RadixThemesSwitch,Text as RadixThemesText} from "@radix-ui/themes"
import {Fragment,useCallback,useContext,useEffect} from "react"
import {EventLoopContext,StateContexts} from "$/utils/context"
import {ReflexEvent} from "$/utils/state"
import {RefreshCw as LucideRefreshCw} from "lucide-react"
import {jsx} from "@emotion/react"

export function Button_cfb7c0dc3db1f366d309143cfc793645 () {
  const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_click_0cee88a49fd82d0fbcb8c7796d33c613 = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.noxuscmmd___state____state.move_ptz", ({ ["direction"] : "0" }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(RadixThemesButton,{onClick:on_click_0cee88a49fd82d0fbcb8c7796d33c613,size:"1",variant:"soft"},"\u2b06")
  )
}


export function Button_bcb4fa1b3209c320edc5ea6d0901bdd8 () {
  const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_click_83cacfcd02df851206a75c4dba98f72f = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.noxuscmmd___state____state.move_ptz", ({ ["direction"] : "6" }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(RadixThemesButton,{onClick:on_click_83cacfcd02df851206a75c4dba98f72f,size:"1",variant:"soft"},"\u2b05")
  )
}


export function Button_ce8938bada235488ecdaa7adc0c3279b () {
  const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_click_9777adc4c694367202f04c6d8e57a4fe = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.noxuscmmd___state____state.move_ptz", ({ ["direction"] : "stop" }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(RadixThemesButton,{color:"red",onClick:on_click_9777adc4c694367202f04c6d8e57a4fe,size:"1",variant:"soft"},"\u23f9")
  )
}


export function Button_2747309f36bc9b7a24274549c2c850c2 () {
  const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_click_25f68a4c0935cdb55b594f69104744c4 = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.noxuscmmd___state____state.move_ptz", ({ ["direction"] : "2" }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(RadixThemesButton,{onClick:on_click_25f68a4c0935cdb55b594f69104744c4,size:"1",variant:"soft"},"\u27a1")
  )
}


export function Button_de8c4a731c4b018ce8f7caf8325f48e1 () {
  const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_click_f781233541818c7cf15696525c6d6dc4 = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.noxuscmmd___state____state.move_ptz", ({ ["direction"] : "4" }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(RadixThemesButton,{onClick:on_click_f781233541818c7cf15696525c6d6dc4,size:"1",variant:"soft"},"\u2b07")
  )
}


export function Text_f3ac6b1e71fcb3e1875f4c1124179851 () {
  const reflex___state____state__noxuscmmd___state____state = useContext(StateContexts.reflex___state____state__noxuscmmd___state____state)



  return (
    jsx(RadixThemesText,{as:"p",css:({ ["color"] : "gray" }),size:"1"},reflex___state____state__noxuscmmd___state____state.cam_msg_rx_state_)
  )
}


export function Switch_351e774a3f5408ef6b62c3ff767950f3 () {
  const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_change_b34d1c3148047e2083cf2e744bdd03c3 = useCallback(((_ev_0) => (addEvents([(ReflexEvent("reflex___state____state.noxuscmmd___state____state.toggle_privacy", ({ ["device_id"] : "bf5b184f7dd3d48c45avop", ["enable"] : _ev_0 }), ({  })))], [_ev_0], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(RadixThemesSwitch,{onCheckedChange:on_change_b34d1c3148047e2083cf2e744bdd03c3,size:"1"},)
  )
}


export function Switch_8660adb7ce8bc363fb963cc43e3eb67c () {
  const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_change_40b7a06944820ba066415980d4b25390 = useCallback(((_ev_0) => (addEvents([(ReflexEvent("reflex___state____state.noxuscmmd___state____state.toggle_privacy", ({ ["device_id"] : "bfc560d51d22c6a73d9khg", ["enable"] : _ev_0 }), ({  })))], [_ev_0], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(RadixThemesSwitch,{onCheckedChange:on_change_40b7a06944820ba066415980d4b25390,size:"1"},)
  )
}


export function Badge_71e9a74001b2b3cb765f1218d44c7c03 () {
  const reflex___state____state__noxuscmmd___state____state = useContext(StateContexts.reflex___state____state__noxuscmmd___state____state)



  return (
    jsx(RadixThemesBadge,{color:((reflex___state____state__noxuscmmd___state____state.cam_mode_rx_state_?.valueOf?.() === "pc"?.valueOf?.()) ? "blue" : "green")},((reflex___state____state__noxuscmmd___state____state.cam_mode_rx_state_?.valueOf?.() === "pc"?.valueOf?.()) ? "MODO PC" : "MODO M\u00d3VIL"))
  )
}


export function Button_13d098fee24bcb1de97f8df2b2c719b9 () {
  const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_click_7e1fca2a5925d1e7b39777269594363c = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.noxuscmmd___state____state.toggle_cam_mode", ({  }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(RadixThemesButton,{onClick:on_click_7e1fca2a5925d1e7b39777269594363c,size:"1",title:"Cambiar entre modo PC y modo M\u00f3vil",variant:"ghost"},jsx(LucideRefreshCw,{size:16},))
  )
}


export function Iframe_b53914305b29756db0ab6667df718368 () {
  const reflex___state____state__noxuscmmd___state____state = useContext(StateContexts.reflex___state____state__noxuscmmd___state____state)



  return (
    jsx("iframe",{allow:"autoplay; fullscreen",css:({ ["width"] : "100%", ["height"] : "100%", ["border"] : "none" }),src:reflex___state____state__noxuscmmd___state____state.url_fija_stream_rx_state_},)
  )
}


export function Button_a397f95e192af40e10d13c7a5f34fab8 () {
  const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_click_7e1fca2a5925d1e7b39777269594363c = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.noxuscmmd___state____state.toggle_cam_mode", ({  }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(RadixThemesButton,{color:"blue",onClick:on_click_7e1fca2a5925d1e7b39777269594363c,size:"2",variant:"soft"},"\ud83d\udcf1 Forzar modo PC")
  )
}


export function Iframe_222959a15c6cbea95102493c53b504ae () {
  const reflex___state____state__noxuscmmd___state____state = useContext(StateContexts.reflex___state____state__noxuscmmd___state____state)



  return (
    jsx("iframe",{allow:"autoplay; fullscreen",css:({ ["width"] : "100%", ["height"] : "100%", ["border"] : "none" }),src:reflex___state____state__noxuscmmd___state____state.url_ptz_stream_rx_state_},)
  )
}
