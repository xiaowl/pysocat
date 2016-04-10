import socket
import select

version = (0, 1, 0)


class Pipe(object):
    """
    A Pipe connects 2 sockets, in a unidirectional way, from src to dst.
    Thus, to forward network traffic from A to B, 2 pipes will be setup:
    One Pipe reads from A and writes to B, another from B to A.
    """

    def __init__(self, src, dst):
        self.src = src
        self.dst = dst
        self.src_ready = False
        self.dst_ready = False
        self.started = False
        super(Pipe, self).__init__()

    def shutdown(self):
        self.src.close()
        self.dst.close()

    def is_ready(self):
        return self.src_ready and self.dst_ready

    def relay(self, size=4096):
        data = self.src.recv(size)
        if data:
            if not self.started:
                print "Start relaying", self.src.getpeername(),\
                    "->", self.dst.getpeername()
                self.started = True
            self.dst.send(data)
            # waiting for epoll to tell us the dst is writable again.
            self.dst_ready = False
        return bool(data)


def connect(remote):
    so = socket.socket()
    so.connect(remote)
    so.setblocking(0)
    return so


def serve(local, remote):
    so = socket.socket()
    so.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    so.bind(local)
    so.listen(1024)
    so.setblocking(0)

    epoll = select.epoll()
    epoll.register(so.fileno(), select.EPOLLIN)

    print local, "->", remote
    try:
        pipes, peers, conn = {}, {}, {}

        def cleanup(fd):
            print "Cleaning up...", conn[fd].getpeername()
            epoll.unregister(fd)
            epoll.unregister(peers[fd])
            del conn[fd]
            del conn[peers[fd]]
            # only shutdown one pipe, as it closes both sockets
            pipes[fd].shutdown()
            del pipes[peers[fd]]
            del pipes[fd]
            del peers[peers[fd]]
            del peers[fd]

        while True:
            events = epoll.poll(5)
            for fd, event in events:
                # got server event
                if fd == so.fileno():
                    conn0, _ = so.accept()
                    conn0.setblocking(0)
                    epoll.register(conn0.fileno(),
                                   select.EPOLLIN | select.EPOLLOUT)

                    # setup remote network connection
                    conn1 = connect(remote)
                    epoll.register(conn1.fileno(),
                                   select.EPOLLIN | select.EPOLLOUT)

                    # bookkeeping
                    pipes[conn0.fileno()] = Pipe(conn0, conn1)
                    pipes[conn1.fileno()] = Pipe(conn1, conn0)
                    peers[conn0.fileno()] = conn1.fileno()
                    peers[conn1.fileno()] = conn0.fileno()
                    conn[conn0.fileno()] = conn0
                    conn[conn1.fileno()] = conn1

                else:
                    # some socket has data available
                    if event & select.EPOLLIN:
                        pipes[fd].src_ready = True
                        # only read these data if the pipe is ready
                        # if it's not, no data will be consumed, thus epoll
                        # will re-raise EPOLLIN event. (Level-Trigger)
                        #
                        # if the relay() fail, which means nothing read
                        # back from src, the network is closed, so cleanup.
                        if pipes[fd].is_ready() and not pipes[fd].relay():
                            cleanup(fd)
                            break

                        epoll.modify(
                            peers[fd], select.EPOLLIN | select.EPOLLOUT)

                    if event & select.EPOLLOUT:
                        pipes[peers[fd]].dst_ready = True
                        # when write is done, EPOLLOUT event will be registered
                        # again.
                        epoll.modify(fd, select.EPOLLIN)

    finally:
        epoll.unregister(so.fileno())
        epoll.close()
        so.close()


if __name__ == "__main__":
    import argparse
    import sys
    parser = argparse.ArgumentParser(description="Relay TCP traffic.")
    parser.add_argument("-l", dest="src", metavar="",
                        help="wait tranffic from, 127.0.0.1:2020")
    parser.add_argument("-f", dest="dst", metavar="",
                        help="forward traffic to, example.com:3030")
    parser.add_argument("-v", action='store_true',
                        dest='version', help='version')
    args = parser.parse_args()
    if args.version:
        print ".".join(str(v) for v in version)
        sys.exit(0)
    if not (args.src and args.dst):
        parser.print_help()
        sys.exit(1)

    def tuplify(addr):
        h, p = addr.split(":")
        return h, int(p)

    serve(tuplify(args.src), tuplify(args.dst))
