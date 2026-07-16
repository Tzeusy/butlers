// ---------------------------------------------------------------------------
// Amber text consumer regression tests — bu-kx3xc
//
// `contrast.test.ts` proves the --amber-text token itself clears AA. These
// checks cover direct style props outside Tailwind classes, while retaining
// bright --amber for the decorative progress fill and warning border.
// ---------------------------------------------------------------------------

import { readFileSync } from "node:fs"
import { fileURLToPath } from "node:url"
import { describe, expect, it } from "vitest"

function readSource(relativePath: string): string {
  return readFileSync(fileURLToPath(new URL(relativePath, import.meta.url)), "utf-8")
}

describe("amber text consumers", () => {
  it("uses the AA-safe token for ProviderConfigDrawer copy while retaining its warning border", () => {
    const source = readSource("../components/secrets/passport/ProviderConfigDrawer.tsx")

    expect(source.match(/color="var\(--amber-text\)"/g) ?? []).toHaveLength(2)
    expect(source).toContain('border: "1px solid var(--amber)"')
  })

  it("uses the AA-safe token for DirectionPassport captions", () => {
    const source = readSource("../components/secrets/passport/DirectionPassport.tsx")

    expect(source).toContain('? "var(--amber-text)"')
  })

  it("uses the AA-safe token for Plex capacity labels while retaining the amber fill", () => {
    const source = readSource("../components/relationship/PlexPage.tsx")

    expect(source.match(/color: over \? "var\(--amber-text\)" : "var\(--dim\)"/g) ?? []).toHaveLength(2)
    expect(source).toMatch(/backgroundColor:\s*over\s*\?\s*"var\(--amber\)"/)
  })
})
