import socket
import time
import common

HOST = "127.0.0.1"


def report(name, cond):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}")
    if not cond:
        raise SystemExit(1)


def open_tcp():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(5.0)
    s.connect((HOST, common.TCP_PORT))
    return s


def run_tests():
    s1 = open_tcp()
    common.send_msg(s1, {"op": "create", "name": "Alice"})
    r1 = common.recv_msg(s1)
    code = r1.get("code", "")
    pin = r1.get("pin", "")
    id1 = r1.get("id", 0)
    tok1 = bytes.fromhex(r1.get("token", ""))
    report(
        "1. create returns 6-character code and 4-digit PIN",
        r1.get("op") == "joined"
        and len(code) == 6
        and len(pin) == 4
        and pin.isdigit(),
    )

    bad_pin = "0000" if pin != "0000" else "9999"
    s_bad = open_tcp()
    common.send_msg(
        s_bad, {"op": "join", "name": "Eve", "code": code, "pin": bad_pin}
    )
    r_bad = common.recv_msg(s_bad)
    s_bad.close()
    report(
        "2. join with wrong PIN returns error",
        r_bad.get("op") == "error"
        and r_bad.get("reason") == "Wrong code or PIN",
    )

    s2 = open_tcp()
    common.send_msg(
        s2, {"op": "join", "name": "Bob", "code": code, "pin": pin}
    )
    r2 = common.recv_msg(s2)
    id2 = r2.get("id", 0)
    tok2 = bytes.fromhex(r2.get("token", ""))
    ev_join = common.recv_msg(s1)
    report(
        "3. join with right code and PIN succeeds and creator gets peer_joined",
        r2.get("op") == "joined"
        and ev_join.get("op") == "peer_joined"
        and ev_join.get("id") == id2
        and ev_join.get("name") == "Bob",
    )

    common.send_msg(s2, {"op": "state", "mic": False, "cam": True})
    ev_state = common.recv_msg(s1)
    report(
        "4. state change from one client reaches the other",
        ev_state.get("op") == "state"
        and ev_state.get("id") == id2
        and ev_state.get("mic") is False
        and ev_state.get("cam") is True,
    )

    u1 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    u2 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    u1.settimeout(3.0)
    u2.settimeout(3.0)
    u1.sendto(
        common.pack(common.T_HELLO, id1, 0, 0, 1, tok1), (HOST, common.UDP_PORT)
    )
    u2.sendto(
        common.pack(common.T_HELLO, id2, 0, 0, 1, tok2), (HOST, common.UDP_PORT)
    )
    time.sleep(0.1)
    video_pkt = common.pack(common.T_VIDEO, id1, 42, 0, 1, b"test_frame_bytes")
    u1.sendto(video_pkt, (HOST, common.UDP_PORT))
    received, _ = u2.recvfrom(4096)
    report(
        "5. UDP T_VIDEO packet after HELLO arrives unchanged at peer",
        received == video_pkt,
    )

    common.send_msg(s2, {"op": "leave"})
    ev_left = common.recv_msg(s1)
    report(
        "6. leave makes the other client receive peer_left",
        ev_left.get("op") == "peer_left" and ev_left.get("id") == id2,
    )

    common.send_msg(s1, {"op": "leave"})
    s1.close()
    s2.close()
    u1.close()
    u2.close()


if __name__ == "__main__":
    run_tests()