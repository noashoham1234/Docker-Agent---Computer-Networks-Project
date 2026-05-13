import socket
from constants import *

# Local address dictionary
LOCAL_RECORDS = {
    "myagent.local": "127.0.0.1"
}


def extract_domain_name(data):
    try:
        domain = ""
        i = 12
        length = data[i]
        while length != 0:
            domain += data[i + 1:i + 1 + length].decode() + "."
            i += length + 1
            length = data[i]
        return domain[:-1]
    except:
        return "Unknown"


def build_dns_response(request_data, ip):
    header = request_data[:2] + b'\x81\x80\x00\x01\x00\x01\x00\x00\x00\x00'
    question = request_data[12:]
    answer = b'\xc0\x0c\x00\x01\x00\x01\x00\x00\x00\x3c\x00\x04' + socket.inet_aton(ip)

    return header + question + answer

def start_dns_server():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # This line allows the port to be reused immediately after the server stops
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        server_socket.bind((DNS_LOCAL_IP, DNS_LOCAL_PORT))
        print(f"DNS Server is UP on {DNS_LOCAL_IP}:{DNS_LOCAL_PORT}")
    except Exception as e:
        print(f"Error starting server: {e}")
        return

    print("[INFO] Waiting for DNS queries...")

    while True:
        try:
            # Receive a request
            data, client_address = server_socket.recvfrom(BUFFER_SIZE)
            domain_requested = extract_domain_name(data)

            # Checking the local dictionary (for future logic)
            if domain_requested in LOCAL_RECORDS:
                server_socket.sendto(build_dns_response(data, LOCAL_RECORDS[domain_requested]), client_address)
                continue

            # Contacting Google (Forwarding)
            proxy_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            proxy_socket.settimeout(2.0)
            proxy_socket.sendto(data, GOOGLE_DNS)

            response, _ = proxy_socket.recvfrom(BUFFER_SIZE)

            # Returning the answer to the client
            server_socket.sendto(response, client_address)
            proxy_socket.close()

        except (socket.timeout, Exception):
            continue


if __name__ == "__main__":
    start_dns_server()