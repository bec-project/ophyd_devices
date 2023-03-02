import json

from ophyd import Component as Cpt
from ophyd import Device, PositionerBase, Signal
from ophyd.ophydobj import OphydObject
from ophyd_devices.utils.socket import SocketMock


def get_user_functions(obj) -> list:
    exclude_list = ["log", "SUB_CONNECTION_CHANGE"]
    exclude_classes = [Device, OphydObject, PositionerBase, Signal, Cpt]
    for cls in exclude_classes:
        exclude_list.extend(dir(cls))
    access_list = [
        func for func in dir(obj) if not func.startswith("_") and func not in exclude_list
    ]

    return access_list


def is_serializable(f) -> bool:
    try:
        json.dumps(f)
        return True
    except (TypeError, OverflowError):
        return False


def get_user_interface(obj, obj_interface):
    # user_funcs = get_user_functions(obj)
    for f in [f for f in dir(obj) if f in obj.USER_ACCESS]:
        if f == "controller" or f == "on":
            print(f)
        m = getattr(obj, f)
        if not callable(m):
            if is_serializable(m):
                obj_interface[f] = {"type": type(m).__name__}
            elif isinstance(m, SocketMock):
                pass
            else:
                obj_interface[f] = get_user_interface(m, {})
        else:
            obj_interface[f] = {"type": "func"}
    return obj_interface
