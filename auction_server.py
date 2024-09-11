"""
CSEN233 HW4

Gauri Dave (gdave@scu.edu)
Yukun Li (yli26@scu.edu)
Prasanna Sand (psand@scu.edu)
Divya Shetty (dshetty2@scu.edu)

Implementation of a TCP server that can host an "auction".
Sends messages to the client(s) in the format of HTTP POST messages.
Will handle any bid submissions while announcing auction status in intervals.
Log files generated for auction behavior
"""

import socket
import threading
import json
import time
import logging
import argparse


logging.basicConfig(filename='auction_server.log', level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)s - %(message)s')


class AuctionServer:
    def __init__(self, start_time, next_auction=None):
        self.threads = []
        
        self.host = None
        self.port = None
        
        self.start = start_time
        self.clients = []
        self.highest_bid = 0
        self.highest_bidder = None
        self.auction_open = False
        self.chant = 0
        self.next_auction = next_auction

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.bind_to_local(self.socket)
            self.socket.listen()
        except Exception as e:
            self.close_server()
            logging.info(f"Error starting up auction server:\n{e}")


    def bind_to_local(self, tcp_socket):
        localhost = socket.gethostname()
        tcp_socket.bind((localhost, 0))
        self.host = tcp_socket.getsockname()[0]
        self.port = tcp_socket.getsockname()[1]
        print(f"Auction server started on {self.host}:{self.port}")


    def start_server(self):
        t = threading.Thread(target=self.add_client, daemon=True)
        self.threads.append(t)
        t.start()

        while not self.auction_open:
            if time.time() >= self.start:
                self.auction_open = True
                logging.info("Auction will begin")

        self.broadcast("STATUS")
        self.scheduled_broadcast()


    def close_server(self):
        self.auction_open = False
        print("Closing the auction...")
        for client in self.clients:
            client.close()
            self.clients.remove(client)
        self.socket.close()
        logging.info("Server successfully closed")


    def add_client(self):
        while True:
            try:
                client, address = self.socket.accept()
                logging.info(f"Connection attempt from {address}")

                join = client.recv(1024).decode("utf-8")
                req_line, body = self.parse_msg(join)

                if body and body["request_type"] == "JOIN":
                    print(f"Client {address} has joined")
                    self.clients.append(client)
                    self.post_request(client, "STATUS")
                    threading.Thread(target=self.handle_client, args=(client,), daemon=True).start()
                else:
                    self.status_response(client, 400, "Bad Request")
                    client.close()

            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                logging.info(f"Error decoding join message from {address}: {e}")
                self.status_response(client, 400, "Bad Message Format")
                client.close()
            except Exception as e:
                if not self.auction_open:
                    break
                logging.debug(f"Error accepting connection: {e}")


    def handle_client(self, client):
        client_address = client.getpeername()
        logging.info(f"Handling new client: {client_address}")
        try:
            while self.auction_open:
                bid = client.recv(1024).decode('utf-8')
                if not bid:
                    logging.info(f"Client {client_address} disconnected gracefully.")
                    break

                req_line, body = self.parse_msg(bid)
                if body and body["bid_amount"] and body["bid_amount"].isdigit():
                    self.status_response(client, 200, "OK")
                    logging.info(f"Received bid from {client_address}")

                    if self.process_bid(client, int(body["bid_amount"])) == -1:
                        break
                else:
                    self.status_response(client, 400, "Bad Request")

        except Exception as e:
            logging.error(f"Error handling client {client_address}: {e}", exc_info=True)
        finally:
            self.remove_client(client, client_address)


    def remove_client(self, client, client_address):
        if client in self.clients:
            self.clients.remove(client)
        try:
            client.close()
        except Exception as e:
            logging.error(f"Error closing client socket {client_address}: {e}")
        logging.info(f"Client {client_address} has been removed and socket closed.")


    def process_bid(self, client, bid):
        if self.auction_open:
            if bid > self.highest_bid:
                self.highest_bid = bid
                self.highest_bidder = client.getpeername()[0]
                self.chant = 0
                self.post_request(client, "BID_ACK", bid_status="ACCEPTED")
            else:
                self.post_request(client, "BID_ACK", bid_status="REJECTED")
            return
        return -1


    def scheduled_broadcast(self):
        while self.auction_open:
            time.sleep(10)
            self.chant += 1
            if self.chant > 3:
                self.auction_open = False
                self.broadcast("CLOSE")
                logging.info(f"Auction complete. Winner is {self.highest_bidder} with {self.highest_bid}")
                break
            else:
                self.broadcast("STATUS")


    def broadcast(self, request_type):
        for client in self.clients:
            self.post_request(client, request_type)


    def parse_msg(self, msg):
        response_list = msg.split('\r\n')
        req_line = response_list[0]
        body = response_list[-1]
        if body:
            body = json.loads(body)
        return (req_line, body)


    def status_response(self, client, status_code, message):
        response = f"HTTP/1.1 {status_code} {message}\r\n\r\n"
        client.sendall(response.encode())

        
    def post_request(self, client, request_type, bid_status=None):
        url = f"http://{client.getpeername()[0]}:{client.getpeername()[1]}"
        host = f"Host: {url}"
        header = {"content_type": "Content-Type: application/json"}

        if request_type == "STATUS":
            body = {
                "request_type": request_type,
                "status": "OPEN" if self.auction_open else "CLOSE",
                "highest_bid": self.highest_bid,
                "highest_bidder": self.highest_bidder,
                "chant": self.chant,
                "n_clients": len(self.clients),
                "next_auction": self.next_auction
                }
        elif request_type == "BID_ACK":
            body = {
                "request_type": request_type,
                "bid_status": bid_status
                }
        elif request_type == "CLOSE":
            body = {
                "request_type": request_type,
                "highest_bid": self.highest_bid,
                "highest_bidder": self.highest_bidder
                }
        else:
            self.status_response(client, 500, "Internal server error")
            return
        
        request = f"POST / HTTP/1.1\r\n{host}\r\n{header['content_type']}\r\n\r\n{json.dumps(body)}"
        client.sendall(request.encode())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-t', '--time', type=int, help="auction start time")
    args = parser.parse_args()

    print(args.time)

    start_time = args.time if args.time else time.time()

    auction_server = AuctionServer(start_time=start_time)
    
    try:
        auction_server.start_server()
    except KeyboardInterrupt:
        pass
    finally:
        auction_server.close_server()
