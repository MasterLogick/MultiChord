import argparse
import asyncio
import secrets
import tempfile

from multi_chord import command_handler
from multi_chord import timings
from multi_chord import node_pool
from multi_chord import udp_server


async def main():
    parser = argparse.ArgumentParser(description="Multi Chord implementation.")
    parser.add_argument("--bootstrap", metavar="address", action="append", help="Specify bootstrap node address.")
    parser.add_argument("ip", metavar="ip", help="Ip address of server socket.")
    parser.add_argument("port", metavar="port", type=int, help="Port number of server socket.")
    parser.add_argument("--stabilize-interval", metavar="seconds", type=float,
                        help="Time between stabilization runs")
    parser.add_argument("--live-interval", metavar="seconds", type=float,
                        help="Time between keep-alive pings")
    parser.add_argument("--command-interval", metavar="seconds", type=float, help="Rpc call timeout")
    parser.add_argument("--get-data-timeout", metavar="seconds", type=float, help="Rpc get data call timeout")
    parser.add_argument("--scenario-host-random", action="store_true", help="Host random temporary file.")
    parser.add_argument("--scenario-local-file", metavar="file", help="Host specified file.")
    parser.add_argument("--scenario-join-remote", nargs=2, metavar=("id", "file"),
                        help="Join to specified swarm and save file.")

    args = parser.parse_args()

    opt_node_server_args = {}
    if args.stabilize_interval and args.stabilize_interval != 0:
        opt_node_server_args["stabilize_interval"] = args.stabilize_interval
    server = udp_server.UdpServer((args.ip, args.port))
    timings_args = {}
    if args.stabilize_interval is not None:
        timings_args["stabilize_interval"] = args.stabilize_interval
    if args.live_interval is not None:
        timings_args["live_interval"] = args.live_interval
    if args.command_interval is not None:
        timings_args["command_interval"] = args.command_interval
    if args.get_data_timeout is not None:
        timings_args["get_data_timeout"] = args.get_data_timeout
    t = timings.Timings(*timings_args)
    pool = node_pool.NodePool(server, t)

    if args.bootstrap:
        for b in args.bootstrap:
            pool.add_remote_bootstrap(b)

    await server.start(pool)
    ch = command_handler.CommandHandler(pool)

    if args.scenario_host_random:
        f = tempfile.NamedTemporaryFile("wb+")
        f.write(secrets.randbits(512).to_bytes(64, "little", signed=False))
        f.flush()
        ch.host_local_file(f)
    if args.scenario_local_file is not None:
        ch.host_local_file(args.scenario_local_file)
    if args.scenario_join_remote is not None:
        ch.join_remote(args.scenario_join_remote[0], args.scenario_join_remote[1])

    await ch.run()
    server.stop()


if __name__ == "__main__":
    task = asyncio.get_event_loop().create_task(main(), name="main")
    try:
        asyncio.get_event_loop().run_until_complete(task)
    except KeyboardInterrupt:
        task.cancel()
