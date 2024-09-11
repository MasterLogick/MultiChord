# Multi chord

PoC of a distributed hash table based on chord that do not store member lists.

Every multi chord app instance consists of a udp server, node pool, controller and a set of hosted virtual nodes. Udp
server manages all network connection and rpc messages serialization/deserialization. Node pool keeps the list of hosted
virtual nodes, handles zero node requests and routes messages between udp server and virtual nodes. Controller manages
creation of new virtual nodes. Virtual nodes are cheap virtual instances of nodes in a chord. Every node stores only one
key-value pair and can be described by application network address and its key. Virtual nodes with the same key(id) form
one swarm.

Node pool description:

```
NodePool (
   virtual_nodes: list of VirtualNode
)
```

Virtual node description:

```
VirtualNode (
   id: Id
   node_value: data
   predecessor: RemoteNode
   successor: RemoteNode
   finger_table: finger table of RemoteNode
   swarm: list of RemoteNode
)
Idealy finger table consists of nodes with ids: Node.id + 2^0, Node.id + 2^1, Node.id + 2^2, Node.id + 2^3, ...
But in reality this ids are upper bounds for fingers.
```

Remote node description:

```
RemoteNode (
   id: Id
   address: string
)
```

## RPC Protocol

Multi chord is based on udp so there is no need to keep expensive sessions and perform redundant handshakes. Each rpc
call is performed between two virtual nodes. Caller sends request message to the callee’s server socket, callee performs
a call and sends back to caller response message. Each message has a header that consists of source node id, destination
node id and type of message.

Rpc message description:

```
RpcMessage (
   header: RpcMessageHeader
   extra_fields: ...
)
```

Rpc message header description:

```
RpcMessageHeader (
   from_id: Id
   to_id: Id
   message_type: byte
)
```

### RPC Messages(See the same list in [rpc.py](./multi_chord/rpc.py)):

Multi chord rpc consists of 8 messages(4 rpc calls: request + response messages).

Parenthesis in description contain message fields. Header fields are omitted in message fields.

0. `PingRequest()` requests remote node to send back `PingResponse()`. Can be used to check callee liveness or notify
   callee about existence of the caller.
1. `PingRespoinse()` - response to `PingRequest()`.
2. `GetNodeRequest(query_id: Id)` - requests remote node to return id and address of remote node that has id lower or
   equal
   to `query_id`. Same as `find_successor` call in Chord(However, here we essentially search for predecessor).
3. `GetNodeResponse(node: RemoteNode)` - response to `GetNodeRequest(query_id)`.
4. `GetSwarmRequest()` - requests callee to return a list of all known nodes in callee swarm.
5. `GetSwarmResponse(swarm: list of RemoteNode)` - response to `GetSwarmResponse()`.
6. `GetContentRequest()` - requests callee to provide its node value.
7. `GetContentResponse(node_value: data)` - response to `GetContentRequest()`. Empty data means that callee still does
   not have node value.

## Procedures

This section describes all possible behaviours and actions that may occur in Multi Chord.

### Add a new virtual node

We can create new virtual node from specific id or a file. If we create node from id, node will download node value as
soon as it will find other nodes in swarm. If we create node from file, it will provide this file for other nodes in the
network.

```
node_id = derive from file content or get dirrectly from user
node = VirtualNode (
   id = node_id
   node_value = file data if available or None
   predecessor = None
   successor = None
   finger_table = list of None
   swarm = list of None
)
node_pool.add(node)
```

### Stabilize virtual node

As soon as node is created it starts to periodically stabilize itself. During stabilization process, node finds better
remote nodes for finger table and close successor and predecessor. Also, it renews swarm members list and downloads node
value if still does not have local copy.

```
# stabilize predecessor and finger table
Node.predecessor = find_node_below_or_equal(Node.id - 1)
for index, finger_offset in Node.finger_table:
   Node.finger_table[index] = find_node_below_or_equal(Node.id + finger_offset)

# stabilize successor
successor_candidate = Node.finger_table[0] # closest from above to Node finger
while successor_candidate is not Node:
   successor_candidate = find_node_below_or_equal(successor_candidate.id - 1)
Node.successor = successor_candidate

# find swarm
if Node.swarm is empty:
   swarm_member = find_node_below_or_equal(Node.id)
   if swarm_member.id == Node.id:
      Node.swarm.append(swarm_member)

# update swarm members list
if Node.swarm is not empty:
   candidate_list = Node.swarm + unique(flat_map(n.get_swarm() for n in Node.swarm))
   Node.swarm = []
   for n in candidate_list:
      if n.ping() is successfull:
         Node.swarm.append(n)

# get node value
if Node.swarm is not empty and Node.node_value is None:
   for n in Node.swarm:
      Node.node_value = n.get_content()
      if Node.node_value is not None and hash(Node.node_value) == Node.id:
         # got content
         break
```

### `find_node_below_or_equal(query_id: Id)` function

This function finds in the whole Chord node with the closest or equal to `query_id` id.

```
find_node_below_or_equal(query_id: Id):
   # reuse the fact that we store finger table in all nodes, so we may have closer starting point
   candidate = [virt_node.get_node(query_id) for virt_node in node_pool].closest_to(query_id)
   while True:
      next_candidate = candidate.get_node(query_id)
      if next_candidate.id in (candidate.id, query_id]:
         candidate = next_candidate
      else:
         return candidate
```

### `Node.get_node(query_id: Id)` function

This function implements RPC `GetNode` call. It returns the closest node with id below or equal to `query_id` from
finger table, predecessor and successor nodes.

```
Node.get_node(query_id: Id):
   if query_id in [Node.predecessor.id, Node.id):
      return Node.predecessor
   for finger in Node.finger_table.reverse():
      if query_id in [finger.id, Node.id):
         return finger
   if query_id in [Node.predecessor.id, Node.finger_table[0]):
      return Node.predecessor
   else:
      return Node
```

## Runtime requirements

Each network must have at least one bootstrap node with static address that hosts at least one virtual node.
One app instance is one node pool. You can create as many different virtual nodes in one pool as you want.

## Examples

Simple usage:

```shell
python3 main.py 127.0.0.1 1234 # spawns node pool that is bound to 127.0.0.1:1234
python3 main.py --scenario-host-random 127.0.0.1 1234 # hosts one virtual node with random content in the pool
python3 main.py --bootstrap 127.0.0.1:1234 0.0.0.0 0 # spawns node pool on random free port with 127.0.0.1:1234 as a bootstrap. You can specify several --bootstrap arguments 
```

Simple network of 5 node pools (run every command in new console):

```shell
python3 main.py --scenario-host-random 127.0.0.1 1234 # working bootstrap node
python3 main.py --bootstrap 127.0.0.1:1234 0.0.0.0 0 # common node. spawn them as many as you want.
python3 main.py --bootstrap 127.0.0.1:1234 0.0.0.0 0
python3 main.py --bootstrap 127.0.0.1:1234 0.0.0.0 0
python3 main.py --bootstrap 127.0.0.1:1234 0.0.0.0 0
```

## CLI

+ `ls` - list of all hosted virtual nodes.
+ `jr id file` - joins remote swarm with `id` and downloads node value to `file`. checksum is verified after download.
+ `hl file` - calculates file id and creates new node and swarm with this id for `file`.
+ `help` - print CLI help.