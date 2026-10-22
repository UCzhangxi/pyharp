-- Column widths for the Code-layer tables (STYLE 2, 10.10): | what | code link | symbol | switch |.
-- Pandoc sizes pipe-table columns from the dash counts of the source, which leaves the symbol and switch
-- columns too narrow in the PDF, so long identifiers overprint the next cell. This filter gives every
-- table with that header fixed relative widths. It changes no text, only the column specs, and only for
-- LaTeX output.
local WIDTHS = {0.20, 0.28, 0.30, 0.22}

local function header_cells(tbl)
  local rows = tbl.head and tbl.head.rows
  if not rows or #rows == 0 then return nil end
  local out = {}
  for _, cell in ipairs(rows[1].cells) do
    out[#out + 1] = pandoc.utils.stringify(cell.contents):lower()
  end
  return out
end

function Table(tbl)
  if not FORMAT:match("latex") then return nil end
  local h = header_cells(tbl)
  if not h or #h ~= 4 then return nil end
  if h[1] ~= "what" or h[2] ~= "code link" or h[3] ~= "symbol" or not h[4]:match("^switch") then
    return nil
  end
  for i, spec in ipairs(tbl.colspecs) do
    tbl.colspecs[i] = {spec[1], WIDTHS[i]}
  end
  return tbl
end
