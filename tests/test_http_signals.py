from typing import Any
from unittest.mock import ANY

import pytest
import requests_mock
from requests import Request, get, put

from ophyd_devices.utils.http_signal import HttpRestError, HttpRestSignal


@pytest.fixture(autouse=True)
def mock_server():
    with requests_mock.Mocker() as m:
        mock_data = "data"

        def get_cb(request, context):
            nonlocal mock_data
            return mock_data

        def put_cb(request, context):
            nonlocal mock_data
            mock_data = request.text

        def query_param_put_cb(request: Request, context):
            nonlocal mock_data
            pos = request.qs.get("position")
            if len(pos) != 1:
                context.reason = "wrong number of params"
                context.status_code = 422
                return
            pos = pos[0]
            if pos_valid(pos):
                context.reason = ""
                context.status_code = 202
                mock_data = pos
            else:
                context.reason = "out of range"
                context.status_code = 422

        def put_req_valid(request):
            return pos_valid(request.text)

        def pos_valid(val):
            try:
                val = int(val)
            except:
                return False
            return -50 < val < 50

        def put_can_fail_cb(request, context):

            context.reason = "" if put_req_valid(request) else "out of range"
            context.status_code = 202 if put_req_valid(request) else 422

        m.get("http://test.psi.ch/get_data", text=get_cb)
        m.put("http://test.psi.ch/put_data", text=put_cb)

        m.get("http://test.psi.ch/bad_get_endpoint", status_code=404, reason="test not found")
        m.put("http://test.psi.ch/put_can_fail", text=put_can_fail_cb)

        m.put("http://test.psi.ch/transform", text=query_param_put_cb)
        m.get("http://test.psi.ch/transform", text=get_cb)

        yield requests_mock


def test_signal_get():
    sig = HttpRestSignal(name="get", get_uri="http://test.psi.ch/get_data")
    assert sig.read() == {"get": {"timestamp": ANY, "value": "data"}}


def test_signal_put():
    sig = HttpRestSignal(
        name="put_get", get_uri="http://test.psi.ch/get_data", put_uri="http://test.psi.ch/put_data"
    )
    assert sig.read() == {"put_get": {"timestamp": ANY, "value": "data"}}
    sig.put("test_value")
    assert sig.read() == {"put_get": {"timestamp": ANY, "value": "test_value"}}


def test_bad_signal_get():
    sig = HttpRestSignal(name="get", get_uri="http://test.psi.ch/bad_get_endpoint")
    with pytest.raises(HttpRestError) as e:
        sig.read()
    assert e.match("test not found")


def test_bad_signal_put():
    sig = HttpRestSignal(name="get", get_uri="http://test.psi.ch/put_can_fail")
    sig.put("20")

    with pytest.raises(HttpRestError) as e:
        sig.put("51")
    assert e.match("Could not PUT 51")
    assert e.match("Code: 422. Reason: out of range.")


class PutQueryParamsSignal(HttpRestSignal):
    def _get_request_transform(self, uri: str):
        return get(uri + "transform")

    def _put_request_transform(self, uri: str, val: Any, **kwargs):
        return put(uri + "transform", params={"position": val})


def test_put_args_in_params():
    sig = PutQueryParamsSignal(name="transformed", get_uri="http://test.psi.ch/")
    reading = sig.read()
    assert reading.get("transformed").get("value") == "data"

    sig.put("20")
    reading = sig.read()
    assert reading.get("transformed").get("value") == "20"
