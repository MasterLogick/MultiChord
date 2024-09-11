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
    def __init__(self, iface: interface.Interface, t: timings.Timings):
        self._iface = iface
        self.timings = t
        self._hosted_virtual_nodes: dict[
            swarm_id.SwarmId, tuple[hosted_virtual_node.HostedVirtualNode, asyncio.Task]] = {}
        self._bootstraps: list[remote_node.RemoteNode] = []

    def add_remote_bootstrap(self, address: str):
        self._bootstraps.append(remote_node.RemoteNode(swarm_id.zero_id, address))

    def host_virtual_node(self, node: hosted_virtual_node.HostedVirtualNode):
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
        d = []
        for k in self._hosted_virtual_nodes:
            d.append(self._hosted_virtual_nodes[k][0])
        return d

    def get_bootstraps(self) -> list[remote_node.RemoteNode]:
        return self._bootstraps

    def process_message(self, description: remote_node.RemoteNode, message: rpc.RpcMessage):
        dest = message.to_id
        if dest == swarm_id.zero_id:
            self._process_zero_swarm(description, message)
        elif dest in self._hosted_virtual_nodes:
            self._hosted_virtual_nodes[dest][0].process_message(description, message)

    def send_message(self, remote, message):
        self._iface.send_message(remote, message)

    def _process_zero_swarm(self, remote: remote_node.RemoteNode, message: rpc.RpcMessage):
        if isinstance(message, rpc.RpcPingRequest):
            self._iface.send_message(remote, rpc.RpcPingResponse(swarm_id.zero_id, remote.id))
        elif isinstance(message, rpc.RpcGetNodeRequest):
            resp = self.pool_get_node(message.query_id)
            for hvn_id in self._hosted_virtual_nodes:
                if resp is None or hvn_id.in_range(resp.id, message.query_id.add(1)):
                    resp = remote_node.RemoteNode(hvn_id, "")
                    break
            if resp is None:
                resp = remote_node.zero_node
            self._iface.send_message(remote, rpc.RpcGetNodeResponse(swarm_id.zero_id, remote.id, resp))

    def pool_get_node(self, query_id: swarm_id.SwarmId) -> Optional[remote_node.RemoteNode]:
        query_id = query_id.add(1)
        resp = None
        for hvn_id in self._hosted_virtual_nodes:
            hvn = self._hosted_virtual_nodes[hvn_id][0]
            r = hvn.local_get_pred_or_eq(query_id)
            if r is not None and (resp is None or r.id.in_range(resp.id, query_id)):
                resp = r
        return resp
