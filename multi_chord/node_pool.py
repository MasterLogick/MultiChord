import asyncio
import traceback
from typing import Optional

from . import hosted_virtual_node
from . import remote_node
from . import swarm_id
from . import rpc
from . import interface
from . import timings


class NodePool:
    """
    Node pool is a facility that runs virtual nodes. It keeps track of the nodes, routes messages between them and
    the network, helps with node discovery and is responsible for zero swarm requests handling. All virtual nodes in one
    pool have the same network address but belong to different swarms.

    Zero node is service ephemeral node that is present in all node pools. It does not hold any value or stabilizes
    itself, but has special meaning in some rpc calls. Zero node doesn't make rpc calls by itself. It only responds to
    requests from common nodes.
    """

    def __init__(self, iface: interface.Interface, t: timings.Timings):
        self._iface = iface
        self.timings = t
        self._hosted_virtual_nodes: dict[
            swarm_id.SwarmId, tuple[hosted_virtual_node.HostedVirtualNode, asyncio.Task]] = {}
        self._bootstraps: list[remote_node.RemoteNode] = []

    def add_remote_bootstrap(self, address: str):
        """
        Adds new bootstrap address record to local bootstrap list
        :param address: address of a bootstrap node
        """
        self._bootstraps.append(remote_node.RemoteNode(swarm_id.zero_id, address))

    def host_virtual_node(self, node: hosted_virtual_node.HostedVirtualNode):
        """
        Starts hosting new virtual node. Adds node to the hosted list and creates stabilization task for the node.
        :param node: virtual node to host
        """
        if node.id in self._hosted_virtual_nodes:
            raise Exception(f"specified id {node.id.hex()} is already occupied")
        assert node.node_pool is None
        node.node_pool = self

        async def coroutine_unhandled_exception_guard():
            try:
                await node.stabilize_run()
            except:
                print(traceback.format_exc())

        task = asyncio.get_event_loop().create_task(coroutine_unhandled_exception_guard())
        self._hosted_virtual_nodes[node.id] = (node, task)

    def get_hosted_virtual_nodes(self) -> list[hosted_virtual_node.HostedVirtualNode]:
        """
        :return: A list of all hosted virtual nodes
        """
        d = []
        for k in self._hosted_virtual_nodes:
            d.append(self._hosted_virtual_nodes[k][0])
        return d

    def get_bootstraps(self) -> list[remote_node.RemoteNode]:
        """
        :return: A list of all bootstrap nodes
        """
        return self._bootstraps

    def process_message(self, remote: remote_node.RemoteNode, message: rpc.RpcMessage):
        """
        Processes incoming message from a network interface
        :param remote: sender of the message
        :param message: sent message
        """
        dest = message.to_id
        if dest == swarm_id.zero_id:
            self._process_zero_swarm(remote, message)
        elif dest in self._hosted_virtual_nodes:
            self._hosted_virtual_nodes[dest][0].process_message(remote, message)

    def send_message(self, remote, message):
        """
        Sends message to specified remote node over the network interface.
        :param remote: message destination
        :param message: rpc message
        """
        self._iface.send_message(remote, message)

    def _process_zero_swarm(self, remote: remote_node.RemoteNode, message: rpc.RpcMessage):
        """
        Handles incoming messages to the zero node. Zero node responses only to ping requests and GetNode queries.
        Common nodes may use ping requests to check pool liveness and GetNode queries to search for the nearest known
        remote node in all virtual nodes of the pool or to check if a specific virtual node is present in the pool.
        :param remote: message sender
        :param message: rpc request message
        """
        if isinstance(message, rpc.RpcPingRequest):
            self._iface.send_message(remote, rpc.RpcPingResponse(swarm_id.zero_id, remote.id))
        elif isinstance(message, rpc.RpcGetNodeRequest):
            resp = self.pool_get_pred_or_eq_node(message.query_id)
            for hvn_id in self._hosted_virtual_nodes:
                if resp is None or hvn_id.in_range(resp.id, message.query_id.advance(1)):
                    resp = remote_node.RemoteNode(hvn_id, "")
                    break
            if resp is None:
                resp = remote_node.zero_node
            self._iface.send_message(remote, rpc.RpcGetNodeResponse(swarm_id.zero_id, remote.id, resp))

    def pool_get_pred_or_eq_node(self, query_id: swarm_id.SwarmId) -> Optional[remote_node.RemoteNode]:
        """
        :param query_id: id to search for
        :return: Nearest alive and known remote node in all hosted virtual nodes that precedes query_id or has it as id.
        """
        query_id = query_id.advance(1)
        resp = None
        for hvn_id in self._hosted_virtual_nodes:
            hvn = self._hosted_virtual_nodes[hvn_id][0]
            r = hvn.local_get_pred_or_eq(query_id)
            if r is not None and (resp is None or r.id.in_range(resp.id, query_id)):
                resp = r
        return resp
