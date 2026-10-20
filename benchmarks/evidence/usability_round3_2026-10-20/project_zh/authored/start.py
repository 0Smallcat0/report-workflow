from pathlib import Path
SRC = str(Path(__file__).resolve().parent.parent / "sources")
START = dict(prompt="幫我把高二自主學習的成果寫成申請大學用的專題報告：教室二氧化碳濃度和上課專注度有沒有關係，開窗有沒有差",
    source_files=[{"path": f"{SRC}/教室CO2紀錄.csv", "role": "source_data"}, {"path": f"{SRC}/研究筆記.md", "role": "source_data"}],
    report_profile="admissions_project_report", title="教室二氧化碳濃度與上課專注度之關係",
    author_block="王小明", affiliation_block="市立高中二年級", preflight_confirmed=True,
    preflight_decisions={"confirmed_by_user": True, "install_decisions": {}, "feature_decisions": {"web_research": "skip", "notebook_sync": "skip"}})
