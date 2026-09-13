import type { FormEvent } from 'react'
import { useEffect, useRef, useState } from 'react'
import {
  checkHealth,
  getProviderStatus,
  removeProviderKey,
  saveProviderKey,
  streamAutopilot,
  streamChat,
  testProviders,
  type ProviderStatus,
  type ProviderTestResult,
} from './core/api'

const SELF_CODING_GOAL =
  'Continue improving Jarvis. Inspect the current Jarvis workspace, identify the highest-value safe improvement, implement it, verify it, preserve existing working behavior, and leave the workspace in a working state. Work incrementally and keep durable progress in the workspace so another run can continue after interruption.'

const SELF_CODING_RESTART_MS = 1_500
const SELF_CODING_RETRY_MS = 10_000

const PROVIDER_LABELS: Record<string, string> = {
  openai: 'OpenAI',
  openrouter: 'OpenRouter',
  zen_coder: 'Zen Coder',
  groq: 'Groq',
}

function App() {
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [response, setResponse] = useState('')
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [providers, setProviders] = useState<ProviderStatus[]>([])
  const [keys, setKeys] = useState<Record<string, string>>({})
  const [providerResults, setProviderResults] = useState<Record<string, ProviderTestResult>>({})
  const [settingsMessage, setSettingsMessage] = useState('')
  const codingTimerRef = useRef<number | null>(null)
  const codingControllerRef = useRef<AbortController | null>(null)
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      if (codingTimerRef.current !== null) {
        window.clearTimeout(codingTimerRef.current)
        codingTimerRef.current = null
      }
      codingControllerRef.current?.abort()
      codingControllerRef.current = null
    }
  }, [])

  const refreshProviders = async () => {
    try {
      const result = await getProviderStatus()
      if (mountedRef.current) setProviders(result.providers)
    } catch (err: any) {
      if (mountedRef.current) setSettingsMessage(`Unable to load provider status: ${String(err?.message ?? err)}`)
    }
  }

  const openSettings = async () => {
    setSettingsOpen(true)
    setSettingsMessage('')
    await refreshProviders()
  }

  const saveKey = async (provider: string) => {
    const apiKey = keys[provider]?.trim() || ''
    if (!apiKey) {
      setSettingsMessage(`Enter a ${PROVIDER_LABELS[provider] || provider} API key first.`)
      return
    }
    try {
      await saveProviderKey(provider, apiKey)
      setKeys((current) => ({ ...current, [provider]: '' }))
      setSettingsMessage(`${PROVIDER_LABELS[provider] || provider} key saved securely on this Windows account.`)
      await refreshProviders()
    } catch (err: any) {
      setSettingsMessage(`Could not save key: ${String(err?.message ?? err)}`)
    }
  }

  const removeKey = async (provider: string) => {
    try {
      await removeProviderKey(provider)
      setSettingsMessage(`${PROVIDER_LABELS[provider] || provider} key removed.`)
      await refreshProviders()
    } catch (err: any) {
      setSettingsMessage(`Could not remove key: ${String(err?.message ?? err)}`)
    }
  }

  const verifyProviders = async () => {
    try {
      const result = await testProviders()
      setProviderResults(Object.fromEntries(result.providers.map((item) => [item.provider, item])))
      const ready = result.providers.filter((item) => item.ready).length
      setSettingsMessage(`${ready} configured provider${ready === 1 ? '' : 's'} passed Jarvis provider initialization.`)
    } catch (err: any) {
      setSettingsMessage(`Provider verification failed: ${String(err?.message ?? err)}`)
    }
  }

  const speak = (text: string) => {
    if (!text.trim() || !('speechSynthesis' in window)) return
    window.speechSynthesis.cancel()
    const utterance = new SpeechSynthesisUtterance(text)
    utterance.rate = 0.94
    utterance.pitch = 0.95
    window.speechSynthesis.speak(utterance)
  }

  const sendMessage = (event?: FormEvent) => {
    event?.preventDefault()
    const message = input.trim()
    if (!message || busy) return

    if (message.toLowerCase() === '/settings' || message.toLowerCase() === '/keys') {
      setInput('')
      void openSettings()
      return
    }

    setInput('')
    setResponse('')
    setBusy(true)

    let fullResponse = ''
    streamChat(
      { message, session_id: 'default', persona: 'jarvis' },
      (chunk) => {
        const content = String(chunk?.content ?? '')
        if (!content) return
        fullResponse += content
        if (mountedRef.current) setResponse(fullResponse)
      },
      (err) => {
        const text = `I encountered an error: ${String(err?.message ?? err ?? 'unknown error')}`
        fullResponse = text
        if (mountedRef.current) setResponse(text)
      },
      () => {
        if (!mountedRef.current) return
        setBusy(false)
        if (fullResponse.trim()) speak(fullResponse)
      },
    )
  }

  useEffect(() => {
    let cancelled = false

    const scheduleNext = (delay: number) => {
      if (cancelled) return
      if (codingTimerRef.current !== null) window.clearTimeout(codingTimerRef.current)
      codingTimerRef.current = window.setTimeout(runSelfCoding, delay)
    }

    const runSelfCoding = () => {
      if (cancelled) return

      const sessionId = `jarvis-self-coding-${Date.now()}`
      codingControllerRef.current = streamAutopilot(
        {
          goal: SELF_CODING_GOAL,
          session_id: sessionId,
        },
        () => {
          // Self-coding output stays non-visual. Durable progress belongs in the workspace.
        },
        () => {
          codingControllerRef.current = null
          scheduleNext(SELF_CODING_RETRY_MS)
        },
        () => {
          codingControllerRef.current = null
          scheduleNext(SELF_CODING_RESTART_MS)
        },
      )
    }

    const boot = async () => {
      try {
        await checkHealth()
        if (!cancelled) runSelfCoding()
      } catch {
        scheduleNext(SELF_CODING_RETRY_MS)
      }
    }

    void boot()

    return () => {
      cancelled = true
      if (codingTimerRef.current !== null) {
        window.clearTimeout(codingTimerRef.current)
        codingTimerRef.current = null
      }
      codingControllerRef.current?.abort()
      codingControllerRef.current = null
    }
  }, [])

  return (
    <main className="jarvis-shell">
      <button className="jarvis-settings-button" type="button" onClick={() => void openSettings()} aria-label="AI provider settings">
        ⚙
      </button>

      <section className="jarvis-conversation" aria-live="polite" aria-label="Jarvis conversation">
        {response ? (
          <div className="jarvis-response">{response}</div>
        ) : (
          <div className="jarvis-welcome">{busy ? 'Jarvis is thinking…' : 'How may I assist you?'}</div>
        )}
      </section>

      <form className="jarvis-bar" onSubmit={sendMessage}>
        <input
          className="jarvis-input"
          aria-label="Chat with Jarvis"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder={busy ? 'Jarvis is thinking…' : 'Talk to Jarvis…'}
          autoFocus
          disabled={busy}
          autoComplete="off"
          spellCheck={false}
        />
      </form>

      {settingsOpen && (
        <div className="jarvis-settings-backdrop" role="presentation" onMouseDown={() => setSettingsOpen(false)}>
          <section className="jarvis-settings" role="dialog" aria-modal="true" aria-label="AI provider settings" onMouseDown={(event) => event.stopPropagation()}>
            <header className="jarvis-settings-header">
              <div>
                <h2>AI providers</h2>
                <p>Keys are stored locally using Windows account encryption.</p>
              </div>
              <button type="button" onClick={() => setSettingsOpen(false)} aria-label="Close settings">×</button>
            </header>

            <div className="jarvis-provider-list">
              {providers.map((provider) => {
                const result = providerResults[provider.id]
                return (
                  <div className="jarvis-provider" key={provider.id}>
                    <div className="jarvis-provider-name">
                      <strong>{PROVIDER_LABELS[provider.id] || provider.id}</strong>
                      <span>{result ? (result.ready ? 'Ready' : 'Needs attention') : provider.configured ? 'Saved' : 'Not configured'}</span>
                    </div>
                    <div className="jarvis-provider-actions">
                      <input
                        type="password"
                        value={keys[provider.id] || ''}
                        onChange={(event) => setKeys((current) => ({ ...current, [provider.id]: event.target.value }))}
                        placeholder={provider.configured ? 'Enter a new key to replace it' : 'Paste API key'}
                        autoComplete="new-password"
                        spellCheck={false}
                      />
                      <button type="button" onClick={() => void saveKey(provider.id)}>Save</button>
                      {provider.configured && <button type="button" onClick={() => void removeKey(provider.id)}>Remove</button>}
                    </div>
                  </div>
                )
              })}
            </div>

            <footer className="jarvis-settings-footer">
              <button type="button" onClick={() => void verifyProviders()}>Verify providers</button>
              <button type="button" onClick={() => void refreshProviders()}>Refresh</button>
              {settingsMessage && <span role="status">{settingsMessage}</span>}
            </footer>
          </section>
        </div>
      )}
    </main>
  )
}

export default App
