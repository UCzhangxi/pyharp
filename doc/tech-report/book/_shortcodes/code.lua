-- {{< code <path> [<symbol>] [overload=N] >}}: a code citation by symbol (README, "Citing code").
-- Renders `basename` `symbol`, linked to the symbol's lines in the file at the pin of code_pin.yml. The lines
-- come from _code_anchors.json, which tools/code_anchors.py writes before every render (pre-render); a
-- citation that is not in it stops the render.
local citations = nil

local function load()
  if citations == nil then
    local name = quarto.project.directory .. "/_code_anchors.json"
    local f = io.open(name, "r")
    if f == nil then
      error(name .. " is missing: run python3 tools/code_anchors.py check")
    end
    citations = quarto.json.decode(f:read("a")).citations
    f:close()
  end
  return citations
end

return {
  ["code"] = function(args, kwargs)
    local path = args[1] and pandoc.utils.stringify(args[1]) or ""
    local symbol = args[2] and pandoc.utils.stringify(args[2]) or ""
    local overload = pandoc.utils.stringify(kwargs["overload"] or "")
    local repo = pandoc.utils.stringify(kwargs["repo"] or "pyharp")
    local key = repo .. "|" .. path .. "|" .. symbol .. "|" .. overload
    local c = load()[key]
    if c == nil then
      error("unresolved code citation " .. key .. ": run python3 tools/code_anchors.py check")
    end
    local text = { pandoc.Code(c.label) }
    if c.symbol ~= nil and c.symbol ~= pandoc.json.null then
      text[#text + 1] = pandoc.Space()
      text[#text + 1] = pandoc.Code(c.symbol)
    end
    return pandoc.Link(text, c.url)
  end,
}
