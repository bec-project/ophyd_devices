import abc
import socket
import functools
import time
import threading

from typeguard import typechecked
from ophyd import PositionerBase, Signal
from ophyd.device import Device, Component as Cpt
from prettytable import PrettyTable
from ophyd_devices.utils.socket import raise_if_disconnected
from ophyd_devices.utils.controller import SingletonController, threadlocked


def channel_checked(fcn):
    """Decorator to catch attempted access to channels that are not available."""

    @functools.wraps(fcn)
    def wrapper(self, *args, **kwargs):
        self._check_channel(args[0])
        return fcn(self, *args, **kwargs)

    return wrapper


class NPointController(SingletonController):
    NUM_CHANNELS = 3
    _read_single_loc_bit = "A0"
    _write_single_loc_bit = "A2"
    _trailing_bit = "55"
    _range_offset = "78"
    _channel_base = ["11", "83"]

    def __init__(
        self,
        comm_socket: SocketIO,
        server_ip: str = "129.129.99.87",
        server_port: int = 23,
    ) -> None:
        super().__init__()
        self._server_and_port_name = (server_ip, server_port)
        self.socket = comm_socket
        self.connected = False

    @classmethod
    def create(cls):
        return cls(SocketIO())

    def show_all(self) -> None:
        """Display current status of all channels

        Returns:
            None
        """
        if not self.connected:
            print("npoint controller is currently disabled.")
            return
        print(f"Connected to controller at {self._server_and_port_name}")
        t = PrettyTable()
        t.field_names = ["Channel", "Range", "Position", "Target"]
        for ii in range(self.NUM_CHANNELS):
            t.add_row(
                [
                    ii,
                    self._get_range(ii),
                    self._get_current_pos(ii),
                    self._get_target_pos(ii),
                ]
            )
        print(t)

    @threadlocked
    def on(self) -> None:
        """Enable the NPoint controller and open a new socket.

        Raises:
            TimeoutError: Raised if the socket connection raises a timeout.

        Returns:
            None
        """
        if self.connected:
            print("You are already connected to the NPoint controller.")
            return
        if not self.socket.is_open:
            self.socket.open()
        try:
            self.socket.connect(self._server_and_port_name[0], self._server_and_port_name[1])
        except socket.timeout:
            raise TimeoutError(
                f"Failed to connect to the specified server and port {self._server_and_port_name}."
            )
        except OSError:
            print("ERROR while connecting. Let's try again")
            self.socket.close()
            time.sleep(0.5)
            self.socket.open()
            self.socket.connect(self._server_and_port_name[0], self._server_and_port_name[1])
        self.connected = True

    @threadlocked
    def off(self) -> None:
        """Disable the controller and close the socket.

        Returns:
            None
        """
        self.socket.close()
        self.connected = False

    @channel_checked
    def _get_range(self, channel: int) -> int:
        """Get the range of the specified channel axis.

        Args:
            channel (int): Channel for which the range should be requested.

        Raises:
            RuntimeError: Raised if the received message doesn't have the expected number of bytes (10).

        Returns:
            int: Range
        """

        # for first channel: 0x11 83 10 78
        addr = self._channel_base.copy()
        addr.extend([f"{16 + 16 * channel:x}", self._range_offset])
        send_buffer = self.__read_single_location_buffer(addr)

        recvd = self._put_and_receive(send_buffer)
        if len(recvd) != 10:
            raise RuntimeError(
                f"Received buffer is corrupted. Expected 10 bytes and instead got {len(recvd)}"
            )
        device_range = self._hex_list_to_int(recvd[5:-1], signed=False)
        return device_range

    @channel_checked
    def _get_current_pos(self, channel: int) -> float:
        # for first channel: 0x11 83 13 34
        addr = self._channel_base.copy()
        addr.extend([f"{19 + 16 * channel:x}", "34"])
        send_buffer = self.__read_single_location_buffer(addr)

        recvd = self._put_and_receive(send_buffer)

        pos_buffer = recvd[5:-1]
        pos = self._hex_list_to_int(pos_buffer) / 1048574 * 100
        return pos

    @channel_checked
    def _set_target_pos(self, channel: int, pos: float) -> None:
        # for first channel: 0x11 83 12 18 00 00 00 00
        addr = self._channel_base.copy()
        addr.extend([f"{18 + channel * 16:x}", "18"])

        target = int(round(1048574 / 100 * pos))
        data = [f"{m:02x}" for m in target.to_bytes(4, byteorder="big", signed=True)]

        send_buffer = self.__write_single_location_buffer(addr, data)
        self._put(send_buffer)

    @channel_checked
    def _get_target_pos(self, channel: int) -> float:
        # for first channel: 0x11 83 12 18
        addr = self._channel_base.copy()
        addr.extend([f"{18 + channel * 16:x}", "18"])
        send_buffer = self.__read_single_location_buffer(addr)

        recvd = self._put_and_receive(send_buffer)
        pos_buffer = recvd[5:-1]
        pos = self._hex_list_to_int(pos_buffer) / 1048574 * 100
        return pos

    @channel_checked
    def _set_servo(self, channel: int, enable: bool) -> None:
        print("Not tested")
        return
        # for first channel: 0x11 83 10 84 00 00 00 00
        addr = self._channel_base.copy()
        addr.extend([f"{16 + channel * 16:x}", "84"])

        if enable:
            data = ["00"] * 3 + ["01"]
        else:
            data = ["00"] * 4
        send_buffer = self.__write_single_location_buffer(addr, data)

        self._put(send_buffer)

    @channel_checked
    def _get_servo(self, channel: int) -> int:
        # for first channel: 0x11 83 10 84 00 00 00 00
        addr = self._channel_base.copy()
        addr.extend([f"{16 + channel * 16:x}", "84"])
        send_buffer = self.__read_single_location_buffer(addr)

        recvd = self._put_and_receive(send_buffer)
        buffer = recvd[5:-1]
        status = self._hex_list_to_int(buffer)
        return status

    @threadlocked
    def _put(self, buffer: list) -> None:
        """Translates a list of hex values to bytes and sends them to the socket.

        Args:
            buffer (list): List of hex values without leading 0x

        Returns:
            None
        """

        buffer = b"".join([bytes.fromhex(m) for m in buffer])
        self.socket.put(buffer)

    @threadlocked
    def _put_and_receive(self, msg_hex_list: list) -> list:
        """Send msg to socket and wait for a reply.

        Args:
            msg_hex_list (list): List of hex values without leading 0x.

        Returns:
            list: Received message as a list of hex values
        """

        buffer = b"".join([bytes.fromhex(m) for m in msg_hex_list])
        self.socket.put(buffer)
        recv_msg = self.socket.receive()
        recv_hex_list = [hex(m) for m in recv_msg]
        self._verify_received_msg(msg_hex_list, recv_hex_list)
        return recv_hex_list

    def _verify_received_msg(self, in_list: list, out_list: list) -> None:
        """Ensure that the first address bits of sent and received messages are the same.

        Args:
            in_list (list): list containing the sent message
            out_list (list): list containing the received message

        Raises:
            RuntimeError: Raised if first two address bits of 'in' and 'out' are not identical

        Returns:
            None
        """

        # first, translate hex (str) values to int
        in_list_int = [int(val, 16) for val in in_list]
        out_list_int = [int(val, 16) for val in out_list]

        # first ints of the reply should be the same. Otherwise something went wrong
        if not in_list_int[:2] == out_list_int[:2]:
            raise RuntimeError("Connection failure. Please restart the controller.")

    def _check_channel(self, channel: int) -> None:
        if channel >= self.NUM_CHANNELS:
            raise ValueError(
                f"Channel {channel+1} exceeds the available number of channels ({self.NUM_CHANNELS})"
            )

    @staticmethod
    def _hex_list_to_int(in_buffer: list, byteorder="little", signed=True) -> int:
        """Translate hex list to int.

        Args:
            in_buffer (list): Input buffer; received as list of hex values
            byteorder (str, optional): Byteorder of in_buffer. Defaults to "little".
            signed (bool, optional): Whether the hex list represents a signed int. Defaults to True.

        Returns:
            int: Translated integer.
        """
        if byteorder == "little":
            in_buffer.reverse()

        # make sure that all hex strings have the same format ("FF")
        val_hex = [f"{int(m, 16):02x}" for m in in_buffer]

        val_bytes = [bytes.fromhex(m) for m in val_hex]
        val = int.from_bytes(b"".join(val_bytes), byteorder="big", signed=signed)
        return val

    @staticmethod
    def __read_single_location_buffer(addr) -> list:
        """Prepare buffer for reading from a single memory location (hex address).
        Number of bytes: 6
        Format: 0xA0 [addr] 0x55
        Return Value: 0xA0 [addr] [data] 0x55
        Sample Hex Transmission from PC to LC.400: A0 18 12 83 11 55
        Sample Hex Return Transmission from LC.400 to PC: A0 18 12 83 11 64 00 00 00 55

        Args:
            addr (list): Hex address to read from

        Returns:
            list: List of hex values representing the read instruction.
        """
        buffer = []
        buffer.append(NPointController._read_single_loc_bit)
        if isinstance(addr, list):
            addr.reverse()
            buffer.extend(addr)
        else:
            buffer.append(addr)
        buffer.append(NPointController._trailing_bit)

        return buffer

    @staticmethod
    def __write_single_location_buffer(addr: list, data: list) -> list:
        """Prepare buffer for writing to a single memory location (hex address).
        Number of bytes: 10
        Format: 0xA2 [addr] [data] 0x55
        Return Value: none
        Sample Hex Transmission from PC to C.400: A2 18 12 83 11 E8 03 00 00 55

        Args:
            addr (list): List of hex values representing the address to write to.
            data (list): List of hex values representing the data that should be written.

        Returns:
            list: List of hex values representing the write instruction.
        """
        buffer = []
        buffer.append(NPointController._write_single_loc_bit)
        if isinstance(addr, list):
            addr.reverse()
            buffer.extend(addr)
        else:
            buffer.append(addr)

        if isinstance(data, list):
            data.reverse()
            buffer.extend(data)
        else:
            buffer.append(data)
        buffer.append(NPointController._trailing_bit)
        return buffer

    @staticmethod
    def __read_array():
        raise NotImplementedError

    @staticmethod
    def __write_next_command():
        raise NotImplementedError

    def __del__(self):
        if self.connected:
            print("Closing npoint socket")
            self.off()


class SocketSignal(abc.ABC, Signal):
    def __init__(self, *, name, **kwargs):
        super().__init__(**kwargs)

    @abc.abstractmethod
    def _socket_get(self):
        ...

    @abc.abstractmethod
    def _socket_set(self, val):
        ...


class NPointSignalBase(SocketSignal):
    def __init__(self, controller, signal_name, **kwargs):
        self.controller = controller
        self.signal_name = signal_name
        super().__init__(**kwargs)


class NPointReadbackSignal(NPointSignalBase):
    def _socket_get(self):
        pass

    def _socket_set(self, val):
        pass


class NPointAxis(Device, PositionerBase):
    def __init__(
        self,
        prefix="",
        *,
        name,
        channel=None,
        kind=None,
        read_attrs=None,
        configuration_attrs=None,
        parent=None,
        **kwargs,
    ):
        self.channel = channel
        self.controller = self._get_controller()

        self.readback = Cpt(
            NPointSignal, controller=self.controller, signal_name="RBV", kind="hinted"
        )
        self.user_setpoint = Cpt(
            NPointSignal, controller=self.controller, signal_name="VAL", kind="normal"
        )

        self.motor_resolution = Cpt(
            NPointSignal, controller=self.controller, signal_name="RNGE", kind="config"
        )
        self.motor_is_moving = Cpt(
            NPointSignal, controller=self.controller, signal_name="MOVN", kind="config"
        )
        self.axes_referenced = Cpt(
            NPointSignal, controller=self.controller, signal_name="XREF", kind="config"
        )

    def _get_controller(self):
        return NPointController()
