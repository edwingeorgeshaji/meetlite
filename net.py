from collections import deque
import queue
import socket
import sys
import threading
import time
import cv2
import numpy as np
from PIL import Image
import sounddevice as sd
import common


class Net:
    def __init__(self):
        self.id = 0
        self.code = ""
        self.pin = ""
        self.token = b""
        self.mic_on = True
        self.cam_on = True
        self.tx = 0
        self.rx = 0
        self.rtt = 0
        self.events = queue.Queue()
        self.running = False
        self.tcp_sock = None
        self.udp_sock = None
        self.udp_target = None
        self.send_lock = threading.Lock()
        self.audio_lock = threading.Lock()
        self.audio_queues = {}
        self.audio_seq = 0
        self.in_stream = None
        self.out_stream = None
        self.vbuf = {}
        self.last_vseq = {}

    def connect(self, host, name, code=None, pin=None):
        ip = socket.gethostbyname(host.strip())
        self.udp_target = (ip, common.UDP_PORT)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(8.0)
        sock.connect((ip, common.TCP_PORT))
        if code is None:
            req = {"op": "create", "name": name}
        else:
            req = {"op": "join", "name": name, "code": code, "pin": pin}
        common.send_msg(sock, req)
        reply = common.recv_msg(sock)
        if reply.get("op") == "error":
            sock.close()
            raise RuntimeError(reply.get("reason", "Connection rejected"))
        if reply.get("op") != "joined":
            sock.close()
            raise RuntimeError("Unexpected response from server")
        sock.settimeout(None)
        self.tcp_sock = sock
        self.id = reply["id"]
        self.code = reply["code"]
        self.pin = reply["pin"]
        self.token = bytes.fromhex(reply["token"])
        self.udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_sock.bind(("0.0.0.0", 0))
        return reply

    def send_tcp(self, obj):
        if not self.tcp_sock:
            return
        with self.send_lock:
            try:
                common.send_msg(self.tcp_sock, obj)
            except Exception:
                pass

    def send_udp(self, kind, seq, idx, total, payload):
        if not self.udp_sock or not self.udp_target:
            return
        pkt = common.pack(kind, self.id, seq, idx, total, payload)
        try:
            self.udp_sock.sendto(pkt, self.udp_target)
            self.tx += len(pkt)
        except Exception:
            pass

    def start_media(self):
        self.running = True
        self.send_udp(common.T_HELLO, 0, 0, 1, self.token)
        threading.Thread(target=self.tcp_loop, daemon=True).start()
        threading.Thread(target=self.udp_loop, daemon=True).start()
        threading.Thread(target=self.keepalive_loop, daemon=True).start()
        threading.Thread(target=self.video_loop, daemon=True).start()
        self.start_audio()

    def set_mic(self, on):
        self.mic_on = bool(on)
        self.send_tcp({"op": "state", "mic": self.mic_on, "cam": self.cam_on})

    def set_cam(self, on):
        self.cam_on = bool(on)
        self.send_tcp({"op": "state", "mic": self.mic_on, "cam": self.cam_on})

    def tcp_loop(self):
        try:
            while self.running:
                msg = common.recv_msg(self.tcp_sock)
                op = msg.get("op")
                if op == "peer_joined":
                    self.events.put(
                        (
                            "peer_joined",
                            msg["id"],
                            msg["name"],
                            msg["mic"],
                            msg["cam"],
                        )
                    )
                elif op == "peer_left":
                    pid = msg["id"]
                    self.vbuf.pop(pid, None)
                    self.last_vseq.pop(pid, None)
                    with self.audio_lock:
                        self.audio_queues.pop(pid, None)
                    self.events.put(("peer_left", pid))
                elif op == "state":
                    self.events.put(
                        ("peer_state", msg["id"], msg["mic"], msg["cam"])
                    )
                elif op == "pong":
                    sent_t = float(msg.get("t", 0))
                    if sent_t > 0:
                        self.rtt = int((time.time() - sent_t) * 1000)
        except Exception:
            if self.running:
                self.running = False
                self.events.put(("closed", "Connection to the server was lost"))

    def keepalive_loop(self):
        while self.running:
            self.send_udp(common.T_HELLO, 0, 0, 1, self.token)
            self.send_tcp({"op": "ping", "t": time.time()})
            time.sleep(2.0)

    def udp_loop(self):
        while self.running:
            try:
                data, _ = self.udp_sock.recvfrom(65535)
            except Exception:
                if not self.running:
                    break
                continue
            self.rx += len(data)
            try:
                kind, sender, seq, idx, total, payload = common.unpack(data)
            except ValueError:
                continue
            if kind == common.T_VIDEO:
                self.handle_video_pkt(sender, seq, idx, total, payload)
            elif kind == common.T_AUDIO:
                self.handle_audio_pkt(sender, payload)

    def handle_video_pkt(self, sender, seq, idx, total, payload):
        if total == 0 or total > 120 or idx >= total:
            return
        if seq <= self.last_vseq.get(sender, -1):
            return
        sbuf = self.vbuf.setdefault(sender, {})
        if seq not in sbuf:
            for old_seq in [k for k in sbuf if k < seq - 2]:
                del sbuf[old_seq]
            sbuf[seq] = [None] * total
        parts = sbuf[seq]
        if len(parts) != total:
            return
        parts[idx] = payload
        if all(p is not None for p in parts):
            raw = b"".join(parts)
            self.last_vseq[sender] = seq
            for k in [k for k in sbuf if k <= seq]:
                del sbuf[k]
            arr = np.frombuffer(raw, dtype=np.uint8)
            bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if bgr is not None:
                rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                self.events.put(("video", sender, Image.fromarray(rgb)))

    def open_camera(self):
        if sys.platform == "win32":
            cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
            if cap and cap.isOpened():
                return cap
        return cv2.VideoCapture(0)

    def video_loop(self):
        cap = None
        seq = 0
        interval = 1.0 / common.FPS
        while self.running:
            t0 = time.time()
            if not self.cam_on:
                if cap is not None:
                    cap.release()
                    cap = None
                time.sleep(0.05)
                continue
            if cap is None:
                cap = self.open_camera()
                if not cap or not cap.isOpened():
                    if cap:
                        cap.release()
                    cap = None
                    time.sleep(0.5)
                    continue
            ok, frame = cap.read()
            if not ok:
                time.sleep(0.05)
                continue
            frame = cv2.resize(frame, (common.FRAME_W, common.FRAME_H))
            rgb = cv2.cvtColor(cv2.flip(frame, 1), cv2.COLOR_BGR2RGB)
            self.events.put(("local_video", Image.fromarray(rgb)))
            ok, enc = cv2.imencode(
                ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), common.JPEG_Q]
            )
            if ok:
                raw = enc.tobytes()
                total = max(
                    1, (len(raw) + common.FRAG_SIZE - 1) // common.FRAG_SIZE
                )
                seq += 1
                for idx in range(total):
                    chunk = raw[
                        idx * common.FRAG_SIZE : (idx + 1) * common.FRAG_SIZE
                    ]
                    self.send_udp(common.T_VIDEO, seq, idx, total, chunk)
            wait = interval - (time.time() - t0)
            if wait > 0:
                time.sleep(wait)
        if cap is not None:
            cap.release()

    def handle_audio_pkt(self, sender, payload):
        if len(payload) != common.BLOCK * 2:
            return
        with self.audio_lock:
            q = self.audio_queues.get(sender)
            if q is None:
                q = deque(maxlen=12)
                self.audio_queues[sender] = q
            q.append(payload)

    def start_audio(self):
        def mic_cb(indata, frames, time_info, status):
            if self.running and self.mic_on:
                self.audio_seq += 1
                self.send_udp(
                    common.T_AUDIO, self.audio_seq, 0, 1, bytes(indata)
                )

        def spk_cb(outdata, frames, time_info, status):
            chunks = []
            with self.audio_lock:
                for q in self.audio_queues.values():
                    if q:
                        chunks.append(np.frombuffer(q.popleft(), dtype=np.int16))
            if not chunks:
                outdata[:] = b"\x00" * len(outdata)
            else:
                mixed = np.zeros(common.BLOCK, dtype=np.int32)
                for c in chunks:
                    if len(c) == common.BLOCK:
                        mixed += c
                clipped = np.clip(mixed, -32768, 32767).astype(np.int16)
                outdata[:] = clipped.tobytes()

        try:
            self.in_stream = sd.RawInputStream(
                samplerate=common.RATE,
                blocksize=common.BLOCK,
                channels=1,
                dtype="int16",
                callback=mic_cb,
            )
            self.in_stream.start()
        except Exception:
            self.in_stream = None
        try:
            self.out_stream = sd.RawOutputStream(
                samplerate=common.RATE,
                blocksize=common.BLOCK,
                channels=1,
                dtype="int16",
                callback=spk_cb,
            )
            self.out_stream.start()
        except Exception:
            self.out_stream = None

    def close(self):
        was_running = self.running
        self.running = False
        if was_running and self.tcp_sock:
            self.send_tcp({"op": "leave"})
        for stream in (self.in_stream, self.out_stream):
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass
        self.in_stream = None
        self.out_stream = None
        for sock in (self.tcp_sock, self.udp_sock):
            if sock is not None:
                try:
                    sock.close()
                except Exception:
                    pass
        self.tcp_sock = None
        self.udp_sock = None