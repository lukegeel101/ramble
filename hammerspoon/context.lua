-- Bounded, read-only capture of the frontmost dictation destination.
-- No session-file search, clipboard access, scrolling, keystrokes, or browser attachment.
local M = {}
local terminals = {
  ["com.apple.Terminal"] = true, ["com.googlecode.iterm2"] = true,
  ["com.mitchellh.ghostty"] = true, ["dev.warp.Warp-Stable"] = true,
  ["net.kovidgoyal.kitty"] = true, ["com.github.wez.wezterm"] = true,
}
local desktops = {
  ["com.anthropic.claudefordesktop"] = true, ["com.anthropic.claude"] = true,
  ["com.openai.chat"] = true, ["com.openai.codex"] = true,
}
local editors = {["com.microsoft.VSCode"] = true, ["com.todesktop.230313mzl4w4u92"] = true}
local function attr(e, name)
  if not e then return nil end
  local ok, value = pcall(function() e:setTimeout(0.05); return e:attributeValue(name) end)
  if ok then return value end
end
local function tail(text)
  if type(text) ~= "string" then return "" end
  -- Keep valid UTF-8 when dropping the oldest bytes.
  local start = math.max(1, #text - 32000 + 1)
  while start <= #text and text:byte(start) >= 128 and text:byte(start) < 192 do start = start + 1 end
  return text:sub(start)
end
local function secure(e)
  return attr(e, "AXSubrole") == "AXSecureTextField"
end

-- Walk newest children first to reach the latest turns even in a long loaded chat.
-- UI chrome, sidebars, and editable fields are not message bodies.
function M.readPane(root, deadline)
  local parts, count, bytes = {}, 0, 0
  local skip = {AXToolbar=true, AXMenuBar=true, AXMenu=true, AXButton=true,
                AXOutline=true, AXTable=true, AXTextField=true, AXTextArea=true}
  local function walk(e, depth)
    if depth > 35 or count >= 500 or bytes >= 32000 or hs.timer.secondsSinceEpoch() > deadline then return end
    count = count + 1
    local role = attr(e, "AXRole")
    local sub = attr(e, "AXSubrole")
    if skip[role] or sub == "AXSecureTextField" or sub == "AXLandmarkNavigation" or sub == "AXLandmarkComplementary" then return end
    if role == "AXStaticText" then
      local value = tail(attr(e, "AXValue"))
      if value == "" then value = tail(attr(e, "AXTitle")) end
      if value ~= "" then table.insert(parts, 1, value); bytes = bytes + #value end
      return
    end
    local children = attr(e, "AXChildren") or {}
    for i=#children,1,-1 do walk(children[i], depth+1) end
  end
  walk(root, 0)
  return tail(table.concat(parts, "\n\n"))
end

function M.capture(expectedApp, expectedWindow, ocr, extraApps)
  local app = hs.application.frontmostApplication()
  local win = hs.window.focusedWindow()
  local bundle = app and app:bundleID() or ""
  local result = {status="unsupported-app", app=bundle, window=win and tostring(win:id()) or ""}
  for b in (extraApps or ""):gmatch("[^,]+") do terminals[b:match("^%s*(.-)%s*$")] = true end
  if not (terminals[bundle] or desktops[bundle] or editors[bundle]) then return result end
  if (expectedApp ~= "" and expectedApp ~= bundle) or
     (expectedWindow ~= "" and expectedWindow ~= result.window) then
    result.status = "destination-changed"; return result
  end
  if not win or win:application():pid() ~= app:pid() then result.status="no-focused-window"; return result end
  if not hs.accessibilityState() then result.status="accessibility-denied"; return result end
  local ax = hs.axuielement.applicationElement(app)
  local focus = attr(ax, "AXFocusedUIElement")
  if secure(focus) then result.status="secure-field"; return result end
  local deadline = hs.timer.secondsSinceEpoch() + 0.7
  local text = ""
  if terminals[bundle] or editors[bundle] then
    -- Only the focused text area, never another split pane, editor, or terminal tab.
    local desc = (attr(focus, "AXDescription") or ""):lower()
    if attr(focus, "AXRole") == "AXTextArea" and (terminals[bundle] or desc:find("terminal", 1, true)) then
      text = tail(attr(focus, "AXValue"))
    end
    result.source = "terminal-accessibility"
  else
    -- Find the nearest ancestor containing conversation text, stopping before the window.
    -- A composer alone yields nothing; a conversation group normally holds composer + turns.
    local e = focus
    for _=1,16 do
      e = attr(e, "AXParent")
      local role = attr(e, "AXRole")
      if not e or role == "AXWindow" or role == "AXApplication" or hs.timer.secondsSinceEpoch() > deadline then break end
      if role == "AXGroup" or role == "AXWebArea" or role == "AXScrollArea" then
        text = M.readPane(e, deadline)
        if #text >= 40 then break end
      end
    end
    result.source = "conversation-accessibility"
  end
  local current = hs.window.focusedWindow()
  if not current or current:id() ~= win:id() or hs.application.frontmostApplication():pid() ~= app:pid() then
    result.status="destination-changed"; return result
  end
  if text:match("%S") then result.status="ok"; result.text=text; return result end
  -- Some native desktop apps expose no message text. OCR only this window, entirely on-device.
  -- Never OCR a terminal/editor: split panes could contain unrelated sessions or source files.
  if desktops[bundle] and ocr then
    if not hs.screenRecordingState() then result.status="screen-recording-denied"; return result end
    local image = win:snapshot()
    if image then result.image=image:encodeAsURLString(true, "PNG"); result.status="ocr-pending"; return result end
  end
  result.status="no-readable-text"
  return result
end
return M
