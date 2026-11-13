<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { getJSON } from '../api'

const route = useRoute()
const orchId = ref(null)
const orchList = ref([])
const data = ref(null)
const allTotal = ref(null)
const recon = ref(null)
const err = ref('')
const busy = ref(false)

const charged = computed(() => (data.value?.entries || []).length)

async function load() {
  err.value = ''
  try {
    const q = orchId.value != null ? `?orchestration_id=${orchId.value}` : ''
    data.value = await getJSON(`/api/ledger${q}`)
    recon.value = orchId.value != null
      ? await getJSON(`/api/orchestrations/${orchId.value}/reconcile`)
      : null
    allTotal.value = (await getJSON('/api/ledger')).total_cost
  } catch (e) { err.value = String(e.message || e) }
}

onMounted(async () => {
  try {
    orchList.value = await getJSON('/api/orchestrations')
    const q = Number(route.query.orchestration_id)
    // default to the newest run so the reconciliation panel is always populated
    orchId.value = q || (orchList.value[0]?.id ?? null)
    await load()
  } catch (e) { err.value = String(e.message || e) }
})

watch(orchId, async () => { busy.value = true; await load(); busy.value = false })

function fmt(n) { return Number(n ?? 0).toFixed(2) }
</script>

<template>
  <div class="page">
    <h1>账单明细</h1>
    <p class="muted">每一条已执行作业的扣费记录；与本次编排的报告及尝试记录逐条对账。</p>
    <p v-if="err" class="tag danger">{{ err }}</p>

    <div class="panel">
      <label>
        编排
        <select v-model.number="orchId" :disabled="busy">
          <option v-for="o in orchList" :key="o.id" :value="o.id">
            #{{ o.id }} · {{ o.status }} · ¥{{ fmt(o.cost_total) }}
          </option>
        </select>
      </label>
      <span class="muted" style="margin-left:0.75rem">
        本段 {{ charged }} 条扣费 · 累计 ¥{{ fmt(data?.total_cost) }}
      </span>
      <span v-if="allTotal != null" class="muted" style="margin-left:0.75rem">
        全部编排累计 ¥{{ fmt(allTotal) }}
      </span>
    </div>

    <div class="panel" v-if="recon">
      <h3>对账（编排 #{{ recon.orchestration_id }}）</h3>
      <p>
        <span class="tag" :class="recon.consistent ? 'ok' : 'danger'">
          {{ recon.consistent ? '一致' : '不一致' }}
        </span>
      </p>
      <table>
        <thead><tr><th>指标</th><th>报告值</th><th>实际值</th><th>结果</th></tr></thead>
        <tbody>
          <tr v-for="(c, k) in recon.checks" :key="k">
            <td class="mono">{{ k }}</td>
            <td class="mono">{{ k === 'cost_total' ? fmt(c.report) : c.report }}</td>
            <td class="mono">{{ k === 'cost_total' ? fmt(c.actual) : c.actual }}</td>
            <td><span class="tag" :class="c.ok ? 'ok' : 'danger'">{{ c.ok ? '对得上' : '对不上' }}</span></td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="panel">
      <table>
        <thead>
          <tr><th>ID</th><th>编排</th><th>作业</th><th>尝试</th><th>模式</th><th>权重</th><th>固定费</th><th>单价</th><th>扣费</th><th>时间</th></tr>
        </thead>
        <tbody>
          <tr v-for="e in data?.entries || []" :key="e.id">
            <td>{{ e.id }}</td>
            <td>{{ e.orchestration_id }}</td>
            <td class="mono">{{ e.job_name }}</td>
            <td>{{ e.attempt_id }}</td>
            <td>{{ e.cost_mode === 'fixed' ? '固定' : '权重×单价' }}</td>
            <td>{{ e.cost_weight }}</td>
            <td>{{ e.fixed_cost == null ? '—' : fmt(e.fixed_cost) }}</td>
            <td>{{ fmt(e.unit_price) }}</td>
            <td><strong>¥{{ fmt(e.amount) }}</strong></td>
            <td class="mono">{{ e.created_at }}</td>
          </tr>
          <tr v-if="!charged">
            <td colspan="10" class="muted">暂无扣费记录。</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
