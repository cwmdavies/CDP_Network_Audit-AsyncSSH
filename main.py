"""
Author Details:
Name: Chris Davies
Email: chris.davies@weavermanor.co.uk
Tested on Python 3.10

This script takes in up to two IP Addresses, preferably the core switches, runs the "Show CDP Neighbors Detail"
command and saves the information to a list of dictionaries. Each dictionary is then parsed for the neighbouring
IP Address for each CDP neighbour and saved to a separate list. Another list is used to store the IP Addresses
of those that have been processed so no switch is connected too more than once. A connection is made to each IP Address
in the list , using asynchronous multithreading, to retrieve the same information. This recursion goes on until there
are no more IP Addresses to connect to. The information is then converted to a numpy array and saved to an
Excel spreadsheet.
The script uses Asyncio/AsyncSSH to connect to multiple switches at a time and to run multiple commands asynchronously.
"""
import asyncio
import asyncssh
import textfsm
import pandas as np
import shutil
import openpyxl
import time
import datetime
import socket
import multiprocessing
import multiprocessing.pool
import os
import MyPackage.MyGui as MyGui
from MyPackage import config_params
import logging.config
import sys

MyGui.root.mainloop()
SiteName = MyGui.my_gui.SiteName_var.get()
jump_server = MyGui.my_gui.JumpServer_var.get()
USERNAME = MyGui.my_gui.Username_var.get()
PASSWORD = MyGui.my_gui.password_var.get()
IPAddr1 = MyGui.my_gui.IP_Address1_var.get()
IP_LIST = list()
if MyGui.my_gui.IP_Address2_var.get():
    IPAddr2 = MyGui.my_gui.IP_Address2_var.get()
else:
    IPAddr2 = None

FolderPath = MyGui.my_gui.FolderPath_var.get()

DATE_TIME_NOW = datetime.datetime.now()
DATE_NOW = DATE_TIME_NOW.strftime("%d %B %Y")
TIME_NOW = DATE_TIME_NOW.strftime("%H:%M")
IPS_PROCESSED = list()
HOSTNAMES = list()
DNS_IP = {}
CONNECTION_ERRORS = list()
AUTHENTICATION_ERRORS = list()
COLLECTION_OF_RESULTS = list()

logging.config.fileConfig(fname='config_files/logging_configuration.conf',
                          disable_existing_loggers=False,
                          )
log = logging.getLogger(__name__)

JUMP_SERVER_KEYS = list(config_params.Jump_Servers.keys())
JUMP_SERVER_DICT = dict(config_params.Jump_Servers)
if MyGui.my_gui.JumpServer_var.get() == JUMP_SERVER_KEYS[0].upper():
    jump_server = JUMP_SERVER_DICT[JUMP_SERVER_KEYS[0]]
if MyGui.my_gui.JumpServer_var.get() == JUMP_SERVER_KEYS[1].upper():
    jump_server = JUMP_SERVER_DICT[JUMP_SERVER_KEYS[1]]
if MyGui.my_gui.JumpServer_var.get() == "None":
    jump_server = "None"

encryption_algs_list = ["aes128-cbc", "3des-cbc", "aes192-cbc", "aes256-cbc", "aes256-ctr"]
kex_algs_list = ["diffie-hellman-group-exchange-sha1", "diffie-hellman-group14-sha1", "diffie-hellman-group1-sha1"]

credentials = {
    "username": USERNAME,
    "password": PASSWORD,
    "known_hosts": None,
    "encryption_algs": encryption_algs_list,
    "kex_algs": kex_algs_list,
    "connect_timeout": 10,
}


async def direct_connection(host, command: str) -> asyncssh.SSHCompletedProcess:
    log.info("Running Direct Connection Function")
    async with asyncssh.connect(host, **credentials) as conn:
        return await conn.run(command)


async def tunnel_connection(host, command: str) -> asyncssh.SSHCompletedProcess:
    log.info("Running Tunnel Connection Function")
    async with asyncssh.connect(jump_server, **credentials) as tunnel:
        async with asyncssh.connect(host, tunnel=tunnel, **credentials) as conn:
            return await conn.run(command)


def resolve_dns(domain_name) -> None:
    """
    Takes in a domain name and does a DNS lookup on it.
    Saves the information to a dictionary
    :param domain_name: Domain name. Example: google.com
    :return: None. Saves IP Address and domain name to a dictionary. Example: {"google.com": "142.250.200.14"}
    """
    try:
        log.info(f"Attempting to retrieve DNS 'A' record for hostname: {domain_name}")
        addr1 = socket.gethostbyname(domain_name)
        DNS_IP[domain_name] = addr1
        log.info(f"Successfully retrieved DNS 'A' record for hostname: {domain_name}")
    except socket.gaierror:
        log.error(f"Failed to retrieve DNS A record for hostname: {domain_name}")
        DNS_IP[domain_name] = "DNS Resolution Failed"
    except Exception as Err:
        log.error(f"An unknown error occurred for hostname: {domain_name}, {Err}")


async def get_facts(host):
    log.info(f"Getting Version information for host: {host}")
    if jump_server == "None":
        get_version = await direct_connection(host, 'show version')
    else:
        get_version = await tunnel_connection(host, 'show version')
    log.info(f"Version information retrieval successful for host: {host}")

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

        log.info(f"Getting CDP Neighbor Details for host: {host}")
        if jump_server == "None":
            get_cdp_neighbors = await direct_connection(host, 'show cdp neighbor detail')
        else:
            get_cdp_neighbors = await tunnel_connection(host, 'show cdp neighbor detail')
        log.info(f"CDP Neighbor Details retrieval successful for host: {host}")
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
            IPS_PROCESSED.append(host)


def run_multi_thread(function, iterable):
    thread_count = os.cpu_count()
    with multiprocessing.pool.ThreadPool(thread_count) as pool:
        i = 0
        while i < len(iterable):
            limit = i + min(thread_count, (len(iterable) - i))
            ip_addresses = iterable[i:limit]
            pool.map(function, ip_addresses)
            i = limit


async def main() -> None:
    start = time.perf_counter()

    if not IPAddr1:
        log.error("No IP Address specified, exiting script!")
        sys.exit()
    IP_LIST.append(IPAddr1)
    if IPAddr2 is not None:
        IP_LIST.append(IPAddr2)

    while len(IP_LIST) != 0:
        for IP in IPS_PROCESSED:
            if IP in IP_LIST:
                IP_LIST.remove(IP)
        get_facts_tasks = (get_facts(host) for host in IP_LIST)
        await asyncio.gather(*get_facts_tasks)

    run_multi_thread(resolve_dns, HOSTNAMES)

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

    filepath = f"{FolderPath}\\CDP_Neighbors_Detail.xlsx"
    excel_template = f"config_files\\1 - CDP Network Audit _ Template.xlsx"
    shutil.copy2(src=excel_template, dst=filepath)

    wb = openpyxl.load_workbook(filepath)
    ws1 = wb["Audit"]
    ws1["B4"] = SiteName
    ws1["B5"] = DATE_NOW
    ws1["B6"] = TIME_NOW
    ws1["B7"] = IPAddr1
    ws1["B8"] = IPAddr2 if IPAddr2 else "Not Specified"
    wb.save(filepath)
    wb.close()

    writer = np.ExcelWriter(filepath, engine='openpyxl', if_sheet_exists="overlay", mode="a")
    array.to_excel(writer, index=False, sheet_name="Audit", header=False, startrow=11)
    dns_array.to_excel(writer, index=False, sheet_name="DNS Resolved", header=False, startrow=4)
    writer.close()

    end = time.perf_counter()
    log.info(f"Script finished in {end - start:0.4f} seconds")

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())
