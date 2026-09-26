import csv
import io
from pathlib import Path

from test_study_coach import _admin, _client, _publish_pack, _slide


def test_study_progress_export_requires_course_and_downloads_csv(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        endpoint = "/api/v1/admin/study/courses/missing/progress.csv"
        assert client.get(endpoint).status_code == 401
        admin = _admin(client)
        missing = client.get(endpoint)
        assert missing.status_code == 404
        assert missing.json() == {"detail": {"code": "STUDY_COURSE_NOT_FOUND"}}
        pack = _publish_pack(client, admin, _slide(client))
        course = client.post(
            "/api/v1/admin/study/courses",
            headers=admin,
            json={
                "packId": pack["id"],
                "title": "Export course",
                "retentionDays": 30,
                "learnerLimit": 2,
            },
        )
        assert course.status_code == 201
        course_id = course.json()["id"]
        response = client.get(f"/api/v1/admin/study/courses/{course_id}/progress.csv")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")
        assert (
            response.headers["content-disposition"]
            == f'attachment; filename="study-progress-{course_id}.csv"'
        )
        rows = list(csv.reader(io.StringIO(response.text)))
        assert len(rows) == 1
        assert rows[0][:3] == ["pseudonym", "task_id", "status"]
