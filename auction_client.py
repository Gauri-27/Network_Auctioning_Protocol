"""
CSEN233 HW4

Gauri Dave (gdave@scu.edu)
Yukun Li (yli26@scu.edu)
Prasanna Sand (psand@scu.edu)
Divya Shetty (dshetty2@scu.edu)

Implementation of a TCP client that can participate in an "auction".
Sends messages to the server in the format of HTTP POST messages.
Will simultaneously allow for bid entries and receive server messages.
"""

import socket
import threading
import json
import argparse
import time


class AuctionClient:
    def __init__(self, server_host, server_port):
        self.server_host = server_host
        self.server_port = server_port
        self.socket = None
        self.auction_started = False
        self.participating = True


    def join_auction(self):
        # connect to auction server
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect((self.server_host, self.server_port))
        print("Connected to auction server.")

        # send JOIN msg to participate in auction
        self.post_request("JOIN")
        join_response = self.socket.recv(1024).decode()
        reqline, body = self.parse_msg(join_response)
        print(join_response)
        if not body and "200" not in reqline:
            raise Exception("Could not successfully join auction. Try again")
        
        print(body)
        # check if auction has started or not
        self.auction_started = True if body["status"] == "OPEN" else False
        # thread to listen for auction "announcements"
        listening = threading.Thread(target=self.listen_for_server)
        listening.start()

        # while auction is ongoing, option to submit bid
        while True:
            if self.auction_started:
                user_input = input("Enter bid amount or EXIT to leave:\n")
                if user_input.upper() == "EXIT":
                    self.participating = False
                    listening.join()
                    break
                # check if auction CLOSE while input open
                if self.auction_started:
                    self.post_request("BID", user_input)
                    time.sleep(0.5)
                else:
                    print("Auction has closed. Cannot bid.")
                    break
            else:
                self.participating = False
                listening.join()
                break


    def listen_for_server(self):
        while self.participating:
            try:
                broadcast = self.socket.recv(1024).decode("utf-8")
            except ConnectionResetError:
                print("Auction was suddenly closed. Type EXIT.")
                self.auction_started = False
                break

            if not broadcast:
                print(f"The socket was unexpectedly closed.")
                self.auction_started = False
                break

            reqline, body = self.parse_msg(broadcast)
            # check for HTTP codes
            if not body:
                print(f"{reqline}")
                continue

            # check for start of auction (if joined before it began)
            if not self.auction_started and body["request_type"] == "STATUS" and body["status"] == "OPEN":
                self.auction_started = True
            # check for bid acknowledgement
            elif body["request_type"] == "BID_ACK" or body["request_type"] == "STATUS" :
                print(body)
            # check if auction is complete
            elif body["request_type"] == "CLOSE":
                print(body)
                self.auction_started = False
                break


    def close_connection(self):
        self.socket.close()
        print("Exited auction.")


    def parse_msg(self, msg):
        response_list = msg.split('\r\n')
        req_line = response_list[0]
        body = response_list[-1]
        if body:
            body = json.loads(body)
        return (req_line, body)


    def post_request(self, request_type, bid_amount=0):
        url = f"http://{self.server_host}:{self.server_port}"
        host = f"Host: {url}"
        header = "Content-Type: application/json"

        if request_type == "JOIN":
            body = {
                "request_type": request_type
                }
        elif request_type == "BID":
            body = {
                "request_type": request_type,
                "bid_amount": bid_amount
                }
        else:
            print("Error with request_type: {request_type}")
            return
        
        request = f"POST / HTTP/1.1\r\n{host}\r\n{header}\r\n\r\n{json.dumps(body)}"
        self.socket.sendall(request.encode())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--host', action='store', required=True, help="auction server ip")
    parser.add_argument('-p', '--port', type=int, required=True, help="auction server port")
    args = parser.parse_args()

    client = AuctionClient(args.host, args.port)

    try:
        client.join_auction()  
    except KeyboardInterrupt:
        pass
    finally:
        client.close_connection()