import asyncio
import asyncssh
import pandas as pd
import textfsm
import shutil
import openpyxl
import datetime
import argparse
from getpass import getpass

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

parser.add_argument("-d", "--direct", help="True or False: Direct connection to the host."
                                           "Default is false which goes through a Jump Host.",
                    action="store",
                    dest="DIRECT",
                    required=False,
                    default=False,
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
HOST_QUEUE = asyncio.Queue()
JUMP_SERVER = ""
LIMIT = 5

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
    "connect_timeout": 10,
}


# A function to connect to a cisco switch and run a command
async def jump_connection(host, command):
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
        return None


async def direct_connection(host, command):
    print(f"Trying the following command: {command}, on IP Address: {host}")
    try:
        async with asyncssh.connect(host, **default_credentials) as conn:
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
        return None


# A function to parse the cdp output and return a list of neighbors
def get_facts(output, output2, host):
    global CDP_NEIGHBOUR_DETAILS
    global NEIGHBOURS
    global HOSTNAMES
    global HOST_QUEUE

    if output is None:
        return None
    try:
        with open(f"ProgramFiles/textfsm/cisco_ios_show_cdp_neighbors_detail.textfsm") as f:
            re_table = textfsm.TextFSM(f)
            result = re_table.ParseText(output)
        get_cdp_neighbors_output = [dict(zip(re_table.header, entry)) for entry in result]

        # Parse Show Version Output
        with open(f"ProgramFiles/textfsm/cisco_ios_show_version.textfsm") as f:
            re_table = textfsm.TextFSM(f)
            result2 = re_table.ParseText(output2)
        get_version_output = [dict(zip(re_table.header, entry)) for entry in result2]

        hostname = get_version_output[0].get("HOSTNAME")
        serial_numbers = get_version_output[0].get("SERIAL")
        uptime = get_version_output[0].get("UPTIME")

        if hostname not in HOSTNAMES:
            HOSTNAMES.append(hostname)
            for entry in get_cdp_neighbors_output:
                entry["LOCAL_HOST"] = hostname
                entry["LOCAL_IP"] = host
                entry["LOCAL_SERIAL"] = serial_numbers
                entry["LOCAL_UPTIME"] = uptime
                text = entry['DESTINATION_HOST']
                head, sep, tail = text.partition('.')
                entry['DESTINATION_HOST'] = head.upper()
                CDP_NEIGHBOUR_DETAILS.append(entry)
                if 'Switch' in entry['CAPABILITIES'] and "Host" not in entry['CAPABILITIES']:
                    HOST_QUEUE.put_nowait(entry["MANAGEMENT_IP"])
    except Exception as err:
        print(f"An error occurred for host {host} : {err}")


# A function to recursively discover all devices in the network using cdp
async def discover_network(host, username, password, visited):
    global HOST_QUEUE
    if HOST_QUEUE.empty():
        return
    # Put host in queue
    HOST_QUEUE.put_nowait(host)
    # Check if the host is already visited
    if host in visited:
        return
    # Mark the host as visited
    visited.add(host)
    # Run the show cdp neighbour detail command on the host
    if ARGS.DIRECT is False:
        # Run the show version command on the host
        output1 = await jump_connection(host, "show cdp neighbors detail")
        # Parse the cdp output and get the neighbors
        output2 = await jump_connection(host, "show version")
    else:
        run_command = direct_connection
        # Run the show version command on the host
        output1 = await direct_connection(host, "show cdp neighbors detail")
        # Parse the cdp output and get the neighbors
        output2 = await direct_connection(host, "show version")

    get_facts(output1, output2, host)
    hosts_list = list()
    # Recursively discover the neighbours
    try:
        for i in range(LIMIT):
            if HOST_QUEUE.empty():
                break
            hosts_list.append(HOST_QUEUE.get_nowait())
        get_facts_tasks = (discover_network(host, username, password, visited) for host in hosts_list)
        await asyncio.gather(*get_facts_tasks)
    except Exception as err:
        print(f"An error occurred for host {host} : {err}")


# A function to save the information to excel
def save_to_excel(details_list):
    global HOST

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

    filepath = f"{SITE_NAME}_CDP_Network_Audit.xlsx"
    excel_template = f"ProgramFiles\\config_files\\1 - CDP Network Audit _ Template.xlsx"
    shutil.copy2(src=excel_template, dst=filepath)

    wb = openpyxl.load_workbook(filepath)
    ws1 = wb["Audit"]
    ws1["B4"] = SITE_NAME
    ws1["B5"] = DATE_NOW
    ws1["B6"] = TIME_NOW
    ws1["B7"] = HOST
    wb.save(filepath)
    wb.close()

    # Save the dataframe to excel
    writer = pd.ExcelWriter(filepath, engine='openpyxl', if_sheet_exists="overlay", mode="a")
    df.to_excel(writer, index=False, sheet_name="Audit", header=False, startrow=11)
    writer.close()


# The main function
async def main():
    global CDP_NEIGHBOUR_DETAILS
    global HOST
    global USERNAME
    global PASSWORD

    # A set to keep track of visited hosts
    visited = set()
    # Put first host in queue
    HOST_QUEUE.put_nowait(HOST)
    # Discover the network using cdp
    await discover_network(HOST, USERNAME, PASSWORD, visited)
    # Save the network information to excel
    save_to_excel(CDP_NEIGHBOUR_DETAILS)

# Run the main function
asyncio.run(main())
