<script setup>
import { computed, onMounted, ref } from 'vue'
import { getJSON, putJSON } from '../api'

const quota = ref(null)
const scope = ref('run')
const limit = ref('')
const unitPrice = ref('1.00')
const msg = ref('')
const err = ref('')
const busy = ref(false)

async function load() {
  quota.value = await getJSON('/api/quota')
  scope.value = quota.value.quota_scope
  limit.value = quota.value.quota_limit == null ? '' : Number(quota.value.quota_limit).toFixed(2)
  unitPrice.value = Number(quota.value.unit_price).toFixed(2)
}

async function save() {
  err.value = ''; msg.value = ''; busy.value = true
  try {
    const raw = String(limit.value).trim()
    quota.value = await putJSON('/api/quota', {
      quota_scope: scope.value,
      quota_limit: raw === '' ? null : Number(raw),
      unit_price: Number(unitPrice.value) || 0,
    })
    msg.value = '配额设置已保存'
    await load()
  } catch (e) { err.value = String(e.message || e) }
  finally { busy.value = false }
}

const limitHint = computed(() =>
  scope.value === 'global'
    ? '累计所有编排的扣费；本趟起点的已花额度会先扣掉。'
    : '只统计本趟编排内的扣费，新一趟从零开始。'
)

function fmt(n) { return Number(n ?? 0).toFixed(2) }

onMounted(async () => {
  try { await load() } catch (e) { err.value = String(e.message || e) }
})
</script>

<template>
  <div class="page">
    <h1>配额与单价</h1>
    <p class="muted">成本 = 固定费用（优先）或 权重 × 单价。配额为空表示不设闸。</p>
    <p v-if="err" class="tag danger">{{ err }}</p>
    <p v-if="msg" class="tag ok">{{ msg }}</p>
    <div class="panel" v-if="quota">
      <div class="grid">
        <label>
          单价（每单位权重）
          <input type="number" min="0" step="0.01" v-model="unitPrice" />
        </label>
        <label>
          配额范围
          <select v-model="scope">
            <option value="run">本趟（run）</option>
            <option value="global">全局（global）</option>
          </select>
        </label>
        <label>
          配额上限
          <input type="number" min="0" step="0.01" v-model="limit" placeholder="留空 = 不设闸" />
        </label>
      </div>
      <p class="muted">{{ limitHint }}</p>
      <button :disabled="busy" @click="save">{{ busy ? '保存中…' : '保存' }}</button>
      <p class="muted" style="margin-top:0.75rem">
        全局已花 ¥{{ fmt(quota.global_spent) }}
        <span v-if="quota.global_remaining != null">· 全局剩余 ¥{{ fmt(quota.global_remaining) }}</span>
      </p>
    </div>
  </div>
</template>

<style scoped>
.grid { display: flex; gap: 1.25rem; flex-wrap: wrap; margin-bottom: 0.5rem; }
.grid label { display: flex; flex-direction: column; gap: 0.3rem; font-size: 0.9rem; }
</style>
