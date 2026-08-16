import csv
import io

from openpyxl import load_workbook
from sqlalchemy import select

from app.models.export_event import ExportEvent
from tests.factories import create_landmark


def test_csv_export_contains_only_published_results_and_audits_event(client, db_session):
    create_landmark(db_session, landmark_name="可导出地点")
    create_landmark(db_session, work_title="候选", landmark_name="不可导出地点", published=False)

    response = client.get("/api/v1/exports/landmarks.csv?ip_type=game")

    assert response.status_code == 200
    rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert rows[0] == ["作品名称", "地标名称", "国家/地区", "详细地址", "地标简介", "信息更新时间"]
    assert rows[1][1] == "可导出地点"
    assert len(rows) == 2
    event = db_session.scalar(select(ExportEvent))
    assert event is not None
    assert event.actor_kind == "anonymous"
    assert event.result_count == 1


def test_xlsx_export_and_empty_filter_response(client, db_session):
    create_landmark(db_session, landmark_name="XLSX 地点")

    response = client.get("/api/v1/exports/landmarks.xlsx?ip_type=game")
    workbook = load_workbook(io.BytesIO(response.content), read_only=True)
    worksheet = workbook.active

    assert response.status_code == 200
    assert worksheet["A1"].value == "作品名称"
    assert worksheet["B2"].value == "XLSX 地点"
    empty = client.get("/api/v1/exports/landmarks.csv?ip_type=literature")
    assert empty.status_code == 422
