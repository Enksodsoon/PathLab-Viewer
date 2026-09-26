import pytest
from test_library_v2 import _client, _headers
from wsi_viewer.database import session_factory
from wsi_viewer.models import Collection, Folder


@pytest.mark.parametrize("kind", ["folders", "collections"])
def test_library_sort_order_rejects_integer_overflow_without_changing_record(tmp_path, kind):
    with _client(tmp_path) as client:
        headers = _headers(client)
        response = client.post(f"/api/v2/admin/{kind}", json={"name": "Bounded"}, headers=headers)
        assert response.status_code == 201
        record_id = response.json()["id"]
        path = f"/api/v2/admin/{kind}/{record_id}"
        assert client.patch(path, json={"sortOrder": 2**31 - 1}, headers=headers).status_code == 200
        for invalid in (2**63, 2**31):
            response = client.patch(path, json={"sortOrder": invalid}, headers=headers)
            assert response.status_code == 422
        with session_factory(client.app.state.settings)() as database:
            record = database.get(Folder if kind == "folders" else Collection, record_id)
            assert record is not None and record.sort_order == 2**31 - 1
