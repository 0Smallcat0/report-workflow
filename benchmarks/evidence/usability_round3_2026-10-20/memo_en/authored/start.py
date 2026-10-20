from pathlib import Path
SRC = str(Path(__file__).resolve().parent.parent / "sources")
START = dict(prompt="Write an internal research memo on whether our 20-day momentum signal predicts next-week returns of the sector ETF basket, and whether it holds in both regimes",
    source_files=[{"path": f"{SRC}/momentum_backtest.csv", "role": "source_data"}, {"path": f"{SRC}/test_notes.md", "role": "source_data"}],
    report_profile="quant_research_memo", title="Does the 20-Day Momentum Signal Predict Next-Week Basket Returns?",
    author_block="Quant Research Desk", preflight_confirmed=True,
    preflight_decisions={"confirmed_by_user": True, "install_decisions": {}, "feature_decisions": {"web_research": "skip", "notebook_sync": "skip"}})
