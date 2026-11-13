<script setup>
import { onMounted, ref } from 'vue'
import { getJSON, putJSON } from '../api'
import { useRouter } from 'vue-router'

const router = useRouter()
const rows = ref([])
const msg = ref('')
const err = ref('')
const draft = ref({})
const busy = ref(false)

async function refresh() {
  rows.value = await getJSON('/api/settings')
  draft.value = Object.fromEntries(rows.value.map(s => [s.key, s.value]))
}

async function save(key) {
  err.value = ''; msg.value = ''; busy.value = true
  try {
    await putJSON(`/api/settings/${key}`, { value: String(draft.value[key] ?? '') })
    msg.value = `已保存 ${key}`
    await refresh()
  } catch (e) { err.value = String(e.message || e) }
  finally { busy.value = false }
}

onMounted(async () => {
  try { await refresh() } catch (e) { err.value = String(e.message || e) }
})
const hints = {
  unit_price: '每单位成本权重的单价，决定权重计费模式下的扣费。',
  quota_scope: 'run（本趟）或 global（全局）。',
  quota_limit: '留空表示不设闸；达到或即将超限时按策略熔断跳过。',
  default_max_attempts: '种子作业的默认最大尝试次数。',
}
</script>
<template>
  <div class="page">
    <h1>设置</h1>
    <p class="muted">全局键值。成本单价与配额也可以直接在 <router-link to="/quota">配额页</router-link> 修改。</p>
    <p v-if="err" class="tag danger">{{ err }}</p>
    <p v-if="msg" class="tag ok">{{ msg }}</p>
    <div class="panel">
      <table>
        <thead><tr><th>key</th><th>value</th><th>说明</th><th></th></tr></thead>
        <tbody>
          <tr v-for="s in rows" :key="s.key">
            <td class="mono">{{ s.key }}</td>
            <td><input v-model="draft[s.key]" style="width:12rem" /></td>
            <td class="muted">{{ hints[s.key] || '—' }}</td>
            <td>
              <button v-if="s.key !== 'cost_seed_backfilled'" class="secondary"
                      :disabled="busy" @click="save(s.key)">保存</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
