import socket
import json, random, time
import os, uuid
from constants import *
import argparse
from rudp_func import send_rudp_msg, recv_rudp_msg
from message_types import *


BASE_DIR = os.path.dirname(__file__)
CLIENT_IDS_DIR = os.path.join(BASE_DIR, "client_ids")
os.makedirs(CLIENT_IDS_DIR, exist_ok=True)


def client_id_path(client_num: int):
    return os.path.join(CLIENT_IDS_DIR, f"client_id_{client_num}.txt")


def get_or_create_client_id(client_num: int):
    path = client_id_path(client_num)

    if os.path.exists(path):
        return open(path, "r", encoding="utf-8").read().strip()

    cid = str(uuid.uuid4())
    with open(path, "w", encoding="utf-8") as f:
        f.write(cid)
    return cid

def resolve_dns_locally(domain):
    try:
        dns_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        dns_sock.settimeout(2)
        header = b'\xaa\xaa\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00'
        query = b'\x07myagent\x05local\x00\x00\x01\x00\x01'
        dns_sock.sendto(header + query, ("127.0.0.1", 5358))
        dns_sock.recvfrom(1024)
        print("[DNS] Domain resolved via local DNS server")
    except:
        print("[DNS] DNS server not responding, using default IP")
    finally:
        dns_sock.close()


def run_dhcp_server(client_num: int):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(2.0)

    client_id = get_or_create_client_id(client_num)
    xid = random.randint(1, 99999)

    try:
        discover = {"type": "DISCOVER", "xid": xid, "client_id": client_id}

        offer = None
        for attempt in range(3):
            sock.sendto(json.dumps(discover).encode(), (DHCP_SERVER_IP, DHCP_SERVER_PORT))
            try:
                data, _ = sock.recvfrom(4096)
                msg = json.loads(data.decode())

                if msg.get("xid") != xid:
                    continue

                if msg.get("type") == "OFFER":
                    offer = msg
                    break

                if msg.get("type") == "NAK":
                    print("DHCP NAK:", msg)
                    return None

            except socket.timeout:
                print(f"[DHCP] DISCOVER timeout (attempt {attempt+1}/3)")
            except ConnectionResetError:
                print("[DHCP] UDP reset received. Retrying DISCOVER...")
            except socket.timeout:
                print(f"[DHCP] DISCOVER timeout (attempt {attempt + 1}/3)")

        if not offer:
            print("[DHCP] Failed to get OFFER")
            return None

        print("Received OFFER:", offer)

        request = {
            "type": "REQUEST",
            "xid": xid,
            "client_id": client_id,
            "requested_ip": offer["offered_ip"],
            "server_id": offer.get("server_id")
        }

        ack = None
        for attempt in range(3):
            print(f"[DHCP] Sending REQUEST (attempt {attempt + 1}/3)")
            sock.sendto(json.dumps(request).encode(), (DHCP_SERVER_IP, DHCP_SERVER_PORT))

            try:
                data, _ = sock.recvfrom(4096)
                msg = json.loads(data.decode())

                if msg.get("xid") != xid:
                    continue

                if msg.get("type") == "ACK":
                    ack = msg
                    break

                if msg.get("type") == "NAK":
                    print("[DHCP] Server returned NAK:", msg)
                    return None

            except socket.timeout:
                print(f"[DHCP] REQUEST timeout (attempt {attempt + 1}/3)")
            except ConnectionResetError:
                print("[DHCP] UDP reset received. Retrying REQUEST...")

        if not ack:
            print("[DHCP] Failed to get ACK")
            return None

        print("Received ACK:", ack)
        return ack

    finally:
        sock.close()


def get_user_payload(protocol_used, assigned_ip):
    print("--- Configuration ---")
    name = input("Enter your name: ") or "Student"
    container_port = input("Enter container port (default 8080): ") or "8080"
    container_name = input("Enter container name (default nginx_server): ") or "nginx_server"

    data = {
        "name": name,
        "container_name": container_name,
        "port": container_port,
        "protocol": protocol_used,
        "assigned_ip": assigned_ip,
    }
    return data


def dhcp_release(client_num: int):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(2.0)

    client_id = get_or_create_client_id(client_num)
    xid = random.randint(1, 99999)

    release = {"type": "RELEASE", "xid": xid, "client_id": client_id}
    sock.sendto(json.dumps(release).encode(), (DHCP_SERVER_IP, DHCP_SERVER_PORT))

    try:
        data, _ = sock.recvfrom(4096)
        resp = json.loads(data.decode())
        print("Received RELEASE response:", resp)
        return resp
    except socket.timeout:
        print("[DHCP] RELEASE timeout")
        return None
    finally:
        sock.close()


# TCP client
def run_tcp_client(payload):
    json_bytes = json.dumps(payload).encode('utf-8')

    print(f"\n[TCP Client] Connecting to {APP_SERVER_IP}:{SERVER_PORT}...")

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(20)

    try:
        sock.connect((APP_SERVER_IP, SERVER_PORT))
        print("[TCP Client] Connected successfully!")

        sock.sendall(json_bytes)
        print(f"[TCP Client] Data sent ({len(json_bytes)} bytes). Waiting for server logic...")

        response = sock.recv(4096)
        print(f"\n[TCP Client] Server Response:\n{response.decode()}")

    except socket.timeout:
        print("\n[ERROR] Timeout! Server is taking too long (maybe downloading Docker image?).")
    except ConnectionRefusedError:
        print(f"[TCP Client] Error: Could not connect to {APP_SERVER_IP}:{SERVER_PORT}. Is the server running?")
    except Exception as e:
        print(f"[TCP Client] Error: {e}")
    finally:
        sock.close()
        print("[TCP Client] Connection closed.")


# RUDP client
def run_rudp_client(payload):
    json_str = json.dumps(payload)
    print(f"\n[RUDP Client] Connecting to {APP_SERVER_IP}:{SERVER_PORT}...")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(2.0)
    server_addr = (APP_SERVER_IP, SERVER_PORT)

    # 1. Handshake
    send_rudp_msg(sock, {"type": TYPE_SIN}, server_addr)
    try:
        res, _ = recv_rudp_msg(sock)
        if not res or res.get("type") != TYPE_SIN_ACK:
            print("[RUDP Client] Handshake Failed!")
            return
        send_rudp_msg(sock, {"type": TYPE_ACK}, server_addr)
        print("[RUDP Client] Handshake Succeeded!")
    except socket.timeout:
        print("[RUDP Client] Handshake Timeout!")
        return

    MAX_SIZE = 50
    chunks = [json_str[i:i + MAX_SIZE] for i in range(0, len(json_str), MAX_SIZE)]
    seq, next_seq, window_size = 0, 0, 3
    send_times = {}

    while seq < len(chunks):
        while next_seq < len(chunks) and next_seq < seq + window_size:
            send_rudp_msg(sock, {"type": TYPE_DATA, "seq": next_seq, "payload": chunks[next_seq]}, server_addr)
            send_times[next_seq] = time.time()
            next_seq += 1

        if seq in send_times and (time.time() - send_times[seq] > 1.0):
            window_size = max(1, window_size - 1)
            next_seq = seq
            send_times.clear()
            continue

        try:
            ack_msg, _ = recv_rudp_msg(sock)
            if ack_msg and ack_msg.get("type") == TYPE_ACK:
                ack_num = ack_msg["ack"]
                if ack_num >= seq:
                    for s in range(seq, ack_num + 1):
                        send_times.pop(s, None)
                    seq = ack_num + 1
                    window_size += 1
        except socket.timeout:
            pass

    send_rudp_msg(sock, {"type": TYPE_END_MESSAGE}, server_addr)
    sock.settimeout(20.0)

    try:
        response_msg, _ = recv_rudp_msg(sock)
        if response_msg:
            print(f"\n[RUDP Client] Server Response:\n{response_msg.get('payload', '')}")
    except socket.timeout:
        print("[RUDP Client] Timeout waiting for server response.")
    finally:
        sock.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--client", type=int, default=1, help="Client number (e.g., 1,2,3)")
    parser.add_argument("--protocol", type=str, choices=['tcp', 'rudp'], default='tcp',
                        help="Choose transport protocol (tcp or rudp)")
    args = parser.parse_args()

    client_num = args.client
    protocol = args.protocol

    print(f"[Client] Running as client #{client_num} using {protocol.upper()}")

    ack = run_dhcp_server(client_num)
    if not ack:
        exit(1)

    assigned_ip = ack.get("assigned_ip")
    print(f"[Client {client_num}] My assigned IP: {assigned_ip}")

    resolve_dns_locally("myagent.local")
    payload = get_user_payload(protocol, assigned_ip)


    if protocol == 'tcp':
        run_tcp_client(payload)
    else:
        run_rudp_client(payload)

    dhcp_release(client_num)