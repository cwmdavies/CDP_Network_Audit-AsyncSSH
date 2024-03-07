#!/usr/local/bin/python3
# -*- coding: cp1252 -*-
import asyncio
import asyncssh
import socket
import pandas as pd
import textfsm
import shutil
import openpyxl
import datetime
import argparse
from getpass import getpass
from ProgramFiles import config_params

parser = argparse.ArgumentParser()
parser.add_argument("-u", "--username", help="Username used to login to the device with.",
                    action="store",
                    dest="USERNAME",
                    required=True,
                    )
parser.add_argument("-a", "--ipaddress", help="Password used to login to the device with.",
                    action="store",
                    dest="HOST",
                    required=True,
                    )
parser.add_argument("-s", "--site_name", help="Site name used for the name of the Excel output file.",
                    action="store",
                    dest="SITE_NAME",
                    required=True,
                    )

ARGS = parser.parse_args()
USERNAME = ARGS.USERNAME
PASSWORD = getpass("Enter your password: ")
HOST = ARGS.HOST
SITE_NAME = ARGS.SITE_NAME
CDP_NEIGHBOUR_DETAILS = list()
DATE_TIME_NOW = datetime.datetime.now()
DATE_NOW = DATE_TIME_NOW.strftime("%d %B %Y")
TIME_NOW = DATE_TIME_NOW.strftime("%H:%M")
NEIGHBOURS = list()
HOSTNAMES = list()
AUTHENTICATION_ERRORS = list()
HOST_QUEUE = asyncio.Queue()
DNS_QUEUE = asyncio.Queue()
DNS_IP = {}

# Configuration Parameters from ini file
LIMIT = int(config_params.Settings["LIMIT"])
TIMEOUT = int(config_params.Settings["TIMEOUT"])
JUMP_SERVER = config_params.Jump_Servers["ACTIVE"]

# A set to keep track of visited hosts
VISITED = set()

encryption_algs_list = [
    "aes128-cbc",
    "3des-cbc",
    "aes192-cbc",
    "aes256-cbc",
    "aes256-ctr"
]

kex_algs_list = [
    "diffie-hellman-group-exchange-sha1",
    "diffie-hellman-group14-sha1",
    "diffie-hellman-group1-sha1",
    "diffie-hellman-group-exchange-sha256",
]

default_credentials = {
    "username": USERNAME,
    "password": PASSWORD,
    "known_hosts": None,
    "encryption_algs": encryption_algs_list,
    "kex_algs": kex_algs_list,
    "connect_timeout": TIMEOUT,
}


# A function to connect to a cisco switch and run a command
async def run_command(host, command):
    print(f"Trying the following command: {command}, on IP Address: {host}")
    try:
        async with asyncssh.connect(JUMP_SERVER, **default_credentials) as tunnel:
            async with asyncssh.connect(host, tunnel=tunnel, **default_credentials) as conn:
                result = await conn.run(command, check=True)
                return result.stdout
    except asyncssh.misc.ChannelOpenError:
        print(f"An error occurred when trying to connect to IP: {host}")
        return None
    except TimeoutError:
        print(f"An Timeout error occurred when trying to connect to IP: {host}")
        return None
    except asyncssh.misc.PermissionDenied:
        print(f"An Authentication error occurred when trying to connect to IP: {host}")
        if host not in AUTHENTICATION_ERRORS:
            AUTHENTICATION_ERRORS.append(host)
        return None


# A function to parse the cdp output and return a list of neighbors
def get_facts(output, output2, host, neighbour_list, hostnames_list, host_queue):
    if output is None:
        return None
    try:
        with open(f"ProgramFiles/textfsm/cisco_ios_show_cdp_neighbors_detail.textfsm", "r", encoding="cp1252") as f:
            re_table = textfsm.TextFSM(f)
            result = re_table.ParseText(output)
        get_cdp_neighbors_output = [dict(zip(re_table.header, entry)) for entry in result]

        # Parse Show Version Output
        with open(f"ProgramFiles/textfsm/cisco_ios_show_version.textfsm", "r", encoding="cp1252") as f:
            re_table = textfsm.TextFSM(f)
            result2 = re_table.ParseText(output2)
        get_version_output = [dict(zip(re_table.header, entry)) for entry in result2]

        hostname = get_version_output[0].get("HOSTNAME")
        serial_numbers = get_version_output[0].get("SERIAL")
        uptime = get_version_output[0].get("UPTIME")

        if hostname not in hostnames_list:
            hostnames_list.append(hostname)
            for entry in get_cdp_neighbors_output:
                entry["LOCAL_HOST"] = hostname
                entry["LOCAL_IP"] = host
                entry["LOCAL_SERIAL"] = serial_numbers
                entry["LOCAL_UPTIME"] = uptime
                text = entry['DESTINATION_HOST']
                head, sep, tail = text.partition('.')
                entry['DESTINATION_HOST'] = head.upper()
                neighbour_list.append(entry)
                if 'Switch' in entry['CAPABILITIES'] and "Host" not in entry['CAPABILITIES']:
                    host_queue.put_nowait(entry["MANAGEMENT_IP"])
    except Exception as err:
        print(f"An error occurred for host {host} : {err}")


# A function to recursively discover all devices in the network using cdp
async def discover_network(host, username, password, visited, queue):
    semaphore = asyncio.Semaphore(LIMIT)
    if host in visited:
        return
    visited.add(host)

    async def process_host(host_ip, semaphore_token):
        async with semaphore_token:  # Acquire the semaphore before proceeding
            for attempt in range(3):
                try:
                    output1 = await run_command(host_ip, "show cdp neighbors detail")
                    output2 = await run_command(host_ip, "show version")
                    get_facts(output1, output2, host_ip, CDP_NEIGHBOUR_DETAILS, HOSTNAMES, HOST_QUEUE)
                    # Discover neighbors on this host
                    await discover_network(host_ip, username, password, visited, queue)
                    break  # Success
                except (asyncio.TimeoutError, asyncssh.Error) as err:
                    print(f"Error on host {host_ip}, attempt {attempt + 1}: {err}")
                    await asyncio.sleep(2)

    # Process hosts in parallel
    hosts_tasks = []
    while not queue.empty():
        for _ in range(LIMIT):  # Create a batch of tasks
            if queue.empty():
                break
            host = queue.get_nowait()
            hosts_tasks.append(asyncio.create_task(process_host(host, semaphore)))

        await asyncio.gather(*hosts_tasks)  # Wait for tasks in this batch


async def resolve_dns(hostnames, queue):
    semaphore = asyncio.Semaphore(LIMIT)

    async def process_host(domain_name, semaphore_token):
        async with semaphore_token:  # Acquire the semaphore before proceeding
            try:
                print(f"Attempting to retrieve DNS 'A' record for hostname: {domain_name}")
                addr1 = socket.gethostbyname(domain_name)
                DNS_IP[domain_name] = addr1
                print(f"Successfully retrieved DNS 'A' record for hostname: {domain_name}")
            except socket.gaierror:
                print(f"Failed to retrieve DNS A record for hostname: {domain_name}")
                DNS_IP[domain_name] = "DNS Resolution Failed"
            except Exception as Err:
                print(f"An unknown error occurred for hostname: {domain_name}, {Err}",)

    for hostname in hostnames:
        queue.put_nowait(hostname)

    dns_tasks = []
    while not queue.empty():
        for _ in range(LIMIT):  # Create a batch of tasks
            if queue.empty():
                break
            dns_addr = queue.get_nowait()
            dns_tasks.append(asyncio.create_task(process_host(dns_addr, semaphore)))

        await asyncio.gather(*dns_tasks)  # Wait for tasks in this batch


# A function to save the information to excel
def save_to_excel(details_list, dns_info, host):

    # Create a dataframe from the network dictionary
    df = pd.DataFrame(details_list, columns=["LOCAL_HOST",
                                             "LOCAL_IP",
                                             "LOCAL_PORT",
                                             "LOCAL_SERIAL",
                                             "LOCAL_UPTIME",
                                             "DESTINATION_HOST",
                                             "REMOTE_PORT",
                                             "MANAGEMENT_IP",
                                             "PLATFORM",
                                             ])
    dns_array = pd.DataFrame(dns_info.items(), columns=["Hostname", "IP Address"])
    auth_array = pd.DataFrame(set(AUTHENTICATION_ERRORS), columns=["Authentication Errors"])

    filepath = f"{SITE_NAME}_CDP_Network_Audit.xlsx"
    excel_template = f"ProgramFiles\\config_files\\1 - CDP Network Audit _ Template.xlsx"
    shutil.copy2(src=excel_template, dst=filepath)

    wb = openpyxl.load_workbook(filepath)
    ws1 = wb["Audit"]
    ws1["B4"] = SITE_NAME
    ws1["B5"] = DATE_NOW
    ws1["B6"] = TIME_NOW
    ws1["B7"] = host
    wb.save(filepath)
    wb.close()

    # Save the dataframe to excel
    writer = pd.ExcelWriter(filepath, engine='openpyxl', if_sheet_exists="overlay", mode="a")
    df.to_excel(writer, index=False, sheet_name="Audit", header=False, startrow=11)
    dns_array.to_excel(writer, index=False, sheet_name="DNS Resolved", header=False, startrow=4)
    auth_array.to_excel(writer, index=False, sheet_name="Authentication Errors", header=False, startrow=4)
    writer.close()


# The main function
async def main():
    # Put first host in queue
    HOST_QUEUE.put_nowait(HOST)
    # Discover the network using cdp
    await discover_network(HOST, USERNAME, PASSWORD, VISITED, HOST_QUEUE)
    await resolve_dns(HOSTNAMES, DNS_QUEUE)
    # Save the network information to excel
    save_to_excel(CDP_NEIGHBOUR_DETAILS, DNS_IP, HOST)

# Run the main function
asyncio.run(main())
