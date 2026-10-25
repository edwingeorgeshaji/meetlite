import secrets
import socket
import threading
import time
import common

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
DIGITS = "0123456789"


class Peer:
    def __init__(self, pid, sock, name, room):
        self.id = pid
        self.sock = sock
        self.name = name
        self.room = room
        self.token = secrets.token_bytes(16)
        self.mic = True
        self.cam = True
        self.udp_addr = None
        self.seen = time.time()


class Room:
    def __init__(self, code, pin):
        self.code = code
        self.pin = pin
        self.peers = {}


class RelayServer:
    def __init__(self):
        self.lock = threading.RLock()
        self.rooms = {}
        self.peers = {}
        self.udp_map = {}
        self.next_id = 1
        self.udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_sock.bind(("0.0.0.0", common.UDP_PORT))
        self.tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.tcp_sock.bind(("0.0.0.0", common.TCP_PORT))
        self.tcp_sock.listen(64)

    def new_code(self):
        while True:
            code = "".join(secrets.choice(ALPHABET) for _ in range(6))
            if code not in self.rooms:
                return code

    def new_pin(self):
        return "".join(secrets.choice(DIGITS) for _ in range(4))

    def allocate_id(self):
        pid = self.next_id
        self.next_id = (self.next_id % 65534) + 1
        return pid

    def broadcast(self, room, msg, exclude_id=None):
        targets = [p for pid, p in room.peers.items() if pid != exclude_id]
        for peer in targets:
            try:
                common.send_msg(peer.sock, msg)
            except Exception:
                pass

    def remove_peer(self, peer):
        with self.lock:
            if peer.id not in self.peers:
                return
            del self.peers[peer.id]
            if peer.udp_addr and self.udp_map.get(peer.udp_addr) == peer:
                del self.udp_map[peer.udp_addr]
            room = peer.room
            if room and peer.id in room.peers:
                del room.peers[peer.id]
                print(f"[LEAVE] {peer.name} (id={peer.id}) left room {room.code}")
                if not room.peers:
                    self.rooms.pop(room.code, None)
                else:
                    self.broadcast(room, {"op": "peer_left", "id": peer.id})
        try:
            peer.sock.close()
        except Exception:
            pass

    def register_peer(self, sock, name, room):
        pid = self.allocate_id()
        peer = Peer(pid, sock, name, room)
        existing = [
            {"id": p.id, "name": p.name, "mic": p.mic, "cam": p.cam}
            for p in room.peers.values()
        ]
        room.peers[pid] = peer
        self.peers[pid] = peer
        common.send_msg(
            sock,
            {
                "op": "joined",
                "id": pid,
                "token": peer.token.hex(),
                "code": room.code,
                "pin": room.pin,
                "peers": existing,
            },
        )
        self.broadcast(
            room,
            {
                "op": "peer_joined",
                "id": pid,
                "name": name,
                "mic": peer.mic,
                "cam": peer.cam,
            },
            exclude_id=pid,
        )
        print(f"[JOIN] {name} (id={pid}) joined room {room.code}")
        return peer

    def handle_auth(self, sock):
        attempts = 0
        while attempts < 3:
            msg = common.recv_msg(sock)
            op = msg.get("op")
            name = str(msg.get("name", "Guest")).strip()[:24] or "Guest"
            if op == "create":
                with self.lock:
                    code = self.new_code()
                    pin = self.new_pin()
                    room = Room(code, pin)
                    self.rooms[code] = room
                    return self.register_peer(sock, name, room)
            elif op == "join":
                code = str(msg.get("code", "")).strip().upper()
                pin = str(msg.get("pin", "")).strip()
                with self.lock:
                    room = self.rooms.get(code)
                    if not room or not secrets.compare_digest(room.pin, pin):
                        attempts += 1
                        common.send_msg(
                            sock, {"op": "error", "reason": "Wrong code or PIN"}
                        )
                        if attempts >= 3:
                            sock.close()
                            return None
                        continue
                    if len(room.peers) >= common.MAX_PEERS:
                        common.send_msg(
                            sock, {"op": "error", "reason": "Meeting is full"}
                        )
                        sock.close()
                        return None
                    return self.register_peer(sock, name, room)
            else:
                sock.close()
                return None
        return None

    def handle_client(self, sock):
        peer = None
        try:
            peer = self.handle_auth(sock)
            if not peer:
                return
            while True:
                msg = common.recv_msg(sock)
                with self.lock:
                    peer.seen = time.time()
                op = msg.get("op")
                if op == "ping":
                    common.send_msg(sock, {"op": "pong", "t": msg.get("t", 0)})
                elif op == "state":
                    with self.lock:
                        peer.mic = bool(msg.get("mic", True))
                        peer.cam = bool(msg.get("cam", True))
                        self.broadcast(
                            peer.room,
                            {
                                "op": "state",
                                "id": peer.id,
                                "mic": peer.mic,
                                "cam": peer.cam,
                            },
                            exclude_id=peer.id,
                        )
                elif op == "leave":
                    break
        except Exception:
            pass
        finally:
            if peer:
                self.remove_peer(peer)
            else:
                try:
                    sock.close()
                except Exception:
                    pass

    def udp_loop(self):
        while True:
            try:
                data, addr = self.udp_sock.recvfrom(65535)
            except ConnectionResetError:
                continue
            except Exception:
                continue
            if len(data) < common.HDR.size:
                continue
            kind, sender_id, seq, idx, total = common.HDR.unpack_from(data, 0)
            if kind == common.T_HELLO:
                payload = data[common.HDR.size :]
                with self.lock:
                    peer = self.peers.get(sender_id)
                    if peer and secrets.compare_digest(peer.token, payload):
                        if peer.udp_addr and peer.udp_addr != addr:
                            self.udp_map.pop(peer.udp_addr, None)
                        peer.udp_addr = addr
                        peer.seen = time.time()
                        self.udp_map[addr] = peer
                continue
            with self.lock:
                peer = self.udp_map.get(addr)
                if not peer or peer.id != sender_id:
                    continue
                peer.seen = time.time()
                targets = [
                    p.udp_addr
                    for pid, p in peer.room.peers.items()
                    if pid != sender_id and p.udp_addr is not None
                ]
            for dst in targets:
                try:
                    self.udp_sock.sendto(data, dst)
                except Exception:
                    pass

    def reaper_loop(self):
        while True:
            time.sleep(5)
            now = time.time()
            with self.lock:
                stale = [p for p in self.peers.values() if now - p.seen > 15]
            for peer in stale:
                self.remove_peer(peer)

    def serve(self):
        print(
            f"MeetLite Server listening on TCP {common.TCP_PORT} and UDP {common.UDP_PORT}"
        )
        threading.Thread(target=self.udp_loop, daemon=True).start()
        threading.Thread(target=self.reaper_loop, daemon=True).start()
        while True:
            sock, _ = self.tcp_sock.accept()
            threading.Thread(
                target=self.handle_client, args=(sock,), daemon=True
            ).start()


if __name__ == "__main__":
    RelayServer().serve()