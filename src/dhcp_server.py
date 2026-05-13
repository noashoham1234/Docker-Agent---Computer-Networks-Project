import socket, json, time, threading, random
from constants import *

leases = {}          # client_id -> {"ip": str, "expires": float}
ip_in_use = {}       # ip -> client_id
pending_offers = {}  # (client_id, xid) -> {"ip": str, "expires": float}
last_ip_by_client = {}   # client_id -> last assigned ip
next_ip_index = 0
lock = threading.Lock()

statistics = {
    "discover_received": 0,
    "offer_sent": 0,
    "request_received": 0,
    "ack_sent": 0,
    "nak_sent": 0,
    "release_received": 0
}


def cleanup_loop():
    while True:
        now = time.time()
        with lock:
            # cleanup expired leases
            expired_leases = [cid for cid, d in leases.items() if d["expires"] <= now]
            for cid in expired_leases:
                ip = leases[cid]["ip"]
                leases.pop(cid, None)
                ip_in_use.pop(ip, None)
                print(f"[LEASE EXPIRED] client_id={cid} ip={ip}")

            # cleanup expired pending offers
            expired_offers = [key for key, d in pending_offers.items() if d["expires"] <= now]
            for key in expired_offers:
                ip = pending_offers[key]["ip"]
                pending_offers.pop(key, None)
                print(f"[OFFER EXPIRED] key={key} ip={ip}")

        time.sleep(2)

def get_free_ip():
    global next_ip_index

    with lock:
        offered_ips = {d["ip"] for d in pending_offers.values()}
        pool_size = len(IP_POOL)

        for i in range(pool_size):
            index = (next_ip_index + i) % pool_size
            ip = IP_POOL[index]

            if ip not in ip_in_use and ip not in offered_ips:
                next_ip_index = (index + 1) % pool_size
                return ip

    return None


def handle_discover(msg):
    client_id = msg.get("client_id")
    xid = msg.get("xid")

    if not client_id or xid is None:
        return {
            "type": "NAK",
            "xid": xid,
            "reason": "MISSING_FIELDS"
        }

    now = time.time()

    with lock:
        # valid lease exists -> re-offer same IP
        if client_id in leases and leases[client_id]["expires"] > now:
            ip = leases[client_id]["ip"]
            pending_offers[(client_id, xid)] = {"ip": ip, "expires": now + OFFER_TTL}
            return {
                "type": "OFFER",
                "xid": xid,
                "offered_ip": ip,
                "lease_time": LEASE_TIME,
                "server_id": SERVER_ID
            }

        # no active lease, but client had an old IP -> try to reuse it if free
        old_ip = last_ip_by_client.get(client_id)
        if old_ip and old_ip not in ip_in_use:
            offered_ips = {d["ip"] for d in pending_offers.values()}
            if old_ip not in offered_ips:
                pending_offers[(client_id, xid)] = {"ip": old_ip, "expires": now + OFFER_TTL}
                return {
                    "type": "OFFER",
                    "xid": xid,
                    "offered_ip": old_ip,
                    "lease_time": LEASE_TIME,
                    "server_id": SERVER_ID
                }

    ip = get_free_ip()
    if not ip:
        return {
            "type": "NAK",
            "xid": xid,
            "reason": "POOL_EXHAUSTED"
        }

    with lock:
        pending_offers[(client_id, xid)] = {"ip": ip, "expires": now + OFFER_TTL}

    return {
        "type": "OFFER",
        "xid": xid,
        "offered_ip": ip,
        "lease_time": LEASE_TIME,
        "server_id": SERVER_ID
    }


def handle_request(msg):
    client_id = msg.get("client_id")
    xid = msg.get("xid")
    server_id = msg.get("server_id")
    requested_ip = msg.get("requested_ip")

    if not client_id or xid is None or not requested_ip:
        return {
            "type": "NAK",
            "xid": xid,
            "reason": "MISSING_FIELDS"
        }

    if server_id != SERVER_ID:
        return {
            "type": "NAK",
            "xid": xid,
            "reason": "WRONG_SERVER_ID"
        }

    now = time.time()
    key = (client_id, xid)

    with lock:
        # If client already has that lease -> renew
        if client_id in leases and leases[client_id]["ip"] == requested_ip and leases[client_id]["expires"] > now:
            leases[client_id]["expires"] = now + LEASE_TIME
            return {
                "type": "ACK",
                "xid": xid,
                "assigned_ip": requested_ip,
                "lease_time": LEASE_TIME,
                "lease_start_time": int(now),
                "dns_ip": DNS_LOCAL_IP,
                "app_server_ip": APP_SERVER_IP,
                "subnet_mask": SUBNET_MASK,
                "router": ROUTER_IP,
                "domain_name": DOMAIN_NAME,
                "server_id": SERVER_ID
            }

        # must have matching pending offer
        if key not in pending_offers:
            return {
                "type": "NAK",
                "xid": xid,
                "reason": "NO_PENDING_OFFER"
            }

        offered = pending_offers[key]
        if offered["expires"] <= now:
            pending_offers.pop(key, None)
            return {
                "type": "NAK",
                "xid": xid,
                "reason": "OFFER_EXPIRED"
            }

        if offered["ip"] != requested_ip:
            return {
                "type": "NAK",
                "xid": xid,
                "reason": "IP_MISMATCH"
            }

        # commit lease
        leases[client_id] = {"ip": requested_ip, "expires": now + LEASE_TIME}
        ip_in_use[requested_ip] = client_id
        last_ip_by_client[client_id] = requested_ip
        pending_offers.pop(key, None)

    print(f"[LEASE GRANTED] client_id={client_id} ip={requested_ip}")
    return {
        "type": "ACK",
        "xid": xid,
        "assigned_ip": requested_ip,
        "lease_time": LEASE_TIME,
        "lease_start_time": int(now),
        "dns_ip": DNS_LOCAL_IP,
        "app_server_ip": APP_SERVER_IP,
        "subnet_mask": SUBNET_MASK,
        "router": ROUTER_IP,
        "domain_name": DOMAIN_NAME,
        "server_id": SERVER_ID
    }

def handle_release(msg):
    client_id = msg.get("client_id")
    xid = msg.get("xid")

    if not client_id:
        return {"type": "NAK", "xid": xid, "reason": "MISSING_CLIENT_ID"}

    with lock:
        if client_id not in leases:
            return {"type": "ACK", "xid": xid, "released": False, "reason": "NO_ACTIVE_LEASE"}

        ip = leases[client_id]["ip"]
        leases.pop(client_id, None)
        ip_in_use.pop(ip, None)

        # לנקות offers תלויים של אותו client (נחמד)
        to_delete = [k for k in pending_offers.keys() if k[0] == client_id]
        for k in to_delete:
            pending_offers.pop(k, None)

    print(f"[LEASE RELEASED] client_id={client_id} ip={ip}")
    return {"type": "ACK", "xid": xid, "released": True, "released_ip": ip}

def print_statistics_loop():
    while True:
        time.sleep(20)

        with lock:
            active_leases = len(leases)
            pending_count = len(pending_offers)

            print("\n========== DHCP STATISTICS ==========")
            print(f"DISCOVER received : {statistics['discover_received']}")
            print(f"OFFER sent        : {statistics['offer_sent']}")
            print(f"REQUEST received  : {statistics['request_received']}")
            print(f"ACK sent          : {statistics['ack_sent']}")
            print(f"NAK sent          : {statistics['nak_sent']}")
            print(f"RELEASE received  : {statistics['release_received']}")
            print(f"Active leases     : {active_leases}")
            print(f"Pending offers    : {pending_count}")
            print("========================================\n")


def start_server():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((DHCP_SERVER_IP, DHCP_SERVER_PORT))
    print(f"[DHCP] listening on: {DHCP_SERVER_IP}:{DHCP_SERVER_PORT}")

    while True:
        data, addr = sock.recvfrom(4096)
        try:
            msg = json.loads(data.decode())
        except Exception:
            continue

        mtype = msg.get("type")
        with lock:
            if mtype == "DISCOVER":
                statistics["discover_received"] += 1
            elif mtype == "REQUEST":
                statistics["request_received"] += 1
            elif mtype == "RELEASE":
                statistics["release_received"] += 1

        if mtype == "DISCOVER":
            resp = handle_discover(msg)
        elif mtype == "REQUEST":
            resp = handle_request(msg)
        elif mtype == "RELEASE":
            resp = handle_release(msg)
        else:
            resp = {"type": "NAK", "xid": msg.get("xid"), "reason": "UNKNOWN_TYPE"}

        resp_type = resp.get("type")

        with lock:
            if resp_type == "OFFER":
                statistics["offer_sent"] += 1
            elif resp_type == "ACK":
                statistics["ack_sent"] += 1
            elif resp_type == "NAK":
                statistics["nak_sent"] += 1

        print(f"[DHCP] RX {mtype} from {addr} -> TX {resp_type} xid={resp.get('xid')} client_id={msg.get('client_id')}")

        if SIMULATE_ACK_LOSS and resp_type == "ACK" and random.random() < ACK_LOSS_PROBABILITY:
            print("[TEST] Dropping ACK to simulate loss")
            continue

        sock.sendto(json.dumps(resp).encode(), addr)


if __name__ == "__main__":
    threading.Thread(target=cleanup_loop, daemon=True).start()
    threading.Thread(target=print_statistics_loop, daemon=True).start()
    start_server()
