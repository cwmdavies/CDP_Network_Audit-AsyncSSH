import asyncssh
import asyncio

JUMP_HOST = '192.168.1.1'
HOSTS = ["192.168.1.2", "192.168.1.3", "192.168.1.4"]

credentials = {
    "username": "",
    "password": "",
    "known_hosts": None,
}


async def run_client(host, command: str) -> asyncssh.SSHCompletedProcess:
    async with asyncssh.connect(JUMP_HOST, **credentials):
        async with asyncssh.connect(host, **credentials) as conn:
            return await conn.run(command)


async def run_multiple_clients(command: str) -> None:
    tasks = (run_client(host, command) for host in HOSTS)
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for i, result in enumerate(results, 1):
        if isinstance(result, Exception):
            print('Task %d failed: %s' % (i, str(result)))
        elif result.exit_status != 0:
            print('Task %d exited with status %s:' % (i, result.exit_status))
            print(result.stderr, end='')
        else:
            print('Task %d succeeded:' % i)
            print(result.stdout, end='')

        print(75*'-')

asyncio.get_event_loop().run_until_complete(run_multiple_clients("show version"))
