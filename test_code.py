import asyncio
import asyncssh
import textfsm
import pandas as np
import shutil
import openpyxl
import datetime

DATE_TIME_NOW = datetime.datetime.now()
DATE_NOW = DATE_TIME_NOW.strftime("%d %B %Y")
TIME_NOW = DATE_TIME_NOW.strftime("%H:%M")
hosts_queue = asyncio.Queue()
hosts_queue.put_nowait("192.168.1.1")
ip_addresses = []
hostnames = []
hosts = list()
collection_of_results = []

encryption_algs_list = ["aes128-cbc", "3des-cbc", "aes192-cbc", "aes256-cbc", "aes256-ctr"]
kex_algs_list = ["diffie-hellman-group-exchange-sha1", "diffie-hellman-group14-sha1", "diffie-hellman-group1-sha1"]

credentials = {
    "username": '',
    "password": '',
    "known_hosts": None,
    "encryption_algs": encryption_algs_list,
    "kex_algs": kex_algs_list,
    "connect_timeout": 10,
}


async def run_client(host, command: str) -> asyncssh.SSHCompletedProcess:
    async with asyncssh.connect(host, **credentials) as conn:
        return await conn.run(command)


async def get_facts(host):
    ip_addresses.append(host)
    print(f"Getting Version information for host: {host}")
    get_version = await run_client(host, 'show version')

    # Parse Show Version Output
    with open(f"textfsm/cisco_ios_show_version.textfsm") as f:
        re_table = textfsm.TextFSM(f)
        result = re_table.ParseText(get_version.stdout)
    get_version_output = [dict(zip(re_table.header, entry)) for entry in result]

    hostname = get_version_output[0].get("HOSTNAME")
    serial_numbers = get_version_output[0].get("SERIAL")
    uptime = get_version_output[0].get("UPTIME")

    if hostname not in hostnames:
        hostnames.append(hostname)

        print(f"Getting CDP Neighbor Details for host: {host}")
        get_cdp_neighbors = await run_client(host, 'show cdp neighbor detail')
        with open(f"textfsm/cisco_ios_show_cdp_neighbors_detail.textfsm") as f:
            re_table = textfsm.TextFSM(f)
            result = re_table.ParseText(get_cdp_neighbors.stdout)
        get_cdp_neighbors_output = [dict(zip(re_table.header, entry)) for entry in result]

        for entry in get_cdp_neighbors_output:
            entry["LOCAL_HOST"] = hostname
            entry["LOCAL_IP"] = host
            entry["LOCAL_SERIAL"] = serial_numbers
            entry["LOCAL_UPTIME"] = uptime
            text = entry['DESTINATION_HOST']
            head, sep, tail = text.partition('.')
            entry['DESTINATION_HOST'] = head.upper()
            collection_of_results.append(entry)
            if entry["MANAGEMENT_IP"] not in ip_addresses:
                if 'Switch' in entry['CAPABILITIES'] and "Host" not in entry['CAPABILITIES']:
                    hosts_queue.put_nowait(entry["MANAGEMENT_IP"])


async def run_multiple_clients() -> None:
    while True:
        if hosts_queue.empty():
            break

        for host in range(hosts_queue.qsize()):
            hosts.append(hosts_queue.get_nowait())

            print(hosts)
            tasks = (get_facts(host) for host in hosts)
            await asyncio.gather(*tasks)
        hosts_queue.task_done()
        hosts.clear()

    array = np.DataFrame(collection_of_results, columns=["LOCAL_HOST",
                                                         "LOCAL_IP",
                                                         "LOCAL_PORT",
                                                         "LOCAL_SERIAL",
                                                         "LOCAL_UPTIME",
                                                         "DESTINATION_HOST",
                                                         "REMOTE_PORT",
                                                         "MANAGEMENT_IP",
                                                         "PLATFORM",
                                                         "SOFTWARE_VERSION",
                                                         "CAPABILITIES"
                                                         ])
    filepath = 'CDP_Neighbors_Detail.xlsx'
    excel_template = f"config_files\\1 - CDP Network Audit _ Template.xlsx"
    shutil.copy2(src=excel_template, dst=filepath)

    wb = openpyxl.load_workbook(filepath)
    ws1 = wb["Audit"]
    ws1["B5"] = DATE_NOW
    ws1["B6"] = TIME_NOW
    wb.save(filepath)
    wb.close()

    writer = np.ExcelWriter(filepath, engine='openpyxl', if_sheet_exists="overlay", mode="a")
    array.to_excel(writer, index=False, sheet_name="Audit", header=False, startrow=11)

    writer.close()

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(run_multiple_clients())
