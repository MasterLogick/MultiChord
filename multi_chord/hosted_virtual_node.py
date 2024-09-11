import asyncio
import hashlib
import datetime
import random
from typing import Optional, BinaryIO

from . import remote_node
from . import swarm_id
from . import rpc


class AliveRemoteNode:
    """
    Helper class that keeps track of a remote node liveness. Timeout specifies a liveness timeout and send_ping flag.
    When liveness timeout reaches zero, virtual node sends ping request to remote node, resets timeout with command time
    and raises send_ping flag. If remote node can not respond within command time, it will be deleted at the next
    stabilization round.
    """

    def __init__(self, remote: remote_node.RemoteNode, ttl: float):
        self.remote = remote
        self.timeout = datetime.datetime.now() + datetime.timedelta(seconds=ttl)
        self.sent_ping = False

    def __str__(self):
        return f"AliveRemoteNode(remote={self.remote}, timeout={self.timeout})"


class PendingRequest:
    """
    Helper class to keep track of pending request.
    """

    def __init__(self, request_type: rpc.RpcMessageType, future: asyncio.Future):
        self.request_type = request_type
        self.future = future


_finger_table_size = 10


class HostedVirtualNode:
    """
    Virtual node is a main object in the network. Hosted virtual node is locally running node. Every node belongs to one
    node pool. Virtual nodes with the same id form a swarm. Hosted virtual nodes contains routing info, keeps track of
    pending requests and contains a stored value.
    """

    def __init__(self, node_id: swarm_id.SwarmId):
        self.id = node_id
        self.file: Optional[BinaryIO] = None
        self.has_content = False
        self._pending_requests: dict[remote_node.RemoteNode, PendingRequest] = {}
        self._swarm: list[AliveRemoteNode] = []
        self.finger_table: list[Optional[AliveRemoteNode]] = [None] * _finger_table_size
        self.predecessor: Optional[AliveRemoteNode] = None
        self.successor: Optional[AliveRemoteNode] = None
        self.node_pool = None

    def set_content_path(self, file: BinaryIO, has_content: bool):
        """
        Sets value of the node or tells the node that it needs to retrieve value from another node in the swarm.
        :param file: file storage for the value
        :param has_content: True, if file storage already contains value. Otherwise, node will contact swarm and
        download content to this file storage.
        """
        self.file = file
        self.has_content = has_content

    def process_message(self, remote: remote_node.RemoteNode, message: rpc.RpcMessage):
        """Handles rpc requests from remote nodes and resolves rpc responses from this node. Common virtual node
        supports ping requests, GetSwarm requests and GetContent requests"""
        assert message.to_id == self.id
        if message.command.value % 2 == 1:
            if remote in self._pending_requests:
                pending_request = self._pending_requests[remote]
                if pending_request.request_type.value + 1 == message.command.value:
                    pending_request.future.set_result(message)
        elif isinstance(message, rpc.RpcPingRequest):
            self._try_stabilize_with_remote(AliveRemoteNode(remote, self.node_pool.timings.live_interval))
            self.node_pool.send_message(remote, rpc.RpcPingResponse(self.id, remote.id))
        elif isinstance(message, rpc.RpcGetSwarmRequest):
            self.node_pool.send_message(remote, rpc.RpcGetSwarmResponse(self.id, remote.id, list(
                map(lambda x: x.remote, self._swarm))))
        elif isinstance(message, rpc.RpcGetContentRequest):
            if self.has_content:
                self.file.seek(0, 0)
                data = self.file.read()
                self.node_pool.send_message(remote, rpc.RpcGetContentResponse(self.id, remote.id, data))
            else:
                self.node_pool.send_message(remote, rpc.RpcGetContentResponse(self.id, remote.id, b""))

    async def send_request(self, remote: remote_node.RemoteNode, request: rpc.RpcMessage,
                           timeout: float) -> Optional[rpc.RpcMessage]:
        """
        Sends request and waits timeout seconds for response from remote node. It is guaranteed that response will
        have correct message type.
        :param remote: remote callee node.
        :param request: rpc request message.
        :param timeout: response waiting timeout.
        :return: rpc response message, if the call was successful. None otherwise.
        """
        assert request.to_id == remote.id
        assert request.from_id == self.id

        now = datetime.datetime.now()
        timeout_point = now + datetime.timedelta(seconds=timeout)
        f = asyncio.get_event_loop().create_future()
        # wait for a pending request to complete it there are any requests to specified ndoe.
        if remote in self._pending_requests:
            try:
                await asyncio.wait_for(self._pending_requests[remote].future, timeout)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                return None
        self._pending_requests[remote] = PendingRequest(request.command, f)
        self.node_pool.send_message(remote, request)
        try:
            val = await asyncio.wait_for(f, (timeout_point - datetime.datetime.now()).total_seconds())
        except (asyncio.TimeoutError, asyncio.CancelledError):
            val = None
        finally:
            del self._pending_requests[remote]
        return val

    async def stabilize_run(self):
        """
        Keeps node's routing information up to date, retrieves node value if required and updates swarm members list.
        Periodically runs stabilization rounds to remove unresponsive remote nodes from routing tables and find better
        remote nodes.
        """
        while True:
            # stabilizes finger table, successor and predecessor nodes
            for i in range(_finger_table_size):
                ideal_id = self.id.advance(2 ** (swarm_id.SwarmId.bit_size - _finger_table_size + i))
                self.finger_table[i] = await self._stabilize_to_id_from_below(self.finger_table[i], ideal_id)
            self.predecessor = await self._stabilize_to_id_from_below(self.predecessor, self.id.advance(-1))
            await self._stabilize_successor()

            # search for a swarm if it is not found yet
            if len(self._swarm) == 0:
                swarm_node = await self._network_get_pred_or_eq(self.id)
                if swarm_node is not None and swarm_node.id == self.id:
                    self._swarm.append(AliveRemoteNode(swarm_node, self.node_pool.timings.live_interval))
            await self._update_swarm()

            # retrieve node value from the swarm if required
            if not self.has_content:
                for node in self._swarm:
                    resp: Optional[rpc.RpcGetContentResponse] = \
                        await self.send_request(node.remote, rpc.RpcGetContentRequest(self.id, node.remote.id),
                                                self.node_pool.timings.get_data_timeout)
                    if resp is not None and len(resp.data) > 0:
                        self.file.write(resp.data)
                        self.has_content = True
                        digest = hashlib.sha3_512(resp.data).digest()
                        if digest != self.id.id:
                            print(f"wrong content hash for {self.id.hex()}!!!")
                        else:
                            print(f"got valid content for {self.id.hex()}")
                        break

            await asyncio.sleep(self.node_pool.timings.stabilize_interval)

    async def _update_swarm(self):
        """
        Updates swarm members list. Retrieves members list from all nodes in swarm and merges this lists in a new one.
        """
        new_swarm = set()
        for node in self._swarm:
            resp: Optional[rpc.RpcGetSwarmResponse] = \
                await self.send_request(node.remote, rpc.RpcGetSwarmRequest(self.id, node.remote.id),
                                        self.node_pool.timings.command_timeout)
            if resp is None:
                continue
            new_swarm.add(node.remote.address)
            for n in resp.swarm:
                new_swarm.add(n.address)
        self._swarm = await self._filter_swarm(new_swarm)

    async def _filter_swarm(self, swarm: set) -> list[AliveRemoteNode]:
        """
        Simultaneously pings all nodes in the list and waits for responses.
        :param swarm: nodes list to ping.
        :return: list of all nodes that responded to ping in time.
        """
        d = [self.send_request(remote_node.RemoteNode(self.id, addr), rpc.RpcPingRequest(self.id, self.id),
                               self.node_pool.timings.command_timeout) for addr in swarm]
        arr = []
        for a, n in zip(d, swarm):
            resp = await a
            if resp is None:
                continue
            arr.append(AliveRemoteNode(remote_node.RemoteNode(self.id, n), self.node_pool.timings.live_interval))
        return arr

    async def _stabilize_to_id_from_below(self, node: Optional[AliveRemoteNode], ideal_id: swarm_id.SwarmId) -> \
            Optional[AliveRemoteNode]:
        """
        Checks if node is still alive and tries to get a node in range (node.id, ideal_id].
        :param node: remote node to stabilize.
        :param ideal_id: upper bound for node id.
        :return: alive node that precedes specified ideal_id or has exactly ideal_id, or None if no remote nodes found.
        """
        if not await self._check_alive(node):
            n = await self._network_get_pred_or_eq(ideal_id)
            if n is not None:
                return AliveRemoteNode(n, self.node_pool.timings.live_interval)
            else:
                return None
        else:
            successor = await self._remote_get_node_call(node.remote, ideal_id)
            if successor is not None and successor.id.in_range(node.remote.id, ideal_id.advance(1)):
                return AliveRemoteNode(successor, self.node_pool.timings.live_interval)
            else:
                return node

    async def _stabilize_successor(self):
        """
        Stabilizes successor in a chord network. Tries to find node in range (self.id, self.successor.id)
        :return: the closest alive successor or None if no remote nodes found.
        """
        if not await self._check_alive(self.successor):
            self.successor = None
            first_finger = next((node for node in self.finger_table if node is not None), None)
            if first_finger is None:
                return
            successor = first_finger.remote
        else:
            successor = self.successor.remote
        while True:
            n = await self._remote_get_node_call(successor, successor.id.advance(-1))
            if n is not None and n.id.in_range(self.id, successor.id):
                successor = n
            else:
                self.successor = AliveRemoteNode(successor, self.node_pool.timings.live_interval)
                break

    async def _network_get_pred_or_eq(self, query_id: swarm_id.SwarmId) -> Optional[remote_node.RemoteNode]:
        """
        Tries to find node with id the same as specified or below specified in whole the network.
        :param query_id: upper search bound.
        :return: found node or None, if no remote nodes found.
        """
        start = self.node_pool.pool_get_pred_or_eq_node(query_id)
        start_is_bootstrap = False
        if start is None:
            bootstraps: list[remote_node.RemoteNode] = self.node_pool.get_bootstraps()
            if len(bootstraps) == 0:
                return None
            start = random.choice(bootstraps)
            start_is_bootstrap = True
        while True:
            next_node = await self._remote_get_node_call(start, query_id)
            if next_node is None:
                if start_is_bootstrap or start.id == self.id:
                    return None
                else:
                    return start
            else:
                if next_node.id == query_id:
                    return next_node
                if start_is_bootstrap or next_node.id.in_range(start.id, query_id):
                    start = next_node
                else:
                    if start_is_bootstrap or start.id == self.id:
                        return None
                    else:
                        return start
            start_is_bootstrap = False

    def local_get_pred_or_eq(self, query_id: swarm_id.SwarmId) -> Optional[remote_node.RemoteNode]:
        """
        Looks up for a remote node in local routing table.
        :param query_id: upper search bound.
        :return: found node or None, if no remote nodes found.
        """
        for node in self.predecessor, *self.finger_table[::-1], self.successor:
            if node is None:
                continue
            if query_id.in_range(node.remote.id.advance(-1), self.id):
                return node.remote
        return None

    async def _remote_get_node_call(self, remote: remote_node.RemoteNode, query_id: swarm_id.SwarmId) -> \
            Optional[remote_node.RemoteNode]:
        """
        Helper function that calls GetNode rpc call on remote node and processes response.
        :param remote: GetNode rpc call callee.
        :param query_id: GetNode query argument.
        :return: found node or None, if no specified nodes found on remote node.
        """
        r = remote_node.RemoteNode(swarm_id.zero_id, remote.address)
        resp: Optional[rpc.RpcGetNodeResponse] = \
            await self.send_request(r, rpc.RpcGetNodeRequest(self.id, swarm_id.zero_id, query_id),
                                    self.node_pool.timings.command_timeout)
        if resp is None or resp.remote_node.id == swarm_id.zero_id:
            return None
        return resp.remote_node

    async def _check_alive(self, remote: Optional[AliveRemoteNode]) -> bool:
        """
        Checks if remote node is still alive and haven't reached timeouts.
        :param remote: remote node to check for liveness.
        :return: True, if node is still alive, False otherwise.
        """
        if remote is None:
            return False
        now = datetime.datetime.now()
        if now >= remote.timeout:
            if remote.sent_ping:
                return False
            else:
                remote.sent_ping = True
                remote.timeout = now + datetime.timedelta(seconds=self.node_pool.timings.command_timeout)
                resp = await self.send_request(remote.remote, rpc.RpcPingRequest(self.id, remote.remote.id),
                                               self.node_pool.timings.command_timeout)
                if resp is None or not isinstance(resp, rpc.RpcPingResponse):
                    return False
        return True

    def _try_stabilize_with_remote(self, remote: AliveRemoteNode):
        """
        Tries to stabilize routing table with a remote node. Remote node must be alive.
        :param remote: remote node to use in stabilization.
        """
        remote_id = remote.remote.id
        if ((self.predecessor is None and remote_id != self.id) or
                (self.predecessor is not None and remote_id.in_range(self.predecessor.remote.id, self.id))):
            self.predecessor = remote
        if ((self.successor is None and remote_id != self.id) or
                (self.successor is not None and remote_id.in_range(self.id, self.successor.remote.id))):
            self.successor = remote
        for i in range(_finger_table_size):
            ideal_id = self.id.advance(2 ** (swarm_id.SwarmId.bit_size - _finger_table_size + i))
            finger = self.finger_table[i]
            if ((finger is not None and remote_id.in_range(finger.remote.id, ideal_id)) or
                    (finger is None and remote_id.in_range(self.id, ideal_id))):
                self.finger_table[i] = remote
        for n in self._swarm:
            if n.remote.address == remote.remote.address:
                break
        else:
            if remote_id == self.id:
                self._swarm.append(remote)

    def get_swarm(self) -> list:
        """
        :return: addresses of all nodes in swarm.
        """
        return list(map(lambda x: x.remote.address, self._swarm))
