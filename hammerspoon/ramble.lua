-- Ramble: push-to-talk dictation for AI agents.
-- Control+Option+. starts recording and stops it again; the text is cleaned up into a faithful prompt and
-- copied (and pasted, see below). Control+Option+Shift+. copies the last dictation as heard, before cleanup.
-- install.sh copies this file to ~/.hammerspoon/ramble.lua and adds require("ramble") to init.lua.
local home = "@RAMBLE_HOME@"
local script = home .. "/dictate.sh"

-- Change the hotkeys here.
local hotkey = {mods = {"ctrl", "alt"}, key = "."}
local rawHotkey = {mods = {"ctrl", "alt", "shift"}, key = "."}

local menu = hs.menubar.new()
local working = nil  -- the "Transcribing" alert, shown until the stop finishes

-- Auto-paste: when the text is ready, press Command+V for you, but only if the app that was in front when you
-- stopped recording is still in front. Needs Accessibility permission for Hammerspoon.
-- Turn it off by creating the file no-autopaste in the install folder.
local stopWindow = nil
local stopApp = nil  -- bundle ID of the app in front at the stop press
local function autopaste()
  if hs.fs.attributes(home .. "/no-autopaste") then return false end
  if not hs.accessibilityState(true) then return false end
  local front = hs.application.frontmostApplication()
  local function sameDestination()
    local win = hs.window.focusedWindow()
    local app = hs.application.frontmostApplication()
    return app and app:bundleID() == stopApp and win and win:id() == stopWindow
  end
  if not (front and stopApp and sameDestination()) then return false end
  hs.timer.doAfter(0.05, function() if sameDestination() then hs.eventtap.keyStroke({"cmd"}, "v", 0) end end)
  return true
end

local function contextStatus()
  local f = io.open(home .. "/state/context-status.json", "r")
  if not f then return "Context: no dictation yet" end
  local raw = f:read("*a"); f:close()
  local ok, value = pcall(hs.json.decode, raw)
  if not ok or type(value) ~= "table" then return "Context: unavailable" end
  if value.status == "ok" then return "Context: " .. (value.source or "active window") .. " (" .. tostring(value.characters) .. " characters)" end
  return "Context: " .. (value.status or "unavailable")
end
local function setIdle()
  if working then hs.alert.closeSpecific(working); working = nil end
  if menu then menu:setTitle("🎙"); menu:setTooltip("Dictation idle (Control+Option+. or Command+Option+.)\n" .. contextStatus()) end
end
local function setRecording()
  if menu then menu:setTitle("🔴 REC"); menu:setTooltip("Recording: Control+Option+. to stop") end
end
local function setWorking()
  if menu then menu:setTitle("⏳"); menu:setTooltip("Transcribing and cleaning up") end
  working = hs.alert.show("Transcribing and cleaning up...", 60)
end

-- The script's own state, not a flag kept here, decides what a press means: a flag here goes wrong after a
-- config reload during a recording.
local function status()
  local out = hs.execute("'" .. script .. "' status") or ""
  return (out:gsub("%s+$", ""))
end

local function preview(text)
  return #text > 90 and (text:sub(1, 90) .. "...") or text
end

local function toggle()
  local now = status()
  if now == "BUSY" then
    hs.alert.show("Still transcribing the last one. Wait for \"Copied\".", 2)
    return
  end
  local args = {"toggle"}
  if now == "RECORDING" then
    local front = hs.application.frontmostApplication()
    stopApp = front and front:bundleID() or nil
    local win = hs.window.focusedWindow()
    stopWindow = win and win:id() or nil
    args = {"toggle", stopApp or "", stopWindow and tostring(stopWindow) or ""}
    setWorking()
  end
  hs.task.new(script, function(_, out, err)
    out = (out or ""):gsub("%s+$", "")
    if out:find("^BUSY") then
      hs.alert.show("Still transcribing the last one. Wait for \"Copied\".", 2)
    elseif out:find("^RECORDING") then
      setRecording(); hs.alert.show("● Recording (Control+Option+. to stop)", 1.2)
    elseif out:find("^COPIED: ") then
      setIdle()
      local text = out:sub(9)
      if autopaste() then hs.alert.show("Pasted\n" .. preview(text), 2)
      else hs.alert.show("Copied. Press Command+V\n" .. preview(text), 2.5) end
    elseif out:find("^RAW: ") then
      setIdle()
      local text = out:sub(6)
      if autopaste() then hs.alert.show("Cleanup failed; pasted what you said as heard\n" .. preview(text), 3.5)
      else hs.alert.show("Cleanup failed; copied what you said as heard. Press Command+V\n" .. preview(text), 3.5) end
    elseif out:find("^IDLE") then
      setIdle()
    else
      setIdle(); hs.alert.show("Dictation error: " .. (out ~= "" and out or (err or "unknown")), 4)
    end
  end, args):start()
end

hs.hotkey.bind(hotkey.mods, hotkey.key, toggle)
-- Also support the Command+Option+. shortcut used by existing installations.
hs.hotkey.bind({"cmd", "alt"}, ".", toggle)

hs.hotkey.bind(rawHotkey.mods, rawHotkey.key, function()
  hs.task.new(script, function(_, out, err)
    out = (out or ""):gsub("%s+$", "")
    if out:find("^RAW: ") then
      hs.alert.show("Copied the raw transcript. Press Command+V\n" .. preview(out:sub(6)), 2.5)
    else
      hs.alert.show("Dictation: " .. (out ~= "" and out or (err or "unknown")), 3)
    end
  end, {"raw"}):start()
end)

if menu then menu:setClickCallback(toggle) end
if status() == "RECORDING" then setRecording() else setIdle() end
hs.alert.show("Dictation ready: Control+Option+.", 1.5)
