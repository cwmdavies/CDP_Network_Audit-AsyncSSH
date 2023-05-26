import asyncssh
import asyncio

JUMP_HOST = ""
HOSTS = [""]

encryption_algs_list = ["aes128-cbc", "3des-cbc", "aes192-cbc", "aes256-cbc", "aes256-ctr"]
kex_algs_list = ["diffie-hellman-group-exchange-sha1", "diffie-hellman-group14-sha1", "diffie-hellman-group1-sha1"]


credentials = {
    "username": "",
    "password": "_",
    "known_hosts": None,
    "encryption_algs": encryption_algs_list,
    "kex_algs": kex_algs_list,
}


async def run_client(host, command: str) -> asyncssh.SSHCompletedProcess:
    async with asyncssh.connect(JUMP_HOST, **credentials) as tunnel:
        async with asyncssh.connect(host, tunnel=tunnel, **credentials) as conn:
            return await conn.run(command)


async def run_multiple_clients(command: str) -> None:
    tasks = (run_client(host, command) for host in HOSTS)
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for i, result in enumerate(results, 1):
        if isinstance(result, Exception):
            print(f"Task {i} failed: {str(result)}")
        elif result.exit_status != 0:
            print(f"Task {i} exited with status {result.exit_status}:")
            print(result.stderr, end="")
        else:
            print(f"Task {i} succeeded:")
            print(result.stdout, end="")

        print(75*'-')

asyncio.get_event_loop().run_until_complete(run_multiple_clients("show version"))
