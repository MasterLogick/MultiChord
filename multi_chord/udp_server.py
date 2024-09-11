import asyncio
import collections
from typing import Optional

from . import rpc
from . import remote_node
from . import interface
from . import node_pool


class UdpServer(asyncio.DatagramProtocol, interface.Interface):
    """
    Udp server is responsible for a network interface implementation, i.e. message sending and receiving.
    """

    def __init__(self, address: tuple[str, int]):
        """
        Creates a UdpServer instance. Call start() function to bind socket and start listening.
        :param address: Server socket bind address.
        """
        self._node_pool: Optional[node_pool.NodePool] = None
        self._address = address
        self._transport = None
        self._pending_messages: dict[tuple[str, int], bytes] = collections.defaultdict(lambda: b"")

    def connection_made(self, transport):
        """
        This function is called when a server socket is bound.
        :param transport: Wrapped server socket
        """
        self._transport = transport
        sockname = self._transport.get_extra_info("sockname")
        print(f"running server on {sockname[0]}:{sockname[1]}")

    def datagram_received(self, data: bytes, addr: tuple[str, int]):
        """
        This function is called when udp socket receives data. Server tries to parse rpc message
        and send it to node pool.
        :param data: received data
        :param addr: sender address
        """
        msg = self._pending_messages[addr] + data
        address = addr[0] + ":" + str(addr[1])
        message, remainder = rpc.parse_rpc_message(msg, address)
        if message is not None:
            # print(f"got message from {address}: {message}")
            self._node_pool.process_message(remote_node.RemoteNode(message.from_id, address), message)
        if len(remainder) > 0:
            self._pending_messages[addr] = remainder
        else:
            del self._pending_messages[addr]

    async def start(self, pool: node_pool.NodePool):
        """
        Binds server socket and starts listening in python asyncio event loop.
        :param pool: node pool, that will consume messages from this server
        """
        assert self._node_pool is None
        self._node_pool = pool
        await asyncio.get_event_loop().create_datagram_endpoint(lambda: self, self._address)

    def stop(self):
        """
        Stops the server. Closes server socket.
        """
        self._transport.close()

    def send_message(self, remote: remote_node.RemoteNode, message: rpc.RpcMessage):
        """
        Serializes and sends message over the network to specified remote node
        :param remote: message destination
        :param message: payload
        """
        ip, port = remote.address.split(":")
        self._transport.sendto(message.to_bytes(), (ip, int(port)))
        # print(f"sent message to {description.address}: {message}")
