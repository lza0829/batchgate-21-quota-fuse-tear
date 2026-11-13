<script setup>
import { onMounted, ref } from 'vue'
import { getJSON, postJSON } from '../api'
const history = ref([])
const last = ref(null)
const quota = ref(null)
const busy = ref(false)
const err = ref('')
async function refresh() {
  history.value = await getJSON('/api/orchestrations')
  quota.value = await getJSON('/api/quota')
}
async function runOnce() {
  err.value = ''; busy.value = true
  try {
    last.value = await postJSON('/api/orchestrations')
    await refresh()
  } catch (e) { err.value = String(e.message || e) }
  finally { busy.value = false }
}
onMounted(async () => {
  try { await refresh() } catch (e) { err.value = String(e.message || e) }
})
function fmt(n) { return Number(n ?? 0).toFixed(2) }
function statusClass(s) {
  return s === 'ok' ? 'ok' : (s === 'fused' ? 'danger' : (s === 'partial' ? 'warn' : ''))
}
function fuseReason(o) {
  const r = o.report || {}
  if (r.fuse_trigger) return `触发：${r.fuse_trigger}`
  if (r.fused) return '配额已熔断'
  return '—'
}
</script>
<template>
  <div class="page">
    <h1>编排台</h1>
    <p class="muted">
      触发一次全图编排：按依赖层执行；上游未成功则下游记 skipped_dep；额度不够则记 skipped_fuse 并锁闸不再开新作业。
    </p>
    <div class="panel" v-if="quota">
      <span class="tag" :class="quota.quota_limit == null ? '' : 'warn'">
        {{ quota.quota_scope === 'global' ? '全局配额' : '本趟配额' }}
      </span>
      <span class="mono" style="margin-left:0.5rem">
        {{ quota.quota_limit == null ? '不设闸' : `上限 ¥${fmt(quota.quota_limit)}` }}
      </span>
      <span class="muted" style="margin-left:0.75rem">单价 ¥{{ fmt(quota.unit_price) }}</span>
      <span class="muted" style="margin-left:0.75rem">全局已花 ¥{{ fmt(quota.global_spent) }}</span>
      <router-link to="/quota" style="margin-left:0.75rem">调整配额 →</router-link>
    </div>
    <div class="panel">
      <button :disabled="busy" @click="runOnce">{{ busy ? '编排中…' : '执行编排' }}</button>
    </div>
    <p v-if="err" class="tag danger">{{ err }}</p>
    <div class="panel" v-if="last">
      <h3>最近一次报告 #{{ last.id }}</h3>
      <p>
        <span class="tag" :class="statusClass(last.status)">{{ last.status }}</span>
        · 成功 {{ last.report?.succeeded }} ·
        失败 {{ last.report?.failed }} ·
        跳过 {{ last.report?.skipped }}（熔断 {{ last.report?.skipped_fuse }} / 依赖 {{ last.report?.skipped_dep }}）
      </p>
      <p>
        本趟累计成本 <strong>¥{{ fmt(last.report?.cost_total) }}</strong>
        · 扣费 {{ last.report?.ledger_entry_count }} 条
        · 配额 {{ last.report?.quota_scope === 'global' ? '全局' : '本趟' }}
        {{ last.report?.quota_limit == null ? '不设闸' : `上限 ¥${fmt(last.report.quota_limit)}` }}
        <span v-if="last.report?.quota_remaining != null">· 剩余 ¥{{ fmt(last.report.quota_remaining) }}</span>
      </p>
      <p v-if="last.report?.fused" class="tag danger" style="display:block">
        熔断原因：{{ fuseReason({ report: last.report }) }}；已锁闸：
        <span class="mono">{{ (last.report.fuse_jobs || []).join(', ') || '—' }}</span>
      </p>
      <p class="mono muted">watermarked_jobs={{ last.report?.watermarked_jobs }} layers={{ last.report?.layer_count }}</p>
      <p>
        <router-link :to="{ path: '/attempts', query: { orchestration_id: last.id } }">查看本次尝试 →</router-link>
        ·
        <router-link :to="{ path: '/ledger', query: { orchestration_id: last.id } }">账单明细与对账 →</router-link>
        ·
        <router-link to="/watermarks">产出水位 →</router-link>
      </p>
    </div>
    <div class="panel">
      <h3>历史编排</h3>
      <table>
        <thead>
          <tr><th>ID</th><th>状态</th><th>成功</th><th>失败</th><th>跳过</th><th>累计成本</th><th>熔断</th><th>配额</th><th>开始</th></tr>
        </thead>
        <tbody>
          <tr v-for="o in history" :key="o.id">
            <td>{{ o.id }}</td>
            <td><span class="tag" :class="statusClass(o.status)">{{ o.status }}</span></td>
            <td>{{ o.report?.succeeded }}</td>
            <td>{{ o.report?.failed }}</td>
            <td>{{ o.report?.skipped }}</td>
            <td class="mono">¥{{ fmt(o.cost_total) }}</td>
            <td class="mono">{{ o.skipped_fuse ? `${o.skipped_fuse} · ${fuseReason(o)}` : '—' }}</td>
            <td class="mono">{{ o.quota_scope || '—' }} / {{ o.quota_limit == null ? '不设闸' : fmt(o.quota_limit) }}</td>
            <td class="mono">{{ o.started_at }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
