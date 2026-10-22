-- {{< generated <name> <key> >}}: a value of a generated appendix that is computed at render, not committed
-- (tools/generated_values.py): a count summed over chapters, or a symbol's first use, which two chapters' edits
-- would both change. The value comes from _generated/<name>.json, which the appendix's generator writes before
-- every render (pre-render); a missing value stops the render.
local values = {}

local function load(name)
  if values[name] == nil then
    local file = quarto.project.directory .. "/_generated/" .. name .. ".json"
    local f = io.open(file, "r")
    if f == nil then
      error(file .. " is missing: run the generators of book/_quarto.yml's pre-render step")
    end
    values[name] = quarto.json.decode(f:read("a"))
    f:close()
  end
  return values[name]
end

return {
  ["generated"] = function(args, kwargs, meta, raw_args, context)
    local name = args[1] and pandoc.utils.stringify(args[1]) or ""
    local key = args[2] and pandoc.utils.stringify(args[2]) or ""
    local v = load(name)[key]
    if v == nil then
      error("no generated value " .. name .. " " .. key .. ": run the generators of book/_quarto.yml's pre-render step")
    end
    -- a value is markdown: a number, a dash, or a cross-reference that quarto resolves after this shortcode
    local inlines = pandoc.utils.blocks_to_inlines(pandoc.read(v, "markdown").blocks)
    -- alone in a table cell the shortcode is a block; Plain keeps the cell as the committed text would (no <p>)
    if context == "block" then
      return pandoc.Plain(inlines)
    end
    return inlines
  end,
}
