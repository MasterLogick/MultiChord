from enum import IntEnum

from . import remote_node
from . import swarm_id


class RpcMessageType(IntEnum):
    UNKNOWN = -1
    PING_REQUEST = 0
    PING_RESPONSE = 1
    GET_NODE_REQUEST = 2
    GET_NODE_RESPONSE = 3
    GET_SWARM_REQUEST = 4
    GET_SWARM_RESPONSE = 5
    GET_CONTENT_REQUEST = 6
    GET_CONTENT_RESPONSE = 7
    LAST_COMMAND = GET_CONTENT_RESPONSE

    @classmethod
    def _missing_(cls, value):
        return RpcMessageType.UNKNOWN


class RpcMessage:
    def __init__(self, from_id: swarm_id.SwarmId, to_id: swarm_id.SwarmId, command: RpcMessageType):
        self.from_id = from_id
        self.to_id = to_id
        self.command = command

    def __eq__(self, other):
        return self.from_id == other.from_id and self.to_id == other.to_id and self.command == other.command

    def to_bytes(self) -> bytes:
        return self.from_id.id + self.to_id.id + self.command.value.to_bytes(1, byteorder="little", signed=False)


class RpcPingRequest(RpcMessage):
    def __init__(self, from_id: swarm_id.SwarmId, to_id: swarm_id.SwarmId):
        super().__init__(from_id, to_id, RpcMessageType.PING_REQUEST)

    def __str__(self):
        return f"RpcPingRequest(from_id={self.from_id}, to_id={self.to_id})"


class RpcPingResponse(RpcMessage):
    def __init__(self, from_id: swarm_id.SwarmId, to_id: swarm_id.SwarmId):
        super().__init__(from_id, to_id, RpcMessageType.PING_RESPONSE)

    def __str__(self):
        return f"RpcPingResponse(from_id={self.from_id}, to_id={self.to_id})"


class RpcGetNodeRequest(RpcMessage):
    def __init__(self, from_id: swarm_id.SwarmId, to_id: swarm_id.SwarmId, query_id: swarm_id.SwarmId):
        super().__init__(from_id, to_id, RpcMessageType.GET_NODE_REQUEST)
        self.query_id = query_id

    def to_bytes(self) -> bytes:
        return super().to_bytes() + self.query_id.id

    def __eq__(self, other):
        return super().__eq__(other) and self.query_id == other.query_id

    def __str__(self):
        return f"RpcGetNodeRequest(from_id={self.from_id}, to_id={self.to_id}, query_id={self.query_id})"


class RpcGetNodeResponse(RpcMessage):
    def __init__(self, from_id: swarm_id.SwarmId, to_id: swarm_id.SwarmId,
                 remote: remote_node.RemoteNode):
        super().__init__(from_id, to_id, RpcMessageType.GET_NODE_RESPONSE)
        self.remote_node = remote

    def to_bytes(self) -> bytes:
        return super().to_bytes() + _serialize_remote_node(self.remote_node)

    def __eq__(self, other):
        return super().__eq__(other) and self.remote_node == other.remote_node

    def __str__(self):
        return f"RpcGetNodeResponse(from_id={self.from_id}, to_id={self.to_id}, remote_node={self.remote_node})"


class RpcGetSwarmRequest(RpcMessage):
    def __init__(self, from_id: swarm_id.SwarmId, to_id: swarm_id.SwarmId):
        super().__init__(from_id, to_id, RpcMessageType.GET_SWARM_REQUEST)

    def __str__(self):
        return f"RpcGetSwarmRequest(from_id={self.from_id}, to_id={self.to_id})"


class RpcGetSwarmResponse(RpcMessage):
    def __init__(self, from_id: swarm_id.SwarmId, to_id: swarm_id.SwarmId,
                 swarm: list[remote_node.RemoteNode]):
        super().__init__(from_id, to_id, RpcMessageType.GET_SWARM_RESPONSE)
        self.swarm = swarm

    def to_bytes(self) -> bytes:
        serialized = super().to_bytes() + len(self.swarm).to_bytes(4, byteorder="little", signed=False)
        for node in self.swarm:
            serialized += _serialize_remote_node(node)
        return serialized

    def __eq__(self, other):
        if len(self.swarm) != len(other.swarm):
            return False
        for a, b in zip(self.swarm, other.swarm):
            if a != b:
                return False
        return super().__eq__(other)

    def __str__(self):
        return f"RpcGetSwarmResponse(from_id={self.from_id}, to_id={self.to_id}, swarm={self.swarm})"


class RpcGetContentRequest(RpcMessage):
    def __init__(self, from_id: swarm_id.SwarmId, to_id: swarm_id.SwarmId):
        super().__init__(from_id, to_id, RpcMessageType.GET_CONTENT_REQUEST)

    def __str__(self):
        return f"RpcGetContentRequest(from_id={self.from_id}, to_id={self.to_id})"


class RpcGetContentResponse(RpcMessage):
    def __init__(self, from_id: swarm_id.SwarmId, to_id: swarm_id.SwarmId, data: bytes):
        super().__init__(from_id, to_id, RpcMessageType.GET_CONTENT_RESPONSE)
        self.data = data

    def to_bytes(self) -> bytes:
        return super().to_bytes() + len(self.data).to_bytes(4, byteorder="little", signed=False) + self.data

    def __eq__(self, other):
        return super().__eq__(other) and self.data == other.data

    def __str__(self):
        return f"RpcGetContentResponse(from_id={self.from_id}, to_id={self.to_id}, len(data)={len(self.data)})"


def _parse_remote_node(msg: bytes) -> tuple[remote_node.RemoteNode | None, bytes]:
    if len(msg) < swarm_id.SwarmId.bytes_size + 4:
        return None, msg
    addr_len = int.from_bytes(msg[swarm_id.SwarmId.bytes_size: swarm_id.SwarmId.bytes_size + 4], byteorder="little",
                              signed=False)
    if len(msg) < swarm_id.SwarmId.bytes_size + 4 + addr_len:
        return None, msg
    node_id = swarm_id.SwarmId(msg[:swarm_id.SwarmId.bytes_size])
    addr = msg[swarm_id.SwarmId.bytes_size + 4:swarm_id.SwarmId.bytes_size + 4 + addr_len].decode("utf-8")
    return remote_node.RemoteNode(node_id, addr), msg[swarm_id.SwarmId.bytes_size + 4 + addr_len:]


def _serialize_remote_node(node: remote_node.RemoteNode) -> bytes:
    serialized_address = node.address.encode("utf-8")
    return (node.id.id + len(serialized_address).to_bytes(4, byteorder="little", signed=False) +
            serialized_address)


def parse_rpc_message(msg: bytes, address) -> tuple[RpcMessage | None, bytes]:
    if len(msg) < swarm_id.SwarmId.bytes_size + swarm_id.SwarmId.bytes_size + 1:
        return None, msg
    from_id = swarm_id.SwarmId(msg[:swarm_id.SwarmId.bytes_size])
    to_id = swarm_id.SwarmId(msg[swarm_id.SwarmId.bytes_size: swarm_id.SwarmId.bytes_size * 2])
    command = RpcMessageType(msg[swarm_id.SwarmId.bytes_size * 2])
    header_len = swarm_id.SwarmId.bytes_size * 2 + 1
    if command == RpcMessageType.PING_REQUEST:
        return RpcPingRequest(from_id, to_id), msg[header_len:]
    elif command == RpcMessageType.PING_RESPONSE:
        return RpcPingResponse(from_id, to_id), msg[header_len:]
    elif command == RpcMessageType.GET_NODE_REQUEST:
        if len(msg) < header_len + swarm_id.SwarmId.bytes_size:
            return None, msg
        query_id = swarm_id.SwarmId(msg[header_len:header_len + swarm_id.SwarmId.bytes_size])
        return RpcGetNodeRequest(from_id, to_id, query_id), msg[header_len + swarm_id.SwarmId.bytes_size:]
    elif command == RpcMessageType.GET_NODE_RESPONSE:
        node, msg_remainder = _parse_remote_node(msg[header_len:])
        if node is None:
            return None, msg
        if node.address == "":
            node.address = address
        return RpcGetNodeResponse(from_id, to_id, node), msg_remainder
    elif command == RpcMessageType.GET_SWARM_REQUEST:
        return RpcGetSwarmRequest(from_id, to_id), msg[header_len:]
    elif command == RpcMessageType.GET_SWARM_RESPONSE:
        if len(msg) < header_len + 4:
            return None, msg
        count = int.from_bytes(msg[header_len:header_len + 4], byteorder="little", signed=False)
        swarm: list[remote_node.RemoteNode] = []
        msg_remainder = msg[header_len + 4:]
        for i in range(count):
            node, msg_remainder = _parse_remote_node(msg_remainder)
            if node is None:
                return None, msg
            if node.address == "":
                node.address = address
            swarm.append(node)
        return RpcGetSwarmResponse(from_id, to_id, swarm), msg_remainder
    elif command == RpcMessageType.GET_CONTENT_REQUEST:
        return RpcGetContentRequest(from_id, to_id), msg[header_len:]
    elif command == RpcMessageType.GET_CONTENT_RESPONSE:
        if len(msg) < header_len + 4:
            return None, msg
        length = int.from_bytes(msg[header_len:header_len + 4], byteorder="little", signed=False)
        if len(msg) < header_len + 4 + length:
            return None, msg
        return (RpcGetContentResponse(from_id, to_id, msg[header_len + 4:header_len + 4 + length]),
                msg[header_len + 4 + length:])
    else:
        return None, b""


_from_id = swarm_id.SwarmId(
    "384337abeaa3a24884ba6ce6df7e7c533569091f89f102a940ac19242e4947ac41d80c5e2fb4babc825113d2c06c5e44a39c9da3ca4d3fb8cf5969c2def21c7f")
_to_id = swarm_id.SwarmId(
    "cf83e1357eefb8bdf1542850d66d8007d620e4050b5715dc83f4a921d36ce9ce47d0d13c5d85f2b0ff8318d2877eec2f63b931bd47417a81a538327af927da3e")
_swarm_id = swarm_id.SwarmId(
    "8fb29448faee18b656030e8f5a8b9e9a695900f36a3b7d7ebb0d9d51e06c8569d81a55e39b481cf50546d697e7bde1715aa6badede8ddc801c739777be77f166")
_address = "123"
_data = b"123"
_test_rpc_ping_request = RpcPingRequest(_from_id, _to_id)
_test_rpc_ping_response = RpcPingResponse(_from_id, _to_id)
_test_rpc_get_node_request = RpcGetNodeRequest(_from_id, _to_id, _swarm_id)
_test_rpc_get_node_response = RpcGetNodeResponse(_from_id, _to_id, remote_node.RemoteNode(_swarm_id, _address))
_test_rpc_get_swarm_request = RpcGetSwarmRequest(_from_id, _to_id)
_test_rpc_get_swarm_response = RpcGetSwarmResponse(_from_id, _to_id, [remote_node.RemoteNode(_swarm_id, _address)])
_test_rpc_get_content_request = RpcGetContentRequest(_from_id, _to_id)
_test_rpc_get_content_response = RpcGetContentResponse(_from_id, _to_id, _data)
_tests = [_test_rpc_ping_request, _test_rpc_ping_response, _test_rpc_get_node_request, _test_rpc_get_node_response,
          _test_rpc_get_swarm_request, _test_rpc_get_swarm_response, _test_rpc_get_content_request,
          _test_rpc_get_content_response]

for _t in _tests:
    _a, _b = parse_rpc_message(_t.to_bytes(), "")
    assert len(_b) == 0
    assert _a == _t
