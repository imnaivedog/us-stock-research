# A 池 Thesis Reference

A 池 thesis 的业务判断属于用户。Codex 可以维护结构和 placeholder，但不能代填 `thesis_stop_mcap_b`、`target_mcap_b` 或 thesis 业务文字。

## 模板

```markdown
# Thesis · SYMBOL · Company

> Symbol: SYMBOL · Industry: ... · Priority: ... · Status: pending

## 1. 核心论点

- 论点 1，带证据。
- 论点 2。
- 论点 3。

## 2. 关键假设

- [ ] 假设 1，必须可证伪。
- [ ] 假设 2。
- [ ] 假设 3。

## 3. Catalysts

| Time | Event | Expected impact |
| --- | --- | --- |
| YYYY-MM | Example earnings | Market expectation vs actual |

## 4. 财务画像

- 收入增速：
- 毛利率：
- FCF：
- 净现金 / 净负债：
- 估值 vs 5Y 历史：
- 估值 vs peers：

## 5. 驱动与风险

| Drivers | Risks |
| --- | --- |
| Driver 1 | Risk 1 |
| Driver 2 | Risk 2 |

## 6. 目标与 Sunset

- 目标市值：
- 隐含上行空间：
- 时间窗口：
- Sunset condition 1：
- Sunset condition 2：

## 7. 技术参考

由 `a_pool_calibration` 生成；不要手工改生成值。

## 8. 决策日志

| Date | Action | Reason |
| --- | --- | --- |

## 9. 来源

- Filings：
- Research：
- Notes：
```

## YAML 片段形态

```yaml
- symbol: LITE
  status: watching
  added: 2026-04-29
  thesis_stop_mcap_b: <user-owned>
  target_mcap_b: <user-owned>
  thesis_summary: |
    <user-owned thesis text>
  themes: [theme_ai_compute, theme_optical_module]
```

当前系统文档允许的 status：`active`、`watching`、`removed`。只有 `active` 产生评分。

## 当前 placeholder

这里只是骨架。用户填写最终 thesis 数字和文字。

| Symbol | placeholder thesis | Themes |
| --- | --- | --- |
| LITE | AI data-center optical interconnect 龙头；800G/1.6T upgrade cycle。 | `theme_ai_compute`, `theme_optical_module` |
| COHR | Optical communications + laser 双轮；AI data-center transceiver demand。 | `theme_ai_compute`, `theme_optical_module` |
| MRVL | Data-center custom ASIC + optical DSP；AI compute chain。 | `theme_ai_compute`, `theme_semiconductor`, `theme_custom_silicon` |
| WDC | AI data-center HDD demand 与 nearline supply/demand imbalance。 | `theme_ai_compute`, `theme_storage` |
| SNDK | NAND cycle upturn + AI data-center SSD demand。 | `theme_ai_compute`, `theme_storage` |
