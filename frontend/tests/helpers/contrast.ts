// WCAG 2.x relative luminance and contrast ratio for opaque #rrggbb colours.

function channel(value: number): number {
  const scaled = value / 255
  return scaled <= 0.03928 ? scaled / 12.92 : ((scaled + 0.055) / 1.055) ** 2.4
}

export function luminance(hex: string): number {
  if (!/^#[0-9a-f]{6}$/i.test(hex)) throw new Error(`expected an opaque #rrggbb colour, got ${hex}`)
  const value = Number.parseInt(hex.slice(1), 16)
  return (
    0.2126 * channel((value >> 16) & 255) +
    0.7152 * channel((value >> 8) & 255) +
    0.0722 * channel(value & 255)
  )
}

export function contrastRatio(foreground: string, background: string): number {
  const [lighter = 0, darker = 0] = [luminance(foreground), luminance(background)].sort(
    (a, b) => b - a,
  )
  return (lighter + 0.05) / (darker + 0.05)
}
