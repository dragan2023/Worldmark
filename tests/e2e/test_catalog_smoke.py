from tests.factories import create_landmark


def test_catalog_page_has_filter_and_export_entry(client, db_session):
    create_landmark(db_session)

    response = client.get("/games?work=悟空&country=CN")

    assert response.status_code == 200
    assert "黑神话：悟空" in response.text
    assert "导出 CSV" in response.text
    assert "详细地址" in response.text
    assert "交通说明" not in response.text
    assert "name=\"city\"" in response.text


def test_catalog_page_explains_empty_work_result(client):
    response = client.get("/games?work=不存在的游戏")

    assert response.status_code == 200
    assert "该作品暂无已发布地点。" in response.text


def test_work_page_lists_its_landmarks(client, db_session):
    first = create_landmark(db_session, landmark_name="应县木塔")
    create_landmark(db_session, landmark_name="小西天", ip_work=first.ip_work)

    response = client.get(f"/works/{first.ip_work_id}")

    assert response.status_code == 200
    assert "黑神话：悟空" in response.text
    assert "应县木塔" in response.text
    assert "小西天" in response.text
    assert "相关地标" in response.text
