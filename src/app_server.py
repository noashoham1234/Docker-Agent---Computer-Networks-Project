import socket
import json
import subprocess
import os
import shutil
import threading
from rudp_func import recv_rudp_msg, send_rudp_msg
from message_types import *

LISTENING_IP = '0.0.0.0'
LISTENING_PORT = 12345


def deploy_container_logic(data):
    user_name = data.get('name')
    container_name = data.get('container_name')
    website_port = data.get('port')
    protocol = data.get('protocol', 'Unknown')
    assigned_ip = data.get('assigned_ip')
    kill_container_on_port(website_port)

    client_number = assigned_ip.split('.')[-1]
    container_name_suff = container_name + "_" + str(client_number)
    kill_container_by_name(container_name_suff)

    print(f"[Server] Processing deployment for: {user_name} on port {website_port}")

    base_dir = os.path.dirname(os.path.abspath(__file__))

    template_path = os.path.join(base_dir, "html", "template.html")
    output_path = os.path.join(base_dir, "html", "index.html")

    try:
        with open(template_path, "r", encoding="utf-8") as f:
            html_content = f.read()
        final_html = html_content.replace("{{NAME}}", user_name)
        final_html = final_html.replace("{{ASSIGNED_IP}}", assigned_ip)
        final_html = final_html.replace("{{PORT}}", str(website_port))
        final_html = final_html.replace("{{PROTOCOL}}", str(protocol).upper())
        final_html = final_html.replace("{{CONTAINER_NAME}}", container_name_suff)


        with open(output_path, "w", encoding="utf-8") as f:
            f.write(final_html)

    except FileNotFoundError:
        return f"ERROR: Template file missing at {template_path}. Please make sure 'html/template.html' exists."
    except Exception as e:
        return f"ERROR processing HTML: {str(e)}"

    if not shutil.which("docker"):
        return "ERROR: Docker is not installed on the server."

    html_folder = os.path.dirname(output_path)

    cmd = [
        "docker", "run", "-d",
        "-p", f"{website_port}:80",
        "--rm",
        "--name", container_name_suff,
        "--label", "managed_by=my_python_server",
        "-v", f"{html_folder}:/usr/share/nginx/html",
        "nginx"
    ]

    print(f"[Server] Running Docker container '{container_name_suff}'...")
    try:
        result = subprocess.run(cmd, check=True, capture_output=True)
        container_id = result.stdout.decode().strip()[:12]
        return f"SUCCESS! Site deployed. ID: {container_id}. Visit http://localhost:{website_port}"

    except subprocess.CalledProcessError as e:
        return f"DOCKER ERROR: {e.stderr.decode()}"


def start_tcp_server():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server_socket.bind((LISTENING_IP, LISTENING_PORT))
        server_socket.listen(5)
        print(f"[TCP] Server listening on {LISTENING_IP}:{LISTENING_PORT}...")
        while True:
            client_socket, addr = server_socket.accept()
            print(f"[TCP] Connection from {addr}")
            handle_client_connection(client_socket)
    except Exception as e:
        print(f"[TCP] Server Error: {e}")
    finally:
        server_socket.close()


def handle_client_connection(client_socket):
    with client_socket:
        try:
            data = client_socket.recv(4096)
            if not data: return
            json_str = data.decode('utf-8')
            payload = json.loads(json_str)
            response = deploy_container_logic(payload)
            client_socket.sendall(response.encode('utf-8'))
            print("[TCP] Response sent to client.")
        except Exception as e:
            print(f"[TCP] Handler Error: {e}")


def start_rudp_server():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        server_socket.bind((LISTENING_IP, LISTENING_PORT))
        print(f"[RUDP] Server listening on {LISTENING_IP}:{LISTENING_PORT}...")
        expected_seq = 0
        buffer = []
        while True:
            msg, addr = recv_rudp_msg(server_socket)
            if not msg: continue
            msg_type = msg.get("type")

            if msg_type == TYPE_SIN:
                print(f"[RUDP] Handshake initiated by {addr}")
                send_rudp_msg(server_socket, {"type": TYPE_SIN_ACK}, addr)
                expected_seq = 0
                buffer = []
            elif msg_type == TYPE_ACK:
                pass # Handshake complete
            elif msg_type == TYPE_DATA:
                seq = msg.get("seq")
                if seq == expected_seq:
                    buffer.append(msg["payload"])
                    expected_seq += 1
                send_rudp_msg(server_socket, {"type": TYPE_ACK, "ack": expected_seq - 1}, addr)
            elif msg_type == TYPE_END_MESSAGE:
                full_json_str = "".join(buffer)
                print(f"[RUDP] Full payload received.")
                try:
                    payload = json.loads(full_json_str)
                    response_text = deploy_container_logic(payload)
                    send_rudp_msg(server_socket, {"type": "SERVER_RESPONSE", "payload": response_text}, addr)
                except Exception as e:
                    send_rudp_msg(server_socket, {"type": "SERVER_RESPONSE", "payload": f"ERROR: {e}"}, addr)
                expected_seq = 0
                buffer = []
    except Exception as e:
        print(f"[RUDP] Server Error: {e}")
    finally:
        server_socket.close()




def kill_container_on_port(port):
    find_cmd = ["docker", "ps", "-q", "--filter", f"publish={port}"]
    result = subprocess.run(find_cmd, capture_output=True, text=True)
    container_ids = result.stdout.strip().split('\n')
    for c_id in container_ids:
        if c_id:
            print(f"[Server] Cleaning up port {port} (Stopping container {c_id})...")
            subprocess.run(["docker", "rm", "-f", c_id], capture_output=True)
    for c_id in container_ids:
        if c_id:
            print(f" -> Removing container {c_id[:12]}...")
            subprocess.run(["docker", "rm", "-f", c_id], capture_output=True)

    print("[Server] Cleanup complete. Goodbye! 👋")

def kill_container_by_name(container_name):
    find_cmd = ["docker", "ps", "-a", "-q", "--filter", f"name=^{container_name}$"]
    result = subprocess.run(find_cmd, capture_output=True, text=True)
    container_ids = result.stdout.strip().split('\n')

    for c_id in container_ids:
        if c_id:
            print(f"[Server] Cleaning up container name '{container_name}' (Stopping container {c_id[:12]})...")
            subprocess.run(["docker", "rm", "-f", c_id], capture_output=True)


if __name__ == "__main__":
    print("Starting Application Server...")

    tcp_thread = threading.Thread(target=start_tcp_server, daemon=True)
    rudp_thread = threading.Thread(target=start_rudp_server, daemon=True)

    tcp_thread.start()
    rudp_thread.start()

    tcp_thread.join()
    rudp_thread.join()

