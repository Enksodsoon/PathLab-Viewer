import pytest

from scripts.validate_caddy_boundaries import validate


def route(paths, handlers):
    return {"match": [{"path": paths}], "handle": handlers}


def config(routes):
    return {"apps": {"http": {"servers": {"site": {"routes": routes}}}}}


def test_effective_internal_denials_precede_backend_and_web_handlers():
    deny = [{"handler": "subroute", "routes": [
        {"handle": [{"handler": "static_response", "status_code": 404}]},
    ]}]
    validate(config([
        route(["/api/v1/internal/*", "/_pathlab_ome/*"], deny),
        route(["/api/*"], [{"handler": "reverse_proxy"}]),
        {"handle": [{"handler": "file_server"}]},
    ]))


@pytest.mark.parametrize("exposed_path", ["/api/*", "/_pathlab_ome/*"])
def test_late_deny_does_not_hide_an_earlier_delivery_handler(exposed_path):
    with pytest.raises(ValueError, match="before its deny response"):
        validate(config([
            route([exposed_path], [{"handler": "reverse_proxy"}]),
            route(["/api/v1/internal/*", "/_pathlab_ome/*"], [
                {"handler": "static_response", "status_code": 404},
            ]),
        ]))


def test_missing_server_cannot_pass():
    with pytest.raises(ValueError, match="no HTTP server"):
        validate({})
