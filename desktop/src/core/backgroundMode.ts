export type JarvisLifecycle = 'foreground' | 'background'

type Listener = (mode: JarvisLifecycle) => void

let lifecycle: JarvisLifecycle = 'foreground'
const listeners = new Set<Listener>()

export function getJarvisLifecycle(): JarvisLifecycle {
  return lifecycle
}

export function setJarvisLifecycle(mode: JarvisLifecycle): boolean {
  if (mode === lifecycle) return false
  lifecycle = mode
  for (const listener of listeners) {
    try {
      listener(mode)
    } catch {
      // An optional UI listener must never break the lifecycle transition.
    }
  }
  return true
}

export function subscribeJarvisLifecycle(listener: Listener): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function bindDocumentVisibility(): () => void {
  const sync = () => {
    setJarvisLifecycle(document.visibilityState === 'hidden' ? 'background' : 'foreground')
  }

  document.addEventListener('visibilitychange', sync)
  sync()
  return () => document.removeEventListener('visibilitychange', sync)
}
