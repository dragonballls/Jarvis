import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { watchForUpdates } from './core/autoUpdate'
import { bindDocumentVisibility, getJarvisLifecycle } from './core/backgroundMode'

// Production updates remain non-visual. The only application UI is the Jarvis chat bar.
if (import.meta.env.PROD) watchForUpdates()

const root = document.getElementById('root')

if (!root) {
  throw new Error('Jarvis root element was not found.')
}

// Minimize/hide is treated as a lifecycle transition, not a shutdown. Keep
// interaction hooks mounted while exposing state to presentation components.
const unbindVisibility = bindDocumentVisibility()
document.documentElement.dataset.jarvisLifecycle = getJarvisLifecycle()
const updateLifecycleAttribute = () => {
  document.documentElement.dataset.jarvisLifecycle = getJarvisLifecycle()
}
document.addEventListener('visibilitychange', updateLifecycleAttribute)

window.addEventListener('beforeunload', () => {
  unbindVisibility()
  document.removeEventListener('visibilitychange', updateLifecycleAttribute)
})

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
