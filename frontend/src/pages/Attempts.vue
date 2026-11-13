<script setup>
import { onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { getJSON } from '../api'
const route = useRoute()
const orchId = ref(null)
const orchList = ref([])
const rows = ref([])
const err = ref('')
async function load() {
  err.value = ''
  try {
    const q = orchId.value != null ? `?orchestration_id=${orchId.value}` : ''
    rows.value = await getJSON(`/api/attempts${q}`)
  } catch (e) { err.value = String(e.message || e) }
}
onMounted(async () => {
  try {
    orchList.value = await getJSON('/api/orchestrations')
    const q = Number(route.query.orchestration_id)
    if (q) orchId.value = q
    await load()
  } catch (e) { err.value = String(e.message || e) }
})
watch(orchId, load)
function cls(s) { return s === 'success' ? 'ok' : (s === 'failed' ? 'danger' : 'warn') }
function cost(d) {
  const a = d?.cost?.amount
  return a == null ? '—' : `¥${Number(a).toFixed(2)}`
}
function skipReason(d) {
  if (d?.reason) return d.reason
  return JSON.stringify(d)
}
</script>
<template>
  <div class="page">
    <h1>尝试记录</h1>
    <p class="muted">每次作业尝试的状态：success / failed / skipped_dep / skipped_fuse。成功执行会同时写入一条账单明细。</p>
    <p v-if="err" class="tag danger">{{ err }}</p>
    <div class="panel">
      <label>
        编排
        <select v-model.number="orchId">
          <option :value="null">全部</option>
          <option v-for="o in orchList" :key="o.id" :value="o.id">
            #{{ o.id }} · {{ o.status }} · ¥{{ Number(o.cost_total ?? 0).toFixed(2) }}
          </option>
        </select>
      </label>
      <span class="muted" style="margin-left:0.75rem">共 {{ rows.length }} 条</span>
    </div>
    <div class="panel">
      <table>
        <thead><tr><th>ID</th><th>编排</th><th>作业</th><th>次</th><th>状态</th><th>扣费</th><th>详情</th></tr></thead>
        <tbody>
          <tr v-for="a in rows" :key="a.id">
            <td>{{ a.id }}</td>
            <td>{{ a.orchestration_id }}</td>
            <td class="mono">{{ a.job_name }}</td>
            <td>{{ a.attempt_no }}</td>
            <td><span class="tag" :class="cls(a.status)">{{ a.status }}</span></td>
            <td class="mono">{{ cost(a.detail) }}</td>
            <td class="mono">
              <template v-if="a.status === 'skipped_fuse'">{{ skipReason(a.detail) }}</template>
              <template v-else>{{ JSON.stringify(a.detail) }}</template>
            </td>
          </tr>
          <tr v-if="!rows.length"><td colspan="7" class="muted">暂无记录。</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
