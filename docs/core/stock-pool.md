# stock-pool

# 标的池设计 · 双池 SoT

> 双池架构完整说明。所有 SoT 在 yaml · DB 仅镜像。codex 上手前读。
> 

## 1. 两个池的定位

| 项 | M 池 | A 池 |
| --- | --- | --- |
| 含义 | 未拥有 · 只走 β 信号 | 已拥有 / 却思考入场 · thesis 驱动 |
| 规模 | ~1700 · 自动 curate | 5-15 · 手动 |
| SoT | etf_holdings + m_pool_overrides.yaml | a_pool.yaml |
| 信号 | 主题主导 · ETF Top 3 推送 | 12 类个股信号 · R:R |
| 考须现多久 | 每周 sync | 手动 vim |

## 2. M 池 curation

- 上游：etf_holdings（SPY/QQQ/主题 ETF）交集
- 过滤：市值 > 1B / ADV > 1M / 上市 > 1Y
- override：`config/m_pool_overrides.yaml`
    - `forced_in: []` · 手动加
    - `forced_out: []` · 手动去
- CLI：`uv run --package usstock-data usstock-data universe sync`

## 3. A 池 SoT · a_pool.yaml

```yaml
# config/a_pool.yaml
- symbol: LITE
  status: active            # active / watching / paused / archived
  added: 2026-04-29
  thesis_stop_mcap_b: 4.5    # thesis 失效市值 (B USD)
  target_mcap_b:    18.0     # 3-5y 目标市值 (B USD)
  thesis_summary: |
    AI 数据中心光互联龙头 · 800G/1.6T 升级周期
  themes: [theme_ai_compute, theme_optical_module]   # 必 ∈ themes.yaml.keys()
```

### 字段说明

- `status`：active=产生信号 · watching=只看不产生 · paused=暂停 · archived=归档
- `thesis_stop_mcap_b` / `target_mcap_b`：市值锁 · 拆股增发免疫
- 价格反推：`thesis_stop_price = thesis_stop_mcap_b * 1e9 / shares_outstanding`
- `themes[]`：多标签 · 仅 ∈ themes.yaml 注册词
- `thesis_summary`：人读·走 Discord payload 上下文

### 入池门槛（人定）

- 业务有驱动逻辑且在主题上 · 不是单纯动量
- 与 M 池主题交集不足以表达 · 需个股跳出
- 能寫出 [thesis-XXX.md](http://thesis-XXX.md) 主体。写不出 = 不加

## 4. themes SoT · themes.yaml

```yaml
# config/themes.yaml
themes:
  - id: theme_ai_compute
    name: AI Compute
    description: GPU/ASIC · 训练推理算力
    etfs: [SMH, SOXX, AIQ]
  - id: theme_semiconductor
    name: Semiconductor
    ...
```

- 31 主题 · 顶 8：ai_compute / semiconductor / gpu / megacap_tech / enterprise_software / cybersecurity / cloud_infra / clean_energy
- codex 从 etf_holdings 反推草案 → 用户 review → PR merge → `themes sync`
- a_pool.yaml.themes 未注册 → universe sync fail-fast 含行号

## 5. DB 镜像资产

```sql
-- symbol_universe (V5.7 schema)
pool                    TEXT    -- 'm' | 'a'
is_active               BOOLEAN
thesis_added_at         DATE    -- A 池不为NULL
-- 以下 NOT 存在于 DB，V5.7 明确仅 yaml SoT：
--   thesis_stop_mcap_b / target_mcap_b / themes / thesis_summary
```

## 6. 池变更走法

- M 池：编 m_pool_overrides.yaml → PR merge → `universe sync`
- A 池：编 a_pool.yaml + [thesis-XXX.md](http://thesis-XXX.md) → PR merge → `universe sync` + Codex 补股本

## 7. 跨表一致性

- `quotes_daily`、`daily_indicators`、`themes_score_daily` 都走 symbol_universe 全集
- A 池 ⊆ M 池（现阶段）· a 池可以超 m 池范围 但需重新 ETL
- m 池删但 a 池还在 → protect · 不物理删 universe

## 8. shares_outstanding

- ETL 每周五拉取 · 存 `symbol_universe.shares_outstanding`
- NULL → hold + alert WARN · 不静默

## 9. CLI 参考

```bash
usstock-data universe list             # 看现状
usstock-data universe show LITE        # 单股详情
usstock-data universe sync             # 同步 yaml → DB
usstock-data universe a-pool           # 只同步 a 池
usstock-data universe add LITE --pool a
usstock-data universe set-target LITE --target-mcap-b 18.0
usstock-data universe remove LITE --pool a
```