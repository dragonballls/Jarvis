import type { DiaryDay, DiaryPage } from '../types'

const API_BASE = (
  import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8080/api/v1'
).replace(/\/$/, '')

const AUTH_KEY = 'friday_api_secret'

function getApiKey(): string {
  return localStorage.getItem(AUTH_KEY) || ''
}

export function setApiKey(key: string) {
  localStorage.setItem(AUTH_KEY, key)
}

function authHeaders(): Record<string, string> {
  const key = getApiKey()
  return key ? { 'X-API-Key': key } : {}
}

export interface ApiError {
  status: number
  message: string
  body?: any
}

export async function fetchApi<T = any>(
  path: string,
  options: RequestInit = {},
  timeoutMs = 15_000,
): Promise<T> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)

  try {
    const res = await fetch(`${API_BASE}${path}`, {
      ...options,
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        ...authHeaders(),
        ...options.headers,
      },
    })

    if (!res.ok) {
      const body = await res.json().catch(() => null)
      throw { status: res.status, message: body?.error || res.statusText, body } as ApiError
    }

    return await res.json() as T
  } finally {
    clearTimeout(timer)
  }
}

async function streamEndpoint(
  path: string,
  body: Record<string, unknown>,
  onEvent: (event: any) => void,
  onError: (err: any) => void,
  onDone: () => void,
  controller: AbortController,
) {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify(body),
      signal: controller.signal,
    })

    if (!res.ok) {
      const data = await res.json().catch(() => null)
      onError({ status: res.status, message: data?.error || res.statusText })
      onDone()
      return
    }

    const reader = res.body?.getReader()
    if (!reader) {
      onError({ message: 'No response body' })
      onDone()
      return
    }

    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      for (const line of lines) {
        if (!line.trim()) continue
        try { onEvent(JSON.parse(line)) } catch {}
      }
    }

    buffer += decoder.decode()
    if (buffer.trim()) {
      try { onEvent(JSON.parse(buffer)) } catch {}
    }
    onDone()
  } catch (err: any) {
    if (err?.name !== 'AbortError') {
      onError(err)
      onDone()
    }
  }
}

export function streamChat(
  body: { message: string; session_id?: string; persona?: string; persona_prompt?: string },
  onEvent: (event: any) => void,
  onError: (err: any) => void,
  onDone: () => void,
): AbortController {
  const controller = new AbortController()
  streamEndpoint('/chat', body, onEvent, onError, onDone, controller)
  return controller
}

export function streamAutopilot(
  body: { goal: string; session_id?: string },
  onEvent: (event: any) => void,
  onError: (err: any) => void,
  onDone: () => void,
): AbortController {
  const controller = new AbortController()
  streamEndpoint('/autopilot', body, onEvent, onError, onDone, controller)
  return controller
}

export function checkHealth(): Promise<any> { return fetchApi('/health') }

export interface ProviderStatus { id: string; env_var: string; configured: boolean }
export interface ProviderTestResult { provider: string; configured: boolean; ready: boolean; error?: string }
export async function getProviderStatus(): Promise<{ providers: ProviderStatus[] }> { return fetchApi('/providers') }
export async function saveProviderKey(provider: string, apiKey: string): Promise<{ success: boolean; provider: string; configured: boolean }> {
  return fetchApi('/providers', { method: 'POST', body: JSON.stringify({ provider, api_key: apiKey }) })
}
export async function removeProviderKey(provider: string): Promise<{ success: boolean; provider: string; configured: boolean }> {
  return fetchApi(`/providers/${encodeURIComponent(provider)}`, { method: 'DELETE' })
}
export async function testProviders(): Promise<{ providers: ProviderTestResult[] }> {
  return fetchApi('/providers/test', { method: 'POST' })
}

export interface VoiceStatus {
  provider: string
  configured: boolean
  voice_id_configured: boolean
  voice_id: string
  voice_name: string
  model_id: string
  fallback: string
}
export async function getVoiceStatus(): Promise<VoiceStatus> { return fetchApi('/voice/status') }

export async function synthesizeVoice(text: string): Promise<Blob> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 35_000)
  try {
    const res = await fetch(`${API_BASE}/voice/synthesize`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ text }),
      signal: controller.signal,
    })
    if (!res.ok) {
      const body = await res.json().catch(() => null)
      throw { status: res.status, message: body?.error || res.statusText, body } as ApiError
    }
    return await res.blob()
  } finally {
    clearTimeout(timer)
  }
}

export async function getMetrics(): Promise<any> { return fetchApi('/metrics') }
export async function getSessions(): Promise<{ sessions: { id: string; language: string }[] }> { return fetchApi('/sessions') }
export async function createSession(language = 'english') { return fetchApi('/sessions', { method: 'POST', body: JSON.stringify({ language }) }) }
export async function deleteSession(sessionId: string) { return fetchApi(`/sessions/${sessionId}`, { method: 'DELETE' }) }
export async function getOutputDir(sessionId = 'default') { return fetchApi<{ output_dir: string }>(`/output-dir?session_id=${sessionId}`) }
export async function setOutputDir(path: string, sessionId = 'default') { return fetchApi('/output-dir', { method: 'PUT', body: JSON.stringify({ session_id: sessionId, path }) }) }
export async function getApprovals(): Promise<{ approvals: any[] }> { return fetchApi('/approvals') }
export async function resolveApproval(requestId: string, allowed: boolean) { return fetchApi(`/approvals/${encodeURIComponent(requestId)}`, { method: 'POST', body: JSON.stringify({ allowed }) }) }
export async function getSystemInfo(): Promise<any> { return fetchApi('/system-info') }
export async function getNews(): Promise<{ articles: any[] }> { return fetchApi('/news') }
export async function getWeather(): Promise<any> { return fetchApi('/weather') }
export async function getStocks(symbols = 'AAPL,GOOG,MSFT,NVDA,BTC-USD'): Promise<any> { return fetchApi(`/stocks?symbols=${encodeURIComponent(symbols)}`) }
export async function getGithubTrending(): Promise<any> { return fetchApi('/github-trending') }
export async function getEarthquakes(): Promise<any> { return fetchApi('/earthquakes') }
export async function getCrypto(): Promise<any> { return fetchApi('/crypto') }
export async function getSpace(): Promise<any> { return fetchApi('/space') }
export async function getGlobalTime(): Promise<any> { return fetchApi('/global-time') }
export async function getCve(): Promise<any> { return fetchApi('/cve') }
export async function getScreen(): Promise<any> { return fetchApi('/screen') }
export async function getMemory(): Promise<any> { return fetchApi('/memory') }
export async function searchMemory(query: string, topK = 5): Promise<any> { return fetchApi('/memory/search', { method: 'POST', body: JSON.stringify({ query, top_k: topK }) }) }
export async function clearMemory() { return fetchApi('/memory', { method: 'DELETE' }) }
export async function deleteMemory(entryId: string) { return fetchApi(`/memory/${encodeURIComponent(entryId)}`, { method: 'DELETE' }) }

export interface KnowledgeEntity { name: string; type: string; mentions: number; source?: string; first_seen?: number; last_seen?: number }
export async function getKnowledge(): Promise<{ entities: KnowledgeEntity[]; count: number }> { return fetchApi('/knowledge') }
export async function storeKnowledge(text: string): Promise<{ added: KnowledgeEntity[]; count: number }> { return fetchApi('/knowledge', { method: 'POST', body: JSON.stringify({ text }) }) }
export async function queryKnowledge(term: string): Promise<{ results: KnowledgeEntity[]; count: number }> { return fetchApi('/knowledge/query', { method: 'POST', body: JSON.stringify({ term }) }) }
export async function getKnowledgeContinuity(): Promise<{ continuity: string }> { return fetchApi('/knowledge/continuity') }

export interface ComputerStatus { platform: string; mouse_keyboard: boolean; window_management: boolean; note?: string }
export async function getComputerStatus(): Promise<ComputerStatus> { return fetchApi('/computer/status') }
export interface ComputerWindow { handle: number; title: string }
export interface ComputerWindows { windows: ComputerWindow[]; count: number }
export async function getComputerWindows(): Promise<ComputerWindows> { return fetchApi('/computer/windows') }
export interface ComputerSummary extends ComputerStatus { windows: ComputerWindow[]; count: number; size: { success: boolean; width?: number; height?: number; error?: string } }
export async function getComputerSummary(): Promise<ComputerSummary> { return fetchApi('/computer/summary') }

export interface MarketplacePlugin { name: string; builtin: boolean; installed: boolean; enabled: boolean; description: string }
export async function getPlugins(): Promise<MarketplacePlugin[]> { const res = await fetchApi<{ plugins: MarketplacePlugin[] }>('/plugins'); return res.plugins }
export async function installPlugin(name: string): Promise<{ success: boolean; message?: string; error?: string }> { return fetchApi('/plugins/install', { method: 'POST', body: JSON.stringify({ name }) }) }
export async function uninstallPlugin(name: string): Promise<{ success: boolean; message?: string; error?: string }> { return fetchApi('/plugins/uninstall', { method: 'POST', body: JSON.stringify({ name }) }) }

export interface CustomTool { name: string; description: string; parameters: { type: string; properties: Record<string, unknown>; required: string[] }; body: string; source: string }
export async function getCustomTools(): Promise<CustomTool[]> { const res = await fetchApi<{ tools: CustomTool[] }>('/tools/custom'); return res.tools }
export async function createCustomTool(description: string): Promise<{ tool?: CustomTool; error?: string }> { return fetchApi('/tools/custom', { method: 'POST', body: JSON.stringify({ description }) }) }
export async function deleteCustomTool(name: string): Promise<{ success?: boolean; error?: string }> { return fetchApi(`/tools/custom/${encodeURIComponent(name)}`, { method: 'DELETE' }) }

export interface PrivacyStatus { enabled: boolean; local_provider: string; blocked_tools: string[] }
export async function getPrivacyStatus(): Promise<PrivacyStatus> { return fetchApi('/privacy') }
export async function setPrivacy(enabled: boolean): Promise<PrivacyStatus> { return fetchApi('/privacy', { method: 'POST', body: JSON.stringify({ enabled }) }) }
