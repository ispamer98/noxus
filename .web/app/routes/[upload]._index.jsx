import {Fragment,useCallback,useContext,useEffect,useRef} from "react"
import {Box as RadixThemesBox,Button as RadixThemesButton,Flex as RadixThemesFlex,Heading as RadixThemesHeading} from "@radix-ui/themes"
import {} from "react-dropzone"
import {ReflexEvent,refs} from "$/utils/state"
import {EventLoopContext,UploadFilesContext} from "$/utils/context"
import {useDropzone} from "react-dropzone"
import {jsx} from "@emotion/react"




function Comp_2b98b17f68999b511f81089c47c9de29 () {
  const ref_file_upload = useRef(null); refs["ref_file_upload"] = ref_file_upload;
const [addEvents, connectErrors] = useContext(EventLoopContext);
const [filesById, setFilesById] = useContext(UploadFilesContext);
const on_drop_2c54a888c9dc942f42617dade4e1835d = useCallback(e => setFilesById(filesById => {
    const updatedFilesById = Object.assign({}, filesById);
    updatedFilesById["file_upload"] = e;
    return updatedFilesById;
  })
    , [addEvents, ReflexEvent, filesById, setFilesById])
const on_drop_rejected_2fcedbdc0771e7617b4270e2d1ac8cc9 = useCallback(((_ev_0) => (addEvents([(ReflexEvent("_call_function", ({ ["function"] : (() => (refs['__toast']?.["error"]("", ({ ["title"] : "Files not Accepted", ["description"] : _ev_0.map(((osizayzf) => (osizayzf?.["file"]?.["path"]+": "+osizayzf?.["errors"].map(((wnkiegyk) => wnkiegyk?.["message"])).join(", ")))).join("\n\n"), ["closeButton"] : true, ["style"] : ({ ["whiteSpace"] : "pre-line" }) })))), ["callback"] : null }), ({  })))], [_ev_0], ({  })))), [addEvents, ReflexEvent])
const { getRootProps: xdvxrcsn, getInputProps: udaxihhe, isDragActive: bacghqta} = useDropzone(({ ["multiple"] : true, ["id"] : "file_upload", ["onDrop"] : on_drop_2c54a888c9dc942f42617dade4e1835d, ["onDropRejected"] : on_drop_rejected_2fcedbdc0771e7617b4270e2d1ac8cc9 }));



  return (
    jsx(Fragment,{},jsx(RadixThemesBox,{className:"rx-Upload",css:({ ["border"] : "2px dashed #ccc", ["padding"] : "2em", ["textAlign"] : "center" }),id:"file_upload",ref:ref_file_upload,...xdvxrcsn()},jsx("input",{type:"file",...udaxihhe()},)))
  )
}


function Button_2c8f3c6eed3891842994a0598ffdee47 () {
  const [filesById, setFilesById] = useContext(UploadFilesContext);
const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_click_7d10ab4849d24a968ec5d43797db1a80 = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.noxuscmmd___state____state.handle_upload", ({ ["files"] : filesById?.["file_upload"], ["upload_id"] : "file_upload", ["extra_headers"] : ({  }) }), ({  }), "uploadFiles"))], [_e], ({  })))), [addEvents, ReflexEvent, filesById, setFilesById])

  return (
    jsx(RadixThemesButton,{onClick:on_click_7d10ab4849d24a968ec5d43797db1a80},"Subir")
  )
}


function Button_b2c02a337e6f0cc5b194f630e5986433 () {
  const [addEvents, connectErrors] = useContext(EventLoopContext);

const on_click_8552f88a33a715f92112f009d36a6cf6 = useCallback(((_e) => (addEvents([(ReflexEvent("_redirect", ({ ["path"] : "/", ["external"] : false, ["popup"] : false, ["replace"] : false }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])

  return (
    jsx(RadixThemesButton,{onClick:on_click_8552f88a33a715f92112f009d36a6cf6,variant:"soft"},"Volver")
  )
}


export default function Component() {





  return (
    jsx(Fragment,{},jsx(RadixThemesFlex,{css:({ ["display"] : "flex", ["alignItems"] : "center", ["justifyContent"] : "center" })},jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",direction:"column",gap:"4"},jsx(RadixThemesHeading,{},"Subida de Archivos"),jsx(Comp_2b98b17f68999b511f81089c47c9de29,{},),jsx(Button_2c8f3c6eed3891842994a0598ffdee47,{},),jsx(Button_b2c02a337e6f0cc5b194f630e5986433,{},))),jsx("title",{},"Noxuscmmd | Upload"),jsx("meta",{content:"favicon.ico",property:"og:image"},))
  )
}