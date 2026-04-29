from __future__ import annotations

from usstock_analytics.signals.m_pool import breadth, dial, macro, orchestrate, sector, stock, theme


def test_m_pool_modules_import() -> None:
    assert breadth.BreadthRow
    assert dial.RegimeState
    assert sector.SectorSignal
    assert theme.ThemeSignal
    assert stock.StockSignal
    assert macro.MacroResult
    assert callable(orchestrate.run_signal_engine)
