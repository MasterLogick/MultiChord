from . import swarm_id


class RemoteNode:
    """
    RemoteNode specifies a remote node by swarm id and node network address.
    """

    def __init__(self, id: swarm_id.SwarmId, address: str):
        self.id = id
        self.address = address

    def __eq__(self, other):
        return self.id == other.id and self.address == other.address

    def __hash__(self):
        return hash((self.id, self.address))

    def __str__(self):
        return f"RemoteNode(id={self.id}, address={self.address})"


zero_node = RemoteNode(swarm_id.zero_id, "")
