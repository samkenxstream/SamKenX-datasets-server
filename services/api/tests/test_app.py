# SPDX-License-Identifier: Apache-2.0
# Copyright 2022 The HuggingFace Authors.

from typing import Mapping, Optional

import pytest
from pytest_httpserver import HTTPServer
from starlette.testclient import TestClient

from api.app import create_app

from .utils import auth_callback


@pytest.fixture(scope="module")
def client(monkeypatch_session: pytest.MonkeyPatch) -> TestClient:
    return TestClient(create_app())


def test_cors(client: TestClient, first_dataset_endpoint: str) -> None:
    origin = "http://localhost:3000"
    method = "GET"
    header = "X-Requested-With"
    response = client.options(
        f"{first_dataset_endpoint}?dataset=dataset1",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": header,
        },
    )
    assert response.status_code == 200
    assert (
        origin in [o.strip() for o in response.headers["Access-Control-Allow-Origin"].split(",")]
        or response.headers["Access-Control-Allow-Origin"] == "*"
    )
    assert (
        header in [o.strip() for o in response.headers["Access-Control-Allow-Headers"].split(",")]
        or response.headers["Access-Control-Expose-Headers"] == "*"
    )
    assert (
        method in [o.strip() for o in response.headers["Access-Control-Allow-Methods"].split(",")]
        or response.headers["Access-Control-Expose-Headers"] == "*"
    )
    assert response.headers["Access-Control-Allow-Credentials"] == "true"


def test_get_valid_datasets(client: TestClient) -> None:
    response = client.get("/valid")
    assert response.status_code == 200
    assert "valid" in response.json()


# caveat: the returned status codes don't simulate the reality
# they're just used to check every case
@pytest.mark.parametrize(
    "headers,status_code,error_code",
    [
        ({"Cookie": "some cookie"}, 401, "ExternalUnauthenticatedError"),
        ({"Authorization": "Bearer invalid"}, 404, "ExternalAuthenticatedError"),
        ({}, 200, None),
    ],
)
def test_is_valid_auth(
    client: TestClient,
    httpserver: HTTPServer,
    hf_auth_path: str,
    headers: Mapping[str, str],
    status_code: int,
    error_code: Optional[str],
) -> None:
    dataset = "dataset-which-does-not-exist"
    httpserver.expect_request(hf_auth_path % dataset, headers=headers).respond_with_handler(auth_callback)
    response = client.get(f"/is-valid?dataset={dataset}", headers=headers)
    assert response.status_code == status_code
    assert response.headers.get("X-Error-Code") == error_code


def test_get_healthcheck(client: TestClient) -> None:
    response = client.get("/healthcheck")
    assert response.status_code == 200
    assert response.text == "ok"


def test_get_endpoint(client: TestClient, first_dataset_endpoint: str) -> None:
    # missing parameter
    response = client.get(first_dataset_endpoint)
    assert response.status_code == 422
    # empty parameter
    response = client.get(f"{first_dataset_endpoint}?dataset=")
    assert response.status_code == 422


@pytest.mark.parametrize(
    "dataset,config",
    [
        (None, None),
        ("a", None),
        ("a", ""),
    ],
)
def test_get_config_missing_parameter(
    client: TestClient,
    dataset: Optional[str],
    config: Optional[str],
    first_config_endoint: str,
) -> None:
    response = client.get(first_config_endoint, params={"dataset": dataset, "config": config, "split": None})
    assert response.status_code == 422


@pytest.mark.parametrize(
    "dataset,config,split",
    [
        (None, None, None),
        ("a", None, None),
        ("a", "b", None),
        ("a", "b", ""),
    ],
)
def test_get_split_missing_parameter(
    client: TestClient,
    dataset: Optional[str],
    config: Optional[str],
    split: Optional[str],
    first_split_endpoint: str,
) -> None:
    response = client.get(first_split_endpoint, params={"dataset": dataset, "config": config, "split": split})
    assert response.status_code == 422


def test_metrics(client: TestClient) -> None:
    response = client.get("/metrics")
    assert response.status_code == 200
    text = response.text
    lines = text.split("\n")
    metrics = {line.split(" ")[0]: float(line.split(" ")[1]) for line in lines if line and line[0] != "#"}

    # the middleware should have recorded the request
    name = 'starlette_requests_total{method="GET",path_template="/metrics"}'
    assert name in metrics, metrics
    assert metrics[name] > 0, metrics
