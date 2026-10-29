"""A statistic computed at intake has to be a quantity.

A course LCA's parameter sheet — name, value, unit, source — lists a heat value
in kcal/L beside an emission factor in kg CO2/TJ and a mileage in km. Intake
averaged the value column to 4,695.72, crossed it by source into a table of
means, and offered both as citable. The same run summarised a column of
publication years as "最小值 2,025 … 平均數 2,025" and averaged it inside a
cross table as "年份 平均 2,015.00".
"""
import json
import unittest
from datetime import datetime, timezone

from report_workflow.derived_evidence import dataset_summary_units

CREATED_AT = datetime(2026, 9, 15, tzinfo=timezone.utc).isoformat()


def _source(source_id, file_name, rows):
    return {
        "source_id": source_id, "file_name": file_name, "file_path": file_name, "file_type": "csv",
        "parsed_content": [{"block_type": "csv_row", "content": json.dumps(row, ensure_ascii=False)} for row in rows],
    }


PARAMETERS = _source("p1", "parameters.csv", [
    {"參數": "低位熱值", "數值": "7586", "單位": "kcal/L", "出處": "環境部"},
    {"參數": "CO2 排放係數", "數值": "69300", "單位": "kg CO2/TJ", "出處": "環境部"},
    {"參數": "年行駛里程", "數值": "11896", "單位": "km", "出處": "交通部"},
    {"參數": "電池容量", "數值": "53.4", "單位": "kWh", "出處": "ICCT"},
])
ONE_UNIT = _source("u1", "battery.csv", [
    {"車型": "A", "容量": "53.4", "單位": "kWh", "產地": "中國"},
    {"車型": "B", "容量": "75", "單位": "kWh", "產地": "中國"},
    {"車型": "C", "容量": "60", "單位": "kWh", "產地": "南韓"},
])
REGIONS = _source("r1", "regions.csv", [
    {"地區": "瑞典", "年份": "2015", "調查年": "2015", "電動車": "75.7", "判定": "green"},
    {"地區": "法國", "年份": "2015", "調查年": "2016", "電動車": "85.7", "判定": "green"},
    {"地區": "波蘭", "年份": "2015", "調查年": "2017", "電動車": "342.3", "判定": "red"},
    {"地區": "印度", "年份": "2015", "調查年": "2017", "電動車": "404.4", "判定": "red"},
])
METRICS = _source("m1", "metrics.csv", [
    {"指標": "準確率", "平均": "86.7", "單位": "%"},
    {"指標": "F1", "平均": "0.787", "單位": ""},
    {"指標": "找回率", "平均": "78.7", "單位": "%"},
    {"指標": "精確率", "平均": "79.0", "單位": "%"},
    {"指標": "單次推論", "平均": "0.24", "單位": "秒"},
    {"指標": "八次平均", "平均": "1.9", "單位": "秒"},
])


def _contents(source):
    return [unit["content"] for unit in dataset_summary_units([source], CREATED_AT, zh=True)]


class IntakeMeasureTests(unittest.TestCase):
    def test_a_value_column_in_several_units_is_not_averaged(self):
        contents = _contents(PARAMETERS)
        self.assertFalse([text for text in contents if "數值 欄共" in text or "數值 平均" in text or "數值 中位數" in text])
        # The categorical columns are still summarised.
        self.assertTrue([text for text in contents if "出處 欄共" in text])

    def test_one_unit_throughout_is_still_a_quantity(self):
        self.assertTrue([text for text in _contents(ONE_UNIT) if "容量 欄共 3 筆數值" in text])

    def test_a_year_is_counted_not_averaged_and_a_constant_is_not_a_distribution(self):
        contents = _contents(REGIONS)
        joined = "\n".join(contents)
        self.assertNotIn("年份 欄共", joined)
        self.assertNotIn("年份 平均", joined)
        self.assertNotIn("2,015", joined)
        self.assertNotIn("調查年 平均", joined)
        self.assertTrue([text for text in contents if "調查年 欄共 3 個相異值" in text])
        self.assertTrue([text for text in contents if "電動車 欄共 4 筆數值" in text])

    def test_the_unit_column_is_neither_a_distribution_nor_a_cross_table(self):
        units = dataset_summary_units([METRICS], CREATED_AT, zh=True)
        joined = "\n".join(unit["content"] for unit in units)
        self.assertNotIn("單位 欄共", joined)
        self.assertNotIn("單位 分組交叉表", joined)
        self.assertFalse([unit for unit in units if unit.get("table_grid")])


if __name__ == "__main__":
    unittest.main()
