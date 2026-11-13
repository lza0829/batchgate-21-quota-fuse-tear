<script setup>
import { onMounted, ref } from 'vue'
import { getJSON, patchJSON } from '../api'
const rows = ref([])
const msg = ref('')
const err = ref('')
async function refresh() {
  const raw = await getJSON('/api/jobs')
  rows.value = raw.map(j => ({ ...j, fixed_cost_input: j.fixed_cost == null ? '' : String(j.fixed_cost) }))
}
async function saveAttempts(row) {
  err.value = ''; msg.value = ''
  try {
    await patchJSON(`/api/jobs/${row.id}/max-attempts`, { max_attempts: Number(row.max_attempts) || 1 })
    msg.value = `已保存 ${row.name} 的 max_attempts`
    await refresh()
  } catch (e) { err.value = String(e.message || e) }
}
async function saveCost(row) {
  err.value = ''; msg.value = ''
  try {
    const fixedRaw = String(row.fixed_cost_input ?? '').trim()
    await patchJSON(`/api/jobs/${row.id}/cost`, {
      cost_weight: Number(row.cost_weight) || 0,
      fixed_cost: fixedRaw === '' ? null : Number(fixedRaw),
    })
    msg.value = `已保存 ${row.name} 的成本设置`
    await refresh()
  } catch (e) { err.value = String(e.message || e) }
}
onMounted(async () => {
  try { await refresh() } catch (e) { err.value = String(e.message || e) }
})
function fmt(n) { return Number(n ?? 0).toFixed(2) }
</script>
<template>
  <div class="page">
    <h1>作业</h1>
    <p class="muted">查看依赖、尝试次数与成本；成本按固定费用（优先）或 权重 × 单价 计。</p>
    <p v-if="err" class="tag danger">{{ err }}</p>
    <p v-if="msg" class="tag ok">{{ msg }}</p>
    <div class="panel">
      <table>
        <thead>
          <tr>
            <th>ID</th><th>名称</th><th>依赖</th><th>max_attempts</th>
            <th>成本权重</th><th>固定费</th><th>本趟计费</th><th>夹具</th><th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="j in rows" :key="j.id">
            <td>{{ j.id }}</td>
            <td class="mono">{{ j.name }}</td>
            <td class="mono">{{ j.depends_on.join(', ') || '—' }}</td>
            <td><input type="number" min="1" max="10" v-model.number="j.max_attempts" style="width:4.5rem" /></td>
            <td>
              <input type="number" min="0" step="0.1" v-model.number="j.cost_weight"
                     :disabled="j.fixed_cost != null" style="width:5rem" />
            </td>
            <td>
              <input type="number" min="0" step="0.01" v-model="j.fixed_cost_input"
                     placeholder="留空=按权重" style="width:6.5rem" />
            </td>
            <td>
              <strong>¥{{ fmt(j.cost_estimate) }}</strong>
              <span class="tag" :class="j.cost_mode === 'fixed' ? 'warn' : ''">
                {{ j.cost_mode === 'fixed' ? '固定' : '权重' }}
              </span>
            </td>
            <td class="mono">{{ j.fixture_path }}</td>
            <td class="actions">
              <button class="secondary" @click="saveAttempts(j)">存次数</button>
              <button @click="saveCost(j)">存成本</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
<style scoped>
.actions { display: flex; gap: 0.35rem; white-space: nowrap; }
</style>
