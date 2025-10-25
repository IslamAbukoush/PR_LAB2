# client.py
import sys
import socket
import os

if len(sys.argv) != 5:
    print("Usage: python client.py server_host server_port url_path directory")
    sys.exit(1)

server_host = sys.argv[1]
server_port = int(sys.argv[2])
url_path = sys.argv[3]
save_dir = sys.argv[4]

# Ensure save directory exists
os.makedirs(save_dir, exist_ok=True)

# Create HTTP GET request
request = f"GET {url_path} HTTP/1.1\r\nHost: {server_host}\r\nConnection: close\r\n\r\n"

# Connect to server and send request
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.connect((server_host, server_port))
    s.sendall(request.encode())
    
    # Receive full response
    response = b""
    while True:
        chunk = s.recv(4096)
        if not chunk:
            break
        response += chunk

# Split headers and body
header_end = response.find(b"\r\n\r\n")
headers = response[:header_end].decode()
body = response[header_end+4:]

# Determine content type
content_type = None
for line in headers.split("\r\n"):
    if line.lower().startswith("content-type:"):
        content_type = line.split(":")[1].strip()
        break

# Handle response based on content type
if content_type is None or "text/html" in content_type:
    # HTML response, print body
    print(body.decode(errors="ignore"))
elif "application/octet-stream" in content_type or "image/png" in content_type or "application/pdf" in content_type:
    # Binary file, save to directory
    filename = os.path.basename(url_path)
    save_path = os.path.join(save_dir, filename)
    with open(save_path, "wb") as f:
        f.write(body)
    print(f"Saved file to: {save_path}")
else:
    print("Unhandled content type:", content_type)
