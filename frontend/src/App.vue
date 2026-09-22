<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'

type ConnectionState = 'loading' | 'ok' | 'error'
const state = ref<ConnectionState>('loading')
const message = ref('正在检查服务连接…')
const label = computed(() => ({ loading: '连接中', ok: '已连接', error: '连接失败' })[state.value])
let controller: AbortController | undefined

async function checkConnection() {
  controller?.abort()
  controller = new AbortController()
  const request = controller
  const timeout = window.setTimeout(() => request.abort(), 5000)
  state.value = 'loading'
  message.value = '正在检查服务连接…'

  try {
    const response = await fetch('/api/health', { signal: request.signal })
    if (!response.ok) throw new Error('Health request failed')
    const body: unknown = await response.json()
    if (typeof body !== 'object' || body === null || !('status' in body) || body.status !== 'ok') {
      throw new Error('Unexpected health response')
    }
    state.value = 'ok'
    message.value = '服务已就绪，可以开始开发订单详情和物流查询功能。'
  } catch {
    state.value = 'error'
    message.value = '暂时无法连接服务，请确认后端已启动后重试。'
  } finally {
    window.clearTimeout(timeout)
  }
}

onMounted(checkConnection)
onUnmounted(() => controller?.abort())
</script>

<template>
  <main class="shell">
    <header>
      <p class="eyebrow">ORDER ASSESSMENT</p>
      <h1>订单详情与物流查询</h1>
      <p class="intro">项目已初始化。这里将集中展示订单商品、金额明细和配送进度。</p>
    </header>

    <section class="status-card" aria-labelledby="connection-title">
      <div class="status-header">
        <h2 id="connection-title">服务连接</h2>
        <span class="badge" :class="state">{{ label }}</span>
      </div>
      <p class="status-message" role="status" aria-live="polite">{{ message }}</p>
      <button type="button" :disabled="state === 'loading'" @click="checkConnection">重新检查</button>
    </section>

    <p class="note">当前为初始化版本，尚未导入订单或接入物流服务。</p>
  </main>
</template>
