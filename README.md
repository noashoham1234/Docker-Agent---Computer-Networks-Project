# 🌐 Network Simulation & Automated Docker Deployment

This project simulates a complete network environment consisting of **DHCP** and **DNS** servers, alongside an Application Server. The App Server can handle client requests using both standard **TCP** and a custom **RUDP** (Reliable UDP) protocol to automatically deploy Nginx web servers using **Docker**.

## ✨ Key Features
* **DHCP Server**: Simulates a full IP allocation process (DORA - Discover, Offer, Request, Ack), including lease time management and IP releasing.
* **DNS Server**: A local DNS server that listens for and resolves queries.
* **RUDP (Reliable UDP)**: A custom implementation of a reliable protocol over UDP. It features a handshake, a sliding window mechanism, acknowledgments (ACKs), and packet loss handling.
* **TCP Server**: A concurrent server listening for standard TCP requests.
* **Docker Integration**: Automated creation and teardown of Docker containers (Nginx) based on client requests. It dynamically injects client data (username, assigned IP, port, and protocol) into a dedicated HTML template.

---

## 🛠️ Prerequisites
To run this project, ensure you have the following installed and running on your machine:
1. **Python 3.x**
2. **Docker**: Docker must be installed and actively running (Docker Desktop or Docker Daemon) so the App Server can spin up containers.

*Note: All Python libraries used in this project are built-in, so there is no need to run `pip install`.*

### 🐳 Installing Docker Desktop on Windows
If you are using Windows, you need to install Docker Desktop to allow the Application Server to spin up containers. Follow these steps:

1. **Download Docker Desktop**: Go to the official Docker website and download the installer for Windows:
   👉 [Download Docker Desktop for Windows](https://docs.docker.com/desktop/install/windows-install/)
2. **Run the Installer**: Double-click `Docker Desktop Installer.exe` to run it.
3. **WSL 2 Configuration**: During the installation process, ensure that the option **"Use WSL 2 instead of Hyper-V"** is checked (this is highly recommended for better performance).
4. **Finish and Restart**: Follow the instructions on the installation wizard. You may be prompted to restart your computer.
5. **Start Docker**: After restarting, search for "Docker Desktop" in your Windows Start menu and open it. Accept the terms of service. Wait until the Docker icon in the bottom-left corner of the app turns **green** (indicating the engine is running).
6. **Verify Installation**: Open a new terminal (Command Prompt or PowerShell) and run:
   ```bash
   docker --version
   ```
   *If you see the Docker version printed, you are good to go!*

---

## 📁 Project Structure

```text
network-final/
├── README.md                 # Main project documentation
└── src/                      # Source code directory
    ├── .idea/                # IDE configuration folder (PyCharm)
    ├── html/                 # Contains template.html and generated web pages
    ├── app_server.py         # Main App Server (TCP/RUDP & Docker integration)
    ├── client.py             # Client script for initiating connections
    ├── client_id_1.txt       # Auto-generated unique ID file for the client
    ├── constants.py          # Configuration and network constants (IPs, ports, etc.)
    ├── dhcp_server.py        # DHCP Server implementation
    ├── dns_server.py         # Local DNS Server implementation
    ├── message_types.py      # RUDP message type definitions
    └── rudp_func.py          # Helper functions for the RUDP protocol
```

---

## 🚀 How to Run the Project

You will need to open 4 separate terminal windows in your project directory (`src`) and run the components in the following order:

### 1. Start the DHCP Server
In the first terminal, run the DHCP server to handle IP allocations:
```bash
python dhcp_server.py
```

### 2. Start the DNS Server
In the second terminal, run the local DNS server:
```bash
python dns_server.py
```

### 3. Start the Application Server
In the third terminal, start the main server (make sure Docker is running in the background):
```bash
python app_server.py
```

### 4. Run the Client
In the fourth terminal, run the client script. The client will request an IP, resolve the DNS, and ask the server to deploy a website.
You can choose the transport protocol (`tcp` or `rudp`) and the client number via command-line arguments:

**Run with TCP (Default):**
```bash
python client.py --client 1 --protocol tcp
```

**Run with RUDP:**
```bash
python client.py --client 2 --protocol rudp
```

During execution, the client will prompt you for details:
* **Name**: Your name.
* **Container port**: The port you want the website to be hosted on (e.g., `8080`).
* **Container name**: A unique name for your Docker container (e.g., `my_nginx_1`).

Once the server returns a `SUCCESS` message, open your web browser and navigate to `http://localhost:<YOUR_PORT>` to see your newly deployed website! 🎉

### 5. 🧹 Shutting Down & Cleanup
When you are done testing the project, you can gracefully stop the servers by pressing `Ctrl+C` in their respective terminals. 

To ensure your machine stays clean and no residual Docker containers are left running in the background, you can remove all containers generated by this project by running the following command in your terminal:
```bash
docker rm -f $(docker ps -a -q --filter "label=managed_by=my_python_server")
```
* Note: This command safely targets only the containers created by the App Server (using a specific label) and will not affect any of your other personal Docker containers.
---

## 🐛 Troubleshooting
* **DOCKER ERROR**: Ensure the Docker daemon is running. If you get an error stating the container name is already in use, choose a different name in the client prompt, or clear the old container using `docker rm -f <container_name>`.
* **Address already in use**: One of the servers might already be running in the background. Close old terminal windows or kill the processes occupying ports `12345`, `6767`, or `5358`.