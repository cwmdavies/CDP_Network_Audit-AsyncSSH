import asyncio
import asyncssh
import textfsm
import pandas as np
import shutil
import openpyxl
import datetime
from asyncstdlib.builtins import map as amap
from asyncstdlib.builtins import tuple as atuple
import socket

DATE_TIME_NOW = datetime.datetime.now()
DATE_NOW = DATE_TIME_NOW.strftime("%d %B %Y")
TIME_NOW = DATE_TIME_NOW.strftime("%H:%M")
IP_LIST = ["192.168.1.2"]
HOSTNAMES = []
DNS_IP = {}
CONNECTION_ERRORS = []
AUTHENTICATION_ERRORS = []
COLLECTION_OF_RESULTS = []

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


async def run_client(host, command: str) -> asyncssh.SSHCompletedProcess:
    async with asyncssh.connect(host, **credentials) as conn:
        return await conn.run(command)


def resolve_dns(domain_name) -> None:
    """
    Takes in a domain name and does a DNS lookup on it.
    Saves the information to a dictionary
    :param domain_name: Domain name. Example: google.com
    :return: None. Saves IP Address and domain name to a dictionary. Example: {"google.com": "142.250.200.14"}
    """
    try:
        print(f"Attempting to retrieve DNS 'A' record for hostname: {domain_name}")
        addr1 = socket.gethostbyname(domain_name)
        DNS_IP[domain_name] = addr1
        print(f"Successfully retrieved DNS 'A' record for hostname: {domain_name}")
    except socket.gaierror:
        print(f"Failed to retrieve DNS A record for hostname: {domain_name}")
        DNS_IP[domain_name] = "DNS Resolution Failed"
    except Exception as Err:
        print(f"An unknown error occurred for hostname: {domain_name}, {Err}")


async def get_facts(host):
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

    if hostname not in HOSTNAMES:
        HOSTNAMES.append(hostname)

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
            COLLECTION_OF_RESULTS.append(entry)
            if entry["MANAGEMENT_IP"] not in IP_LIST:
                if 'Switch' in entry['CAPABILITIES'] and "Host" not in entry['CAPABILITIES']:
                    IP_LIST.append(entry["MANAGEMENT_IP"])


async def run_multi_thread(function, iterable):
    thread_count = 5
    i = 0
    while i < len(iterable):
        limit = i + min(thread_count, (len(iterable) - i))
        ip_addresses = iterable[i:limit]
        await atuple(amap(function, ip_addresses))
        i = limit


async def main() -> None:
    await run_multi_thread(get_facts, IP_LIST)
    await run_multi_thread(resolve_dns, HOSTNAMES)

    array = np.DataFrame(COLLECTION_OF_RESULTS, columns=["LOCAL_HOST",
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
    dns_array = np.DataFrame(DNS_IP.items(), columns=["Hostname", "IP Address"])

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
    dns_array.to_excel(writer, index=False, sheet_name="DNS Resolved", header=False, startrow=4)
    writer.close()

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())
