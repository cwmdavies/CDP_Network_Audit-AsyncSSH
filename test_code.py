import asyncio
import asyncssh
import textfsm
import pandas as np

encryption_algs_list = ["aes128-cbc", "3des-cbc", "aes192-cbc", "aes256-cbc", "aes256-ctr"]
kex_algs_list = ["diffie-hellman-group-exchange-sha1", "diffie-hellman-group14-sha1", "diffie-hellman-group1-sha1"]

credentials = {
    "username": 'chris',
    "password": '!Lepsodizle0!',
    "known_hosts": None,
    "encryption_algs": encryption_algs_list,
    "kex_algs": kex_algs_list,
    "connect_timeout": 10,
}

collection_of_results = []


async def run_client(host, command: str) -> asyncssh.SSHCompletedProcess:
    async with asyncssh.connect(host, **credentials) as conn:
        return await conn.run(command)


async def run_multiple_clients() -> None:
    # Put your lists of hosts here
    hosts = ['192.168.1.1', '192.168.1.2', '192.168.1.3', '192.168.1.4']

    task1 = (run_client(host, 'show cdp neighbors detail') for host in hosts)

    task1_results = await asyncio.gather(*task1, return_exceptions=True)

    for i, result in enumerate(task1_results, 1):
        if isinstance(result, Exception):
            print(f'Task {i} failed: {str(result)}')
        elif result.exit_status != 0:
            print(f'Task {i} exited with status {str(result)}:')
            print(result.stderr, end='')
        else:
            print(f'Task {i} exited with  {str(result)}:')

            # Get Devices CDP Neighbours
            with open(f"textfsm/cisco_ios_show_cdp_neighbors_detail.textfsm") as f:
                re_table = textfsm.TextFSM(f)
                output = re_table.ParseText(result.stdout)
            outputs = [dict(zip(re_table.header, entry)) for entry in output]

            for entry in outputs:
                text = entry['DESTINATION_HOST']
                head, sep, tail = text.partition('.')
                entry['DESTINATION_HOST'] = head.upper()
                collection_of_results.append(entry)

        print(75 * '-')

    array = np.DataFrame(collection_of_results)
    filepath = 'CDP_Neighbors_Detail.xlsx'
    array.to_excel(filepath, index=False)


if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(run_multiple_clients())
