<script setup>
import { ref, reactive, nextTick, onMounted, onUnmounted, computed } from 'vue'
import {
  createConversation,
  listConversations,
  getConversation,
  deleteConversation,
  sendMessageStream
} from './api'

// ---------- state ----------
const conversations = ref([])      // sidebar list
const activeThreadId = ref(null)   // currently open thread_id
const messages = ref([])           // messages of the active conversation
const draftText = ref('')
const draftImages = reactive([])   // { file, url }
const sending = ref(false)       // true while a request is in flight (disables send button)
const loadingConv = ref(false)
const fileInput = ref(null)
const messagesEl = ref(null)
let abortStream = null           // closes the current SSE stream, if any

const activeTitle = computed(() => {
  const c = conversations.value.find(c => c.thread_id === activeThreadId.value)
  return c ? c.title : '私厨助手'
})

const canSend = computed(() =>
  !sending.value && activeThreadId.value &&
  (draftText.value.trim().length > 0 || draftImages.length > 0)
)

// ---------- helpers ----------
async function scrollToBottom() {
  await nextTick()
  if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight
}

async function refreshList() {
  const data = await listConversations()
  conversations.value = data.conversations || []
}

// ---------- actions ----------
async function onNewChat() {
  try {
    const conv = await createConversation()
    await refreshList()
    await openConversation(conv.thread_id)
  } catch (e) {
    alert('新建对话失败：' + errMsg(e))
  }
}

async function openConversation(threadId) {
  if (loadingConv.value) return
  loadingConv.value = true
  activeThreadId.value = threadId
  messages.value = []
  try {
    const data = await getConversation(threadId)
    messages.value = data.messages || []
    await scrollToBottom()
  } catch (e) {
    alert('加载对话失败：' + errMsg(e))
  } finally {
    loadingConv.value = false
  }
}

async function onDelete(threadId) {
  if (!confirm('确定删除这个对话吗？')) return
  try {
    await deleteConversation(threadId)
    if (activeThreadId.value === threadId) {
      activeThreadId.value = null
      messages.value = []
    }
    await refreshList()
  } catch (e) {
    alert('删除失败：' + errMsg(e))
  }
}

function pickImages() {
  fileInput.value?.click()
}

function onFilesSelected(e) {
  const files = Array.from(e.target.files || [])
  for (const f of files) {
    if (!f.type.startsWith('image/')) continue
    draftImages.push({ file: f, url: URL.createObjectURL(f) })
  }
  e.target.value = '' // allow re-selecting same file
}

function removeDraftImage(i) {
  URL.revokeObjectURL(draftImages[i].url)
  draftImages.splice(i, 1)
}

async function onSend() {
  if (!canSend.value) return
  const text = draftText.value.trim()
  const imgs = draftImages.map(d => d.file)
  const previewUrls = draftImages.map(d => d.url)
  const threadId = activeThreadId.value

  // optimistic user bubble
  messages.value.push({
    role: 'user',
    content: text,
    image_urls: previewUrls,
    created_at: new Date().toISOString()
  })
  draftText.value = ''
  draftImages.splice(0)
  sending.value = true

  // placeholder assistant bubble that gets filled in token by token
  const aiMsg = reactive({
    role: 'assistant',
    content: '',
    streaming: true,
    created_at: new Date().toISOString()
  })
  messages.value.push(aiMsg)
  await scrollToBottom()

  abortStream = sendMessageStream(threadId, text, imgs, {
    onToken: (chunk) => {
      aiMsg.content += chunk
      scrollToBottom()
    },
    onDone: async () => {
      aiMsg.streaming = false
      sending.value = false
      abortStream = null
      await refreshList() // title may update from first message
      await scrollToBottom()
    },
    onError: async (e) => {
      aiMsg.streaming = false
      if (!aiMsg.content) aiMsg.content = '出错了：' + errMsg(e)
      else aiMsg.content += '\n\n[输出中断：' + errMsg(e) + ']'
      sending.value = false
      abortStream = null
      await scrollToBottom()
    }
  })
}

function onStopGenerating() {
  if (abortStream) {
    abortStream()
    abortStream = null
    sending.value = false
    const last = messages.value[messages.value.length - 1]
    if (last && last.streaming) last.streaming = false
  }
}

function onKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    onSend()
  }
}

function errMsg(e) {
  return e?.response?.data?.detail || e?.response?.data?.message || e?.message || '未知错误'
}

onMounted(refreshList)
onUnmounted(() => {
  if (abortStream) abortStream()
})
</script>

<template>
  <div class="layout">
    <!-- Sidebar -->
    <aside class="sidebar">
      <div class="sidebar-head">
        <div class="brand">🍳 私厨助手</div>
        <button class="new-chat-btn" @click="onNewChat">＋ 新建对话</button>
      </div>
      <div class="conv-list">
        <div
          v-for="c in conversations"
          :key="c.thread_id"
          class="conv-item"
          :class="{ active: c.thread_id === activeThreadId }"
          @click="openConversation(c.thread_id)"
        >
          <span>💬</span>
          <span class="conv-title">{{ c.title || '新对话' }}</span>
          <button class="conv-del" @click.stop="onDelete(c.thread_id)" title="删除">🗑</button>
        </div>
        <div v-if="conversations.length === 0" class="empty-hint">
          还没有对话，点上面「新建对话」开始吧
        </div>
      </div>
    </aside>

    <!-- Chat panel -->
    <main class="chat">
      <div class="chat-head">{{ activeTitle }}</div>

      <div class="messages" ref="messagesEl">
        <template v-if="activeThreadId">
          <div
            v-for="(m, i) in messages"
            :key="i"
            class="msg"
            :class="m.role === 'user' ? 'user' : 'ai'"
          >
            <div class="avatar" :class="m.role === 'user' ? 'user' : 'ai'">
              {{ m.role === 'user' ? '🧑' : '🤖' }}
            </div>
            <div class="bubble">
              <img
                v-for="(url, j) in (m.image_urls || [])"
                :key="j"
                :src="url"
                class="msg-img"
                alt="食材图片"
              />
              <span v-if="m.content">{{ m.content }}</span>
              <span
                v-if="m.role === 'assistant' && m.streaming && !m.content"
                class="typing"
              >正在思考…</span>
              <span
                v-if="m.role === 'assistant' && m.streaming && m.content"
                class="stream-cursor"
              >▋</span>
            </div>
          </div>
        </template>

        <div v-else class="welcome">
          <h2>欢迎使用私厨助手</h2>
          <p>上传你手头的食材图片，或者直接描述，我来帮你想想today吃什么、怎么做。</p>
          <p style="margin-top:12px">点击左侧「＋ 新建对话」开始。</p>
        </div>
      </div>

      <!-- Composer -->
      <div class="composer" v-if="activeThreadId">
        <div class="preview-row" v-if="draftImages.length">
          <div class="preview-thumb" v-for="(d, i) in draftImages" :key="i">
            <img :src="d.url" alt="预览" />
            <button class="rm" @click="removeDraftImage(i)">×</button>
          </div>
        </div>
        <div class="composer-box">
          <button class="icon-btn" @click="pickImages" title="上传食材图片">🖼</button>
          <input
            ref="fileInput"
            type="file"
            accept="image/*"
            multiple
            style="display:none"
            @change="onFilesSelected"
          />
          <textarea
            v-model="draftText"
            rows="1"
            placeholder="描述你的食材或需求，支持纯文字 / 文字+图片 / 纯图片…"
            @keydown="onKeydown"
          ></textarea>
          <button
            v-if="!sending"
            class="send-btn"
            :disabled="!canSend"
            @click="onSend"
            title="发送"
          >➤</button>
          <button
            v-else
            class="send-btn stop-btn"
            @click="onStopGenerating"
            title="停止生成"
          >■</button>
        </div>
        <div class="hint">Enter 发送 · Shift+Enter 换行 · 可只发文字、只发图片或两者一起</div>
      </div>
    </main>
  </div>
</template>
