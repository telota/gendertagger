import { describe, expect, it } from 'vitest'

import { formatGameDuration, gameAnswerPoints } from '@/features/game/useGameData'

describe('game scoring presentation', () => {
  it('uses the fixed server-verifiable score for every saved answer', () => {
    expect(gameAnswerPoints()).toBe(10)
  })

  it('formats elapsed milliseconds as tabular round time', () => {
    expect(formatGameDuration(0)).toBe('0:00')
    expect(formatGameDuration(65_999)).toBe('1:05')
  })
})
