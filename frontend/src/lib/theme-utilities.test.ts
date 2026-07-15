import { readFileSync, readdirSync } from "node:fs"
import { extname, relative } from "node:path"
import { fileURLToPath } from "node:url"
import { describe, expect, it } from "vitest"

const SRC_DIR = fileURLToPath(new URL("..", import.meta.url))
const CSS_SOURCE = readFileSync(fileURLToPath(new URL("../index.css", import.meta.url)), "utf-8")

function extractTopLevelBlock(source: string, selector: string): string {
  const startPattern = new RegExp(`^${selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")} \\{$`, "m")
  const startMatch = startPattern.exec(source)
  if (!startMatch) throw new Error(`Could not find "${selector} {" block in index.css`)
  const bodyStart = startMatch.index + startMatch[0].length
  const closeIndex = source.indexOf("\n}", bodyStart)
  if (closeIndex === -1) throw new Error(`Could not find closing "}" for "${selector}" block`)
  return source.slice(bodyStart, closeIndex)
}

function sourceFiles(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = `${directory}/${entry.name}`
    if (entry.isDirectory()) return sourceFiles(path)
    return [".ts", ".tsx"].includes(extname(entry.name)) ? [path] : []
  })
}

describe("Dispatch Tailwind theme utilities", () => {
  it("maps the canonical foreground and page background tokens", () => {
    const theme = extractTopLevelBlock(CSS_SOURCE, "@theme inline")

    expect(theme).toMatch(/--color-fg:\s*var\(--fg\);/)
    expect(theme).toMatch(/--color-bg:\s*var\(--bg\);/)
  })

  it("uses canonical utilities instead of exact arbitrary fg/bg token classes", () => {
    const arbitraryTokenClass =
      /(?:text|bg|border|ring|outline)-\[var\(--(?:fg|bg)\)\](?:\/[\w.[\]-]+)?/g
    const violations = sourceFiles(SRC_DIR).flatMap((path) => {
      const matches = readFileSync(path, "utf-8").match(arbitraryTokenClass) ?? []
      return matches.map((match) => `${relative(SRC_DIR, path)}: ${match}`)
    })

    expect(violations, violations.join("\n")).toHaveLength(0)
  })
})
