import re


class SwarmId:
    """
    SwarmId stores id of the swarm and provides some helper functions to manipulate with id.
    Id is a 64-bytes little endian number.
    """
    bytes_size = 64
    bit_size = 512
    id_max = 2 ** (bytes_size * 8)

    def __init__(self, id: str | bytes):
        """
        Creates a new SwarmId.
        :param id: 128-characters hex string or a 64-bytes binary string that represents id.
        """
        if isinstance(id, str):
            if not re.match("[0-9a-fA-F]{" + str(SwarmId.bytes_size * 2) + "}", id):
                raise ValueError(f"provided string is not id: {id}")
            self.id = bytes.fromhex(id)
        elif isinstance(id, bytes):
            if not len(id) == 64:
                raise ValueError(f"provided bytestring of incorrect size: {len(id)} (required {SwarmId.bytes_size})")
            self.id = id
        else:
            raise ValueError("unsupported type for id: " + str(type(id)))

    def __index__(self):
        """Transforms id to big int"""
        return int.from_bytes(self.id, byteorder="little", signed=False)

    def hex(self):
        """Returns a hex representation of the id."""
        return self.id.hex()

    def __str__(self):
        """Returns a trimmed string representation of the id."""
        return self.id[0:3].hex() + "..." + self.id[-3:].hex()

    def in_range(self, left, right) -> bool:
        """Returns true if self is in (left, right) range."""
        a = left.__index__()
        b = self.__index__()
        c = right.__index__()
        dist_ab = (b - a) % SwarmId.id_max
        dist_ac = (c - a) % SwarmId.id_max
        return dist_ab < dist_ac and a != b and b != c

    def __eq__(self, other):
        return self.id == other.id

    def __hash__(self):
        return hash(self.id)

    def advance(self, i: int):
        """Returns an advanced SwarmId instance."""
        v = (self.__index__() + i) % SwarmId.id_max
        return SwarmId(v.to_bytes(SwarmId.bytes_size, byteorder="little", signed=False))


zero_id = SwarmId(b"\x00" * SwarmId.bytes_size)
