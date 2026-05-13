import json
import socket


def send_rudp_msg(sock, obj, addr):
    try:
        data = json.dumps(obj).encode("utf-8")
        sock.sendto(data, addr)
        print(f"[DEBUG RUDP] Sent to {addr}: {obj}")
    except Exception as e:
        print(f"[DEBUG RUDP] Error sending to {addr}: {e}")


def recv_rudp_msg(sock):
    try:
        data, addr = sock.recvfrom(65535)
        if not data:
            return None, None

        full_msg = json.loads(data.decode("utf-8"))
        print(f"[DEBUG RUDP] Received from {addr}: {full_msg}")
        return full_msg, addr

    except socket.timeout:
        return None, None
    except json.JSONDecodeError:
        print("[DEBUG RUDP] Error: Received corrupted JSON data")
        return None, None
    except Exception as e:
        print(f"[DEBUG RUDP] Unexpected Error in recv: {e}")
        return None, None