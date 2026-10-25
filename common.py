import json
import struct

TCP_PORT = 5000
UDP_PORT = 5001
MAX_PEERS = 6
FRAG_SIZE = 1100

FRAME_W = 480
FRAME_H = 360
FPS = 15
JPEG_Q = 50

RATE = 16000
BLOCK = 320

T_HELLO = 0
T_VIDEO = 1
T_AUDIO = 2

HDR = struct.Struct("!BHIHH")


def send_msg(sock, obj):
    raw = json.dumps(obj).encode("utf-8")
    header = struct.pack("!I", len(raw))
    sock.sendall(header + raw)


def recv_exact(sock, n):
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("Socket closed")
        buf.extend(chunk)
    return bytes(buf)


def recv_msg(sock):
    header = recv_exact(sock, 4)
    (length,) = struct.unpack("!I", header)
    if length > 65536:
        raise ValueError("Message exceeds size limit")
    body = recv_exact(sock, length)
    return json.loads(body.decode("utf-8"))


def pack(kind, sender, seq, idx, total, payload):
    return HDR.pack(kind, sender, seq, idx, total) + payload


def unpack(data):
    if len(data) < HDR.size:
        raise ValueError("Packet shorter than header")
    kind, sender, seq, idx, total = HDR.unpack_from(data, 0)
    return kind, sender, seq, idx, total, data[HDR.size :]