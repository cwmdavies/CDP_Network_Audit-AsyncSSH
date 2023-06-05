import ipaddress
import shutil
import socket
import time
import logging
import openpyxl as openpyxl
import pandas as pandas
import textfsm
import asyncssh
import asyncio

DNS_IP = {}
JUMP_HOST = ""
HOST = ""

encryption_algs_list = ["aes128-cbc", "3des-cbc", "aes192-cbc", "aes256-cbc", "aes256-ctr"]
kex_algs_list = ["diffie-hellman-group-exchange-sha1", "diffie-hellman-group14-sha1", "diffie-hellman-group1-sha1"]


credentials = {
    "username": "",
    "password": "",
    "known_hosts": None,
    "encryption_algs": encryption_algs_list,
    "kex_algs": kex_algs_list,
    "connect_timeout": 4,
}


def ip_check(ip) -> bool:
    """
    Takes in an IP Address as a string.
    Checks that the IP address is a valid one.
    Returns True or false.
    :param ip: Example: 192.168.1.1
    :return: Boolean
    """
    try:
        ipaddress.ip_address(ip)
        return True
    except Exception as Err:
        print(
            f"An error occurred: {Err}",
            )
        return False


async def dns_resolve(domain_name) -> None:
    """
    Takes in a domain name and does a DNS lookup on it.
    Saves the information to a dictionary
    :param domain_name: Domain name. Example: google.com
    :return: None. Saves IP Address and domain name to a dictionary. Example: {"google.com": "142.250.200.14"}
    """
    try:
        logging.info(f"Attempting to retrieve DNS 'A' record for hostname: {domain_name}")
        addr1 = socket.gethostbyname(domain_name)
        DNS_IP[domain_name] = addr1
        logging.info(f"Successfully retrieved DNS 'A' record for hostname: {domain_name}")
    except Exception as Err:
        print(Err)
        logging.error(f"Failed to retrieve DNS A record for hostname: {domain_name}",
                      exc_info=True
                      )
        DNS_IP[domain_name] = "DNS Resolution Failed"


async def direct_client(host, command: str) -> asyncssh.SSHCompletedProcess:
    print(f"Running Direct Client function")
    async with asyncssh.connect(host, **credentials) as conn:
        return await conn.run(command)


async def tunnel_client(host, command: str) -> asyncssh.SSHCompletedProcess:
    print("Running Tunnel Client Function")
    async with asyncssh.connect(JUMP_HOST, **credentials) as tunnel:
        async with asyncssh.connect(host, tunnel=tunnel, **credentials) as conn:
            return await conn.run(command)


async def main():
    start = time.perf_counter()
    collection_of_results = []
    hostnames = []
    ip_addresses = []
    queue = asyncio.Queue()
    queue.put_nowait(HOST)

    dns_queue = asyncio.Queue()

    while True:
        if queue.empty():
            break

        ip_address = queue.get_nowait()
        ip_addresses.append(ip_address)

        try:
            print(f"Attempting to get Hostname for IP Address: {ip_address} ")
            get_hostname = await direct_client(ip_address, "show run | inc hostname")
            print(f"Hostname for IP Address: {ip_address} successfully retrieved")
            with open("textfsm/hostname.textfsm") as f:
                re_table = textfsm.TextFSM(f)
                result = re_table.ParseText(get_hostname.stdout)
                hostname = result[0][0]

            if hostname not in hostnames:
                hostnames.append(hostname)

                print(f"Attempting to get CDP information for IP Address: {ip_address}")
                output = await direct_client(ip_address, "show cdp neighbors detail")

                with open("textfsm/cisco_ios_show_cdp_neighbors_detail.textfsm") as f:
                    re_table = textfsm.TextFSM(f)
                    result = re_table.ParseText(output.stdout)
                result = [dict(zip(re_table.header, entry)) for entry in result]
                for entry in result:
                    entry['LOCAL_IP'] = ip_address
                    entry['LOCAL_HOST'] = hostname.upper()
                    text = entry['DESTINATION_HOST']
                    head, sep, tail = text.partition('.')
                    entry['DESTINATION_HOST'] = head.upper()
                    collection_of_results.append(entry)
                    if entry["MANAGEMENT_IP"] not in ip_addresses:
                        if 'Switch' in entry['CAPABILITIES'] and "Host" not in entry['CAPABILITIES']:
                            await queue.put(entry["MANAGEMENT_IP"])

        except Exception as Err:
            print(f"An error occurred: {Err} ")

        queue.task_done()

    for i in hostnames:
        dns_queue.put_nowait(i)
    while True:
        get_hostname_from_queue = dns_queue.get_nowait()
        print(f"Attempting to resolve IP Address for hostname: {get_hostname_from_queue}")
        await dns_resolve(get_hostname_from_queue)
        dns_queue.task_done()
        if dns_queue.empty():
            break

    end = time.perf_counter()
    print(f"Script finished in {end - start:0.4f} seconds")

    audit_array = pandas.DataFrame(collection_of_results, columns=["LOCAL_HOST",
                                                                   "LOCAL_IP",
                                                                   "LOCAL_PORT",
                                                                   "DESTINATION_HOST",
                                                                   "REMOTE_PORT",
                                                                   "MANAGEMENT_IP",
                                                                   "PLATFORM",
                                                                   "SOFTWARE_VERSION",
                                                                   "CAPABILITIES"
                                                                   ])
    dns_array = pandas.DataFrame(DNS_IP.items(), columns=["Hostname", "IP Address"])

    filepath = "Test_CDP Switch Audit.xlsx"
    excel_template = "1 - CDP Switch Audit _ Template.xlsx"
    shutil.copy2(src=excel_template, dst=filepath)

    wb = openpyxl.load_workbook(filepath)
    ws1 = wb["Audit"]
    ws1["B4"] = "Not Specified"
    ws1["B5"] = "Not Specified"
    ws1["B6"] = "Not Specified"
    ws1["B7"] = HOST
    ws1["B8"] = "Not Specified"
    wb.save(filepath)
    wb.close()

    writer = pandas.ExcelWriter(filepath, engine='openpyxl', if_sheet_exists="overlay", mode="a")
    audit_array.to_excel(writer, index=False, sheet_name="Audit", header=False, startrow=11)
    dns_array.to_excel(writer, index=False, sheet_name="DNS Resolved", header=False, startrow=4)

    writer.close()

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())
