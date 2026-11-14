-- Exercise the actual Hammerspoon adapter against AX-shaped fixtures.
local function element(role, value, children, subrole)
  local e = {AXRole=role, AXValue=value, AXChildren=children or {}, AXSubrole=subrole}
  function e:attributeValue(k) return self[k] end
  function e:setTimeout(_) return self end
  for _, c in ipairs(e.AXChildren) do c.AXParent=e end
  return e
end
local bundle, wid, focus, screenshot = "com.apple.Terminal", 42, nil, 0
local app = {bundleID=function() return bundle end, pid=function() return 10 end}
local win = {id=function() return wid end, application=function() return app end,
             snapshot=function() screenshot=screenshot+1; return {encodeAsURLString=function() return "PNG" end} end}
local ax = element("AXApplication")
hs = {
  timer={secondsSinceEpoch=function() return 1 end},
  application={frontmostApplication=function() return app end},
  window={focusedWindow=function() return win end},
  accessibilityState=function() return true end,
  screenRecordingState=function() return true end,
  axuielement={applicationElement=function() ax.AXFocusedUIElement=focus; return ax end},
}
local m=dofile("hammerspoon/context.lua")
focus=element("AXTextArea", "Claude: MarzipanQueue\nUser: next step")
assert(m.capture(bundle, "42", true, "").text:find("MarzipanQueue"))
assert(m.capture(bundle, "43", true, "").status == "destination-changed")
assert(m.capture("com.openai.codex", "42", true, "").status == "destination-changed")
focus.AXSubrole="AXSecureTextField"
assert(m.capture(bundle, "42", true, "").status == "secure-field")
bundle="com.example.Passwords"
assert(m.capture("", "", true, "").status == "unsupported-app")
bundle="com.openai.codex"
local composer=element("AXTextArea", "UNSENT DRAFT")
local pane=element("AXGroup", nil, {element("AXStaticText", "User: fix the MarzipanQueue retry behavior please"),
                                  element("AXStaticText", "Assistant: keep the recent request ID"), composer})
local sidebar=element("AXOutline", nil, {element("AXStaticText", "OTHER CHAT SECRET")})
element("AXWindow", nil, {sidebar, pane})
focus=composer
local r=m.capture(bundle, "42", true, "")
assert(r.status == "ok" and r.text:find("MarzipanQueue"))
assert(not r.text:find("OTHER CHAT") and not r.text:find("UNSENT DRAFT"))
assert(screenshot==0)
focus=nil
assert(m.capture(bundle, "42", false, "").status == "no-readable-text")
assert(m.capture(bundle, "42", true, "").status == "ocr-pending")
assert(screenshot==1)
hs.screenRecordingState=function() return false end
assert(m.capture(bundle, "42", true, "").status == "screen-recording-denied")
bundle="com.microsoft.VSCode"
focus=element("AXTextArea", "SOURCE CODE SHOULD NOT BE READ")
assert(m.capture(bundle, "42", true, "").status == "no-readable-text")
focus.AXDescription="Terminal input"
assert(m.capture(bundle, "42", true, "").text:find("SOURCE CODE"))
assert(screenshot==1)
print("AX adapter fixtures passed")
