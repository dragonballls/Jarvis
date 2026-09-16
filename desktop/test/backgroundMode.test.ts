import { describe, expect, beforeEach, it } from 'vitest'
import {
  getJarvisLifecycle,
  setJarvisLifecycle,
  subscribeJarvisLifecycle,
} from '../src/core/backgroundMode'

describe('Jarvis background lifecycle', () => {
  beforeEach(() => {
    setJarvisLifecycle('foreground')
  })

  it('starts in foreground and transitions idempotently', () => {
    expect(getJarvisLifecycle()).toBe('foreground')
    expect(setJarvisLifecycle('background')).toBe(true)
    expect(getJarvisLifecycle()).toBe('background')
    expect(setJarvisLifecycle('background')).toBe(false)
    expect(setJarvisLifecycle('foreground')).toBe(true)
    expect(setJarvisLifecycle('foreground')).toBe(false)
  })

  it('notifies subscribers without allowing listener failures to break state changes', () => {
    const events: string[] = []
    const removeBad = subscribeJarvisLifecycle(() => {
      throw new Error('optional listener failure')
    })
    const removeGood = subscribeJarvisLifecycle((mode) => events.push(mode))

    expect(setJarvisLifecycle('background')).toBe(true)
    expect(events).toEqual(['background'])
    expect(getJarvisLifecycle()).toBe('background')

    removeBad()
    removeGood()
  })
})
