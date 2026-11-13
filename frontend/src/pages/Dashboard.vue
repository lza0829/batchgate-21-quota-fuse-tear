<script setup>
import { onMounted, ref } from 'vue'
import { getJSON } from '../api'
const stats = ref(null)
const err = ref('')
onMounted(async () => {
  try { stats.value = await getJSON('/api/dashboard') } catch (e) { err.value = String(e.message || e) }
})
function fmt(n) { return Number(n ?? 0).toFixed(2) }
</script>
<template>
  <div class="page">
    <h1>总览</h1>
    <p class="muted">离线作业依赖编排：作业、编排、水位，以及累计成本与熔断次数。</p>
    <p v-if="err" class="tag danger">{{ err }}</p>
    <div class="panel" v-if="stats">
      <p>作业 {{ stats.job_count }}（启用 {{ stats.enabled_jobs }}）</p>
      <p>编排 {{ stats.orchestration_count }} · 尝试 {{ stats.attempt_count }}</p>
      <p>已有水位的作业 {{ stats.watermarked_jobs }}</p>
      <p>
        累计成本 <strong>¥{{ fmt(stats.total_cost) }}</strong> · 扣费 {{ stats.ledger_entries }} 条 ·
        熔断跳过 {{ stats.fuse_skips }} 次
      </p>
      <p class="mono muted">
        配额 {{ stats.quota_scope === 'global' ? '全局' : '本趟' }}
        {{ stats.quota_limit == null ? '不设闸' : `上限 ¥${fmt(stats.quota_limit)}` }}
        · 单价 ¥{{ fmt(stats.unit_price) }}
      </p>
      <p><router-link to="/ledger">账单明细 →</router-link> · <router-link to="/quota">配额设置 →</router-link></p>
    </div>
  </div>
</template>
