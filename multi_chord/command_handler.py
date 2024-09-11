import asyncio
import hashlib
import sys
from typing import BinaryIO

from . import swarm_id
from . import hosted_virtual_node
from . import node_pool


class CommandHandler:
    """
    CommandHandler is a CLI that manages a node pool. It can create new hosted virtual nodes and retrieve their state.
    """
    help_message = """Available commands:
hl, host, host-local file_path - host local file from file_path
jr, join-remote file_id file_path - join remote swarm with file_id and download file to file_path
lvn, ls, list-virtual-nodes - list hosted virtual nodes
h, help - print this help message
e, q, exit - exit program"""

    def __init__(self, pool: node_pool.NodePool):
        self._node_pool = pool

    async def run(self):
        """
        Reads commands from stdin and executes them.
        """
        reader = await _get_steam_reader(sys.stdin)
        print("Enter commands:")
        while True:
            line = await reader.readline()
            line = line.decode("utf-8").strip()
            if line == "exit" or line == "e" or line == "q":
                break
            self.handle(line)

    def handle(self, line: str):
        """
        Tries to handle user input as a command.
        """
        command = line.split(" ")
        name, args = command[0], command[1:]
        if (name == "host-local" or name == "hl" or name == "host") and len(args) == 1:
            self.host_local_file(args[0])
        elif (name == "join-remote" or name == "jr") and len(args) == 2:
            self.join_remote(args[0], args[1])
        elif (name == "list-virtual-nodes" or name == "lvn" or name == "ls") and len(args) == 0:
            self.list_virtual_nodes()
        elif (name == "help" or name == "h") and len(args) == 0:
            print(CommandHandler.help_message)
        else:
            print("Unknown command. Type \"help\" to get a list of available commands.")

    def host_local_file(self, file: str | BinaryIO):
        """
        Creates a new hosted virtual nodes with available node value.
        :param file: node value
        """
        if isinstance(file, str):
            file = open(file, "rb")
        file.seek(0, 0)
        data = file.read()
        id_bytes = hashlib.sha3_512(data).digest()
        file_id = swarm_id.SwarmId(id_bytes)
        node = hosted_virtual_node.HostedVirtualNode(file_id)
        node.set_content_path(file, True)
        self._node_pool.host_virtual_node(node)
        print(f"added virtual node for {file.name}: {file_id.hex()}")

    def join_remote(self, id_bytes: str, file: str | BinaryIO):
        """
        Creates a new hosted virtual node with specified id and prepares file for node value.
        :param id_bytes: existing id of the swarm.
        :param file: place to store node value later.
        """
        id = swarm_id.SwarmId(id_bytes)
        node = hosted_virtual_node.HostedVirtualNode(id)
        if isinstance(file, str):
            file = open(file, "wb+")
        node.set_content_path(file, False)
        self._node_pool.host_virtual_node(node)
        print(f"joined swarm for {file.name}: {id.hex()}")

    def list_virtual_nodes(self):
        """
        Prints info about all hosted virtual nodes to stdout.
        """
        hosted_nodes = self._node_pool.get_hosted_virtual_nodes()
        for node in hosted_nodes:
            print(node.id.hex() + " file: " + node.file.name + ", has content: " + str(node.has_content))
            print(f"predecessor: {node.predecessor}, successor: {node.successor}")
            for i in range(len(node.finger_table)):
                print(f"{i}: {node.finger_table[i]}")
            for s in node.get_swarm():
                print("\t" + str(s))


async def _get_steam_reader(pipe) -> asyncio.StreamReader:
    """
    Helper function that wraps sys pipe in asyncio wrapper
    :param pipe: sys pipe object
    :return: asyncio wrapper
    """
    loop = asyncio.get_event_loop()
    reader = asyncio.StreamReader(loop=loop)
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, pipe)
    return reader
