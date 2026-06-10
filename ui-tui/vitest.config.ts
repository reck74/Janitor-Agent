import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    exclude: ['dist/**', 'node_modules/**'],
    // cursorDriftRegression.test.ts walks a 590-char message across 7
    // terminal widths (~4k wrap-ansi iterations) and routinely hits
    // 4.3s+ on a warm runner. The upstream default of 5s is right at
    // the cliff under CI load, so it intermittently times out and
    // blocks the Janitor test gate on flakes that aren't ours.
    // 15s gives enough headroom without delaying any other test in the
    // suite (everything else finishes well under 1s).
    testTimeout: 15000
  }
})
