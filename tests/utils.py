class SocketMock:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.buffer_put = []
        self.buffer_recv = [b""]
        self.is_open = False
        self.open()

    def connect(self):
        print(f"connecting to {self.host} port {self.port}")

    def _put(self, msg_bytes):
        self.buffer_put.append(msg_bytes)
        print(self.buffer_put)

    def _recv(self, buffer_length=1024):
        print(self.buffer_recv)
        if isinstance(self.buffer_recv, list):
            if len(self.buffer_recv) > 0:
                ret_val = self.buffer_recv.pop(0)
            else:
                ret_val = b""
            return ret_val
        return self.buffer_recv

    def _initialize_socket(self):
        pass

    def put(self, msg):
        return self._put(msg)

    def receive(self, buffer_length=1024):
        return self._recv(buffer_length=buffer_length)

    def open(self):
        self._initialize_socket()
        self.is_open = True

    def close(self):
        self.sock = None
        self.is_open = False

    def flush_buffer(self):
        self.buffer_put = []
        self.buffer_recv = ""
