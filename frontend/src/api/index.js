import axios from 'axios'

// All requests go through the Vite proxy -> http://127.0.0.1:8000
const http = axios.create({
  baseURL: '/api',
  timeout: 120000
})

// ---- Conversations ----

// Create a new conversation (backend generates thread_id).
// Returns: { thread_id, title, created_at }
export function createConversation() {
  return http.post('/conversations').then(r => r.data)
}

// List all conversations, newest first.
// Returns: { conversations: [{ thread_id, title, created_at, updated_at }] }
export function listConversations() {
  return http.get('/conversations').then(r => r.data)
}

// Get full message history of one conversation.
// Returns: { thread_id, title, messages: [{ role, content, image_urls?, created_at }] }
export function getConversation(threadId) {
  return http.get(`/conversations/${threadId}`).then(r => r.data)
}

// Delete a conversation.
// Returns: { success: true }
export function deleteConversation(threadId) {
  return http.delete(`/conversations/${threadId}`).then(r => r.data)
}

// ---- Chat ----

// Send a message to a conversation. Supports text / text+image / image.
// Uses multipart/form-data:
//   thread_id : string (required)
//   text      : string (optional, may be empty when only images sent)
//   images    : File[] (optional, 0..n image files)
// Returns: { thread_id, reply: { role: 'assistant', content, created_at } }
// NOTE: non-streaming version, kept for compatibility.
export function sendMessage(threadId, text, imageFiles) {
  const form = new FormData()
  form.append('thread_id', threadId)
  if (text) form.append('text', text)
  if (imageFiles && imageFiles.length) {
    for (const f of imageFiles) form.append('images', f)
  }
  return http.post('/chat', form, {
    headers: { 'Content-Type': 'multipart/form-data' }
  }).then(r => r.data)
}

// Streaming chat via SSE over a POST multipart request.
//
// Why fetch instead of EventSource: the native EventSource API only does GET
// and cannot send a multipart body (needed for image upload), so we POST with
// fetch and manually parse the SSE text stream from response.body.
//
// Backend contract (POST /api/chat/stream, Content-Type text/event-stream):
//   - streams token chunks as:   data: {"type":"token","content":"..."}


//   - signals completion as:      data: {"type":"done","created_at":"..."}


//   - signals an error as:        data: {"type":"error","message":"..."}


// (Plain-text chunks without the JSON envelope are also tolerated and treated
//  as tokens, so a simpler backend that just yields text still works.)
//
// Params:
//   threadId, text, imageFiles  — same as sendMessage
//   handlers = { onToken(str), onDone(meta), onError(err) }
// Returns: a function to abort the stream.
export function sendMessageStream(threadId, text, imageFiles, handlers = {}) {
  const { onToken, onDone, onError } = handlers
  const controller = new AbortController()

  const form = new FormData()
  form.append('thread_id', threadId)
  if (text) form.append('text', text)
  if (imageFiles && imageFiles.length) {
    for (const f of imageFiles) form.append('images', f)
  }

  ;(async () => {
    try {
      const resp = await fetch('/api/chat/stream', {
        method: 'POST',
        body: form,
        headers: { Accept: 'text/event-stream' },
        signal: controller.signal
      })
      if (!resp.ok || !resp.body) {
        let detail = `HTTP ${resp.status}`
        try {
          const j = await resp.json()
          detail = j.detail || j.message || detail
        } catch (_) { /* body not json */ }
        throw new Error(detail)
      }

      const reader = resp.body.getReader()
      const decoder = new TextDecoder('utf-8')
      let buffer = ''
      let doneMeta = null

      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        // SSE events are separated by a blank line.
        let sep
        while ((sep = buffer.indexOf('\n\n')) !== -1) {
          const rawEvent = buffer.slice(0, sep)
          buffer = buffer.slice(sep + 2)
          handleEvent(rawEvent)
        }
      }
      // flush any trailing event without a blank line terminator
      if (buffer.trim()) handleEvent(buffer)

      onDone && onDone(doneMeta || {})

      function handleEvent(rawEvent) {
        // collect all `data:` lines of this event
        const dataLines = rawEvent
          .split('\n')
          .filter(l => l.startsWith('data:'))
          .map(l => l.slice(5).replace(/^ /, ''))
        if (!dataLines.length) return
        const payload = dataLines.join('\n')
        if (payload === '[DONE]') return

        let parsed = null
        try { parsed = JSON.parse(payload) } catch (_) { /* plain text */ }

        if (parsed && typeof parsed === 'object') {
          if (parsed.type === 'token' || parsed.type === 'delta') {
            onToken && onToken(parsed.content ?? parsed.delta ?? '')
          } else if (parsed.type === 'done') {
            doneMeta = parsed
          } else if (parsed.type === 'error') {
            throw new Error(parsed.message || 'stream error')
          } else if (typeof parsed.content === 'string') {
            onToken && onToken(parsed.content)
          }
        } else {
          // plain text chunk -> treat as a token
          onToken && onToken(payload)
        }
      }
    } catch (err) {
      if (controller.signal.aborted) return
      onError && onError(err)
    }
  })()

  return () => controller.abort()
}
