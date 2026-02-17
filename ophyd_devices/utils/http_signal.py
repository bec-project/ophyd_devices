from typing import Any

from ophyd.utils.errors import ReadOnlyError
from requests import Response, get, put

from ophyd_devices.utils.socket import SocketSignal


class HttpRestError(Exception):
    """Error for rest calls from a HttpRestSignal."""

    def __init__(self, resp: Response, *args: object, value: Any | None = None) -> None:
        method, url = resp.request.method, resp.request.url
        data = f"{str(value)} to " if value is not None else ""
        super().__init__(
            f"Could not {method} {data}{url}. Code: {resp.status_code}. Reason: {resp.reason}.",
            *args,
        )


class HttpRestSignal(SocketSignal):
    """Ophyd signal which gets and puts to a REST API rather than EPICS PVs."""

    def __init__(self, *args, get_uri: str = "", put_uri: str | None = None, **kwargs):
        self._get_uri = get_uri
        self._put_uri = put_uri or get_uri
        super().__init__(*args, **kwargs)

    def _get_request_transform(self, uri: str):
        """Hook to apply to the GET request before creating the request"""
        return get(uri)

    def _put_request_transform(self, uri: str, val: Any):
        """Hook to apply to the PUT request before creating the request"""
        return put(uri, val)

    def _socket_get(self):
        resp = self._get_request_transform(self._get_uri)
        if not resp.ok:
            raise HttpRestError(resp)
        self._readback = resp.text
        return self._readback

    def _socket_set(self, val: Any):
        resp = self._put_request_transform(self._put_uri, val)
        if not resp.ok:
            raise HttpRestError(resp, value=val)


class HttpRestSignalRO(HttpRestSignal):
    """Read-only version of HttpRestSignal"""

    def __init__(self, *args, get_uri: str = "", **kwargs):
        self._get_uri = get_uri
        super().__init__(*args, **kwargs)

    def _socket_set(self, val):
        raise ReadOnlyError(f"HttpRestSignalRO {self.name} is read-only!")
