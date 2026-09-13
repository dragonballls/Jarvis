import { useState, useRef, useCallback, useEffect } from 'react'
import { getVoiceStatus, synthesizeVoice } from '../core/api'

export type VoiceOutputStatus = 'idle' | 'speaking' | 'paused'

export interface SpeakOptions {
  rate?: number
  pitch?: number
}

interface UseVoiceOutputReturn {
  isSupported: boolean
  enabled: boolean
  setEnabled: (v: boolean) => void
  status: VoiceOutputStatus
  speak: (text: string, options?: SpeakOptions) => void
  stop: () => void
  pause: () => void
  resume: () => void
  voices: SpeechSynthesisVoice[]
  selectedVoice: SpeechSynthesisVoice | null
  setVoice: (voice: SpeechSynthesisVoice) => void
}

const VOICE_STORAGE_KEY = 'friday_tts_voice_uri'
const ENABLED_STORAGE_KEY = 'friday_voice_output_enabled'

export function useVoiceOutput(): UseVoiceOutputReturn {
  const [enabled, setEnabled] = useState(() => localStorage.getItem(ENABLED_STORAGE_KEY) === 'true')
  const [status, setStatus] = useState<VoiceOutputStatus>('idle')
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([])
  const [selectedVoice, setSelectedVoiceState] = useState<SpeechSynthesisVoice | null>(null)
  const [cloudVoiceReady, setCloudVoiceReady] = useState(false)
  const selectedVoiceRef = useRef<SpeechSynthesisVoice | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const audioUrlRef = useRef<string | null>(null)
  const speakQueueRef = useRef<{ text: string; options?: SpeakOptions }[]>([])
  const speakingRef = useRef(false)
  const synthRef = useRef<SpeechSynthesis | null>(null)
  const cloudSpeakingRef = useRef(false)

  const isSupported = typeof window !== 'undefined' && ('speechSynthesis' in window || 'Audio' in window)

  const cleanupAudio = useCallback(() => {
    const audio = audioRef.current
    if (audio) {
      audio.onended = null
      audio.onerror = null
      audio.pause()
      audio.src = ''
    }
    audioRef.current = null
    if (audioUrlRef.current) {
      URL.revokeObjectURL(audioUrlRef.current)
      audioUrlRef.current = null
    }
    cloudSpeakingRef.current = false
  }, [])

  const processBrowserQueue = useCallback(() => {
    if (speakingRef.current || speakQueueRef.current.length === 0) return
    const synth = synthRef.current
    if (!synth) return
    const item = speakQueueRef.current.shift()!
    speakingRef.current = true
    const utterance = new SpeechSynthesisUtterance(item.text)
    if (selectedVoiceRef.current) utterance.voice = selectedVoiceRef.current
    utterance.rate = item.options?.rate ?? 0.94
    utterance.pitch = item.options?.pitch ?? 0.82
    utterance.volume = 1
    utterance.onstart = () => setStatus('speaking')
    utterance.onend = () => {
      speakingRef.current = false
      if (speakQueueRef.current.length > 0) processBrowserQueue()
      else setStatus('idle')
    }
    utterance.onerror = () => {
      speakingRef.current = false
      if (speakQueueRef.current.length > 0) processBrowserQueue()
      else setStatus('idle')
    }
    utterance.onpause = () => setStatus('paused')
    utterance.onresume = () => setStatus('speaking')
    synth.speak(utterance)
  }, [])

  const enqueueBrowserSpeech = useCallback((text: string, options?: SpeakOptions) => {
    if (!synthRef.current) return false
    speakQueueRef.current.push({ text, options })
    processBrowserQueue()
    return true
  }, [processBrowserQueue])

  const speakWithCloudVoice = useCallback(async (text: string, options?: SpeakOptions) => {
    if (!cloudVoiceReady) return false
    cleanupAudio()
    try {
      const blob = await synthesizeVoice(text)
      if (blob.size === 0) throw new Error('ElevenLabs returned empty audio')
      const url = URL.createObjectURL(blob)
      const audio = new Audio(url)
      audio.preload = 'auto'
      audio.playbackRate = options?.rate && options.rate > 0 ? options.rate : 1
      audioRef.current = audio
      audioUrlRef.current = url
      cloudSpeakingRef.current = true
      setStatus('speaking')
      audio.onended = () => { cleanupAudio(); setStatus('idle') }
      audio.onerror = () => { cleanupAudio(); enqueueBrowserSpeech(text, options) }
      await audio.play()
      return true
    } catch {
      cleanupAudio()
      return enqueueBrowserSpeech(text, options)
    }
  }, [cloudVoiceReady, cleanupAudio, enqueueBrowserSpeech])

  const speak = useCallback((text: string, options?: SpeakOptions) => {
    if (!isSupported || !enabled || !text.trim()) return
    if (cloudVoiceReady) {
      void speakWithCloudVoice(text.trim(), options)
      return
    }
    enqueueBrowserSpeech(text.trim(), options)
  }, [isSupported, enabled, cloudVoiceReady, speakWithCloudVoice, enqueueBrowserSpeech])

  const stop = useCallback(() => {
    synthRef.current?.cancel()
    cleanupAudio()
    speakQueueRef.current = []
    speakingRef.current = false
    setStatus('idle')
  }, [cleanupAudio])

  const pause = useCallback(() => {
    if (cloudSpeakingRef.current && audioRef.current) {
      audioRef.current.pause()
      setStatus('paused')
      return
    }
    synthRef.current?.pause()
  }, [])

  const resume = useCallback(() => {
    if (cloudSpeakingRef.current && audioRef.current) {
      void audioRef.current.play().then(() => setStatus('speaking')).catch(() => setStatus('idle'))
      return
    }
    synthRef.current?.resume()
  }, [])

  const setVoice = useCallback((voice: SpeechSynthesisVoice) => {
    selectedVoiceRef.current = voice
    setSelectedVoiceState(voice)
    try { localStorage.setItem(VOICE_STORAGE_KEY, voice.voiceURI) } catch {}
  }, [])

  const setEnabledWrapped = useCallback((v: boolean) => {
    setEnabled(v)
    try { localStorage.setItem(ENABLED_STORAGE_KEY, String(v)) } catch {}
    if (!v) stop()
  }, [stop])

  useEffect(() => {
    if (!isSupported || !('speechSynthesis' in window)) return
    const synth = window.speechSynthesis
    synthRef.current = synth
    const loadVoices = () => {
      const v = synth.getVoices()
      if (!v.length) return
      setVoices(v)
      const savedURI = localStorage.getItem(VOICE_STORAGE_KEY)
      const match = savedURI ? v.find(vo => vo.voiceURI === savedURI) : null
      const fallback = match || v.find(vo => vo.lang.toLowerCase().startsWith('en-gb')) || v.find(vo => vo.lang.startsWith('en')) || v[0]
      selectedVoiceRef.current = fallback
      setSelectedVoiceState(fallback)
    }
    loadVoices()
    synth.addEventListener('voiceschanged', loadVoices)
    return () => { synth.removeEventListener('voiceschanged', loadVoices); cleanupAudio() }
  }, [isSupported, cleanupAudio])

  useEffect(() => {
    let cancelled = false
    void getVoiceStatus().then(info => {
      if (!cancelled) setCloudVoiceReady(info.provider === 'elevenlabs' && info.configured && Boolean(info.voice_id_configured))
    }).catch(() => { if (!cancelled) setCloudVoiceReady(false) })
    return () => { cancelled = true }
  }, [])

  return {
    isSupported,
    enabled,
    setEnabled: setEnabledWrapped,
    status,
    speak,
    stop,
    pause,
    resume,
    voices,
    selectedVoice,
    setVoice,
  }
}