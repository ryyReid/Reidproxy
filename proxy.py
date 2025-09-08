import socket
import threading
import select

def handle_client(client_socket):
    try:
        request = client_socket.recv(1024)
        if not request:
            client_socket.close()
            return

        first_line = request.split(b'\n')[0]
        try:
            method = first_line.split(b' ')[0]
        except IndexError:
            client_socket.close()
            return

        if method == b'CONNECT':
            handle_https_request(client_socket, request)
        else:
            handle_http_request(client_socket, request)
    except Exception as e:
        print(f"[*] Client handling exception: {e}", flush=True)
        client_socket.close()

def handle_http_request(client_socket, request):
    try:
        try:
            first_line = request.decode('ascii').split('\n')[0]
            parts = first_line.split(' ')
            if len(parts) != 3:
                client_socket.close()
                return
            method, url, version = parts
        except (UnicodeDecodeError, ValueError):
            client_socket.close()
            return

        http_pos = url.find("://")
        if http_pos == -1:
            temp = url
        else:
            temp = url[(http_pos + 3):]

        port_pos = temp.find(":")
        webserver_pos = temp.find("/")
        if webserver_pos == -1:
            webserver_pos = len(temp)

        webserver = ""
        port = -1
        if port_pos == -1 or webserver_pos < port_pos:
            port = 80
            webserver = temp[:webserver_pos]
        else:
            try:
                port = int(temp[(port_pos + 1):][:webserver_pos - port_pos - 1])
                webserver = temp[:port_pos]
            except ValueError:
                client_socket.close()
                return

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((webserver, port))
        s.send(request)

        while True:
            data = s.recv(4096)
            if len(data) > 0:
                client_socket.send(data)
            else:
                break
        s.close()
        client_socket.close()
    except Exception as e:
        print(f"[*] HTTP Exception: {e}", flush=True)
        client_socket.close()

def handle_https_request(client_socket, request):
    try:
        first_line = request.split(b'\n')[0]
        host_port = first_line.split(b' ')[1]
        host, port = host_port.split(b':')

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((host, int(port)))
        client_socket.send(b"HTTP/1.1 200 OK\r\n\r\n")

        sockets = [client_socket, s]
        while True:
            readable, writable, exceptional = select.select(sockets, [], sockets, 10)
            if exceptional:
                break
            if not readable and not writable:
                continue

            for sock in readable:
                data = sock.recv(4096)
                if not data:
                    break
                if sock is client_socket:
                    s.sendall(data)
                else:
                    client_socket.sendall(data)
            else:
                continue
            break

    except Exception as e:
        print(f"[*] HTTPS Exception: {e}", flush=True)
        pass
    finally:
        client_socket.close()
        s.close()

def start_server(local_host="127.0.0.1", local_port=6767):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((local_host, local_port))
    server.listen(5)
    print(f"[*] Listening on {local_host}:{local_port}", flush=True)

    while True:
        client_socket, addr = server.accept()
        print(f"[*] Accepted connection from {addr[0]}:{addr[1]}", flush=True)

        client_handler = threading.Thread(target=handle_client, args=(client_socket,))
        client_handler.start()

if __name__ == "__main__":
    start_server()
