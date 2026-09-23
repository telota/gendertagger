// jsdom does not implement `window.matchMedia` (a long-standing, documented gap: it has no CSS
// media-query evaluation engine). Provide a default stub — always reporting "no preference" — so
// any code that calls it (e.g. `useTheme`) doesn't crash tests that aren't exercising media-query
// behaviour themselves. A test that needs to control it stubs it further with
// `vi.stubGlobal('matchMedia', ...)`; `vi.unstubAllGlobals()` in that test's `afterEach` restores
// this default for the rest of the file.
class StubMediaQueryList extends EventTarget implements MediaQueryList {
  matches = false
  media: string
  onchange: ((this: MediaQueryList, event: MediaQueryListEvent) => unknown) | null = null

  constructor(media: string) {
    super()
    this.media = media
  }

  addListener(): void {
    // Deprecated in favour of addEventListener; no listeners to notify since matches never changes.
  }

  removeListener(): void {
    // Deprecated in favour of removeEventListener; nothing to remove.
  }
}

if (!window.matchMedia) {
  window.matchMedia = (query: string): MediaQueryList => new StubMediaQueryList(query)
}

// jsdom also has no layout engine, so it doesn't implement `ResizeObserver` either — needed by
// Headless UI's `Dialog` (used by `SessionRecoveryDialog`) to track its panel. Nothing under test
// reads real sizes, so a no-op observer is enough to let it mount without crashing.
class StubResizeObserver implements ResizeObserver {
  observe(): void {
    // No layout to observe in jsdom.
  }

  unobserve(): void {
    // Nothing was ever observed.
  }

  disconnect(): void {
    // Nothing to disconnect.
  }
}

if (!window.ResizeObserver) {
  window.ResizeObserver = StubResizeObserver
}
