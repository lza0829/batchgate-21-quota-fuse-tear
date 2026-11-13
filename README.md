# 02-batchgate（闸序）

Batchgate — 离线作业依赖编排：作业定义 → 依赖就绪检查 → 执行/失败重试 → 产出水位与对账。

与 Feedstitch（多源 Feed 归并）主链路不同，禁止做成 Feed 解析/冲突/回看换皮。

## 启动

```bash
docker compose up --build
```

| 入口 | 地址 |
| --- | --- |
| 前端 | http://localhost:5200 |
| API | http://localhost:10200 |

## 主链

配置作业与依赖 → 触发一次编排 Run → 按依赖顺序执行夹具作业 → 写入尝试记录与产出水位 → 报告对账 → 扣费入账单并校验一致性

## 成本与配额熔断

- **成本**：每个作业可配 `cost_weight`（权重）或 `fixed_cost`（固定费用，优先）。单次执行成本 = `fixed_cost`，否则 `cost_weight × unit_price`（单价全局配置）。取整到分（四舍五入）。
- **累计**：编排过程中逐作业累计本趟成本，写入 `orchestrations.cost_total`；每次成功执行写一条 `cost_ledger` 扣费行，`attempt_id` 与尝试记录一一对应。
- **配额**：`quota_scope=run`（只算本趟）或 `global`（跨所有编排累计）；`quota_limit` 留空表示不设闸。
- **熔断策略（固定）**：作业开始前先估成本。若 `已用 + 本次成本 > 配额`，该作业记 `skipped_fuse` 并**锁闸**；此后同趟内所有尚未开始的作业（无论依赖是否满足）一律记 `skipped_fuse`，不再开新作业。已执行的作业不回滚、水位保留、扣费保留。
- **对账**：`GET /api/orchestrations/{id}/reconcile` 以尝试记录与账单明细为事实源，核对报告里的 `attempt_count` / `ledger_entry_count` / `cost_total` / `succeeded` / `skipped_fuse`。所有状态都在 SQLite，刷新与重启后保留。

页面：作业页改成本，配额页改配额/单价，编排台看累计成本与熔断原因，账单明细页看逐条扣费与对账。

## 种子说明

- **ingest_orders**：无依赖，写出订单水位，权重 1。
- **dim_customer**：无依赖，写出客户维表水位，权重 2。
- **fact_order_daily**：依赖上两者成功且水位推进后才可执行（底座仅做“上游成功”检查，严格水位闸与重试预算留给 0-1 题），权重 3。

## 技术栈

Python 3.12 + FastAPI + SQLite；Vue 3 + Vite + Nginx。

## 0-1 切口（未实现）

`dep_gate` / `retry_budget` / `watermark_reconcile` / `sla_breach`
