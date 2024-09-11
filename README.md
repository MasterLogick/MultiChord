# Multi chord

PoC of a distributed hash table based on chord that do not store member lists.

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