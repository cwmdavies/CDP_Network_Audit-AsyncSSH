import ipaddress
import shutil
import socket
import time
import logging
import openpyxl as openpyxl
import pandas as pandas
import textfsm
import datetime
import sys
import asyncssh
import asyncio
import MyPackage.MyGui as MyGui
from MyPackage import config_params
import logging.config

MyGui.root.mainloop()
SiteName = MyGui.my_gui.SiteName_var.get()
jump_server = MyGui.my_gui.JumpServer_var.get()
_USERNAME = MyGui.my_gui.Username_var.get()
_PASSWORD = MyGui.my_gui.password_var.get()
IPAddr1 = MyGui.my_gui.IP_Address1_var.get()

if MyGui.my_gui.IP_Address2_var.get():
    IPAddr2 = MyGui.my_gui.IP_Address2_var.get()
else:
    IPAddr2 = None

FolderPath = MyGui.my_gui.FolderPath_var.get()

DNS_IP = {}
AUTHENTICATION_ERRORS = []
CONNECTION_ERRORS = []
DATE_TIME_NOW = datetime.datetime.now()
DATE_NOW = DATE_TIME_NOW.strftime("%d %B %Y")
TIME_NOW = DATE_TIME_NOW.strftime("%H:%M")

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
    "username": _USERNAME,
    "password": _PASSWORD,
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
        log.error(f"An error occurred: {Err}",)
        return False


async def dns_resolve(domain_name) -> str:
    """
    Takes in a domain name and does a DNS lookup on it.
    Saves the information to a dictionary
    :param domain_name: Domain name. Example: google.com
    :return: None. Saves IP Address and domain name to a dictionary. Example: {"google.com": "142.250.200.14"}
    """
    try:
        logging.info(f"Attempting to retrieve DNS 'A' record for hostname: {domain_name}")
        addr1 = socket.gethostbyname(domain_name)
        logging.info(f"Successfully retrieved DNS 'A' record for hostname: {domain_name}")
        return addr1
    except socket.gaierror:
        log.error(f"No DNS A record found for domain name: {domain_name}")
        return "No DNS A record found"
    except Exception as Err:
        log.error(f"An unknown error occurred for hostname: {domain_name}, {Err}", exc_info=True)
        return "DNS Resolution Failed"


async def direct_client(host, command: str) -> asyncssh.SSHCompletedProcess:
    print(f"Running Direct Client function")
    async with asyncssh.connect(host, **credentials) as conn:
        return await conn.run(command)


async def tunnel_client(host, command: str) -> asyncssh.SSHCompletedProcess:
    print("Running Tunnel Client Function")
    async with asyncssh.connect(jump_server, **credentials) as tunnel:
        async with asyncssh.connect(host, tunnel=tunnel, **credentials) as conn:
            return await conn.run(command)


async def main():
    start = time.perf_counter()
    collection_of_results = []
    hostnames = []
    ip_addresses = []

    if not IPAddr1:
        logging.error("No IP Address specified, exiting script!")
        sys.exit()

    queue = asyncio.Queue()
    queue.put_nowait(IPAddr1)
    if IPAddr2 is not None:
        queue.put_nowait(IPAddr2)

    dns_queue = asyncio.Queue()

    while True:
        if queue.empty():
            break

        ip_address = queue.get_nowait()
        ip_addresses.append(ip_address)

        try:
            print(f"Attempting to get Hostname for IP Address: {ip_address} ")
            if jump_server is None:
                get_hostname = await direct_client(ip_address, "show run | inc hostname")
            else:
                get_hostname = await tunnel_client(ip_address, "show run | inc hostname")

            print(f"Hostname for IP Address: {ip_address} successfully retrieved")
            with open("textfsm/hostname.textfsm") as f:
                re_table = textfsm.TextFSM(f)
                result = re_table.ParseText(get_hostname.stdout)
                hostname = result[0][0]

            if hostname not in hostnames:
                hostnames.append(hostname)

                print(f"Attempting to get CDP information for IP Address: {ip_address}")

                if jump_server is None:
                    output = await direct_client(ip_address, "show cdp neighbors detail")
                else:
                    output = await tunnel_client(ip_address, "show cdp neighbors detail")

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

            queue.task_done()

        except TimeoutError:
            log.error("A Timeout error occurred!")
            CONNECTION_ERRORS.append(ip_address)
        except asyncssh.misc.PermissionDenied:
            log.error(f"Authentication Failed for IP Address: {ip_address}!")
            AUTHENTICATION_ERRORS.append(ip_address)
        except Exception as Err:
            log.error(f"An unknown error occurred: {Err}", exc_info=True)
            CONNECTION_ERRORS.append(ip_address)

    for i in hostnames:
        await dns_queue.put(i)
    while True:
        if dns_queue.empty():
            break
        get_hostname_from_queue = dns_queue.get_nowait()
        print(f"Attempting to resolve IP Address for hostname: {get_hostname_from_queue}")
        host_ip_addr = await dns_resolve(get_hostname_from_queue)
        DNS_IP[get_hostname_from_queue] = host_ip_addr
        dns_queue.task_done()

    end = time.perf_counter()

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
    conn_array = pandas.DataFrame(CONNECTION_ERRORS, columns=["Connection Errors"])
    auth_array = pandas.DataFrame(AUTHENTICATION_ERRORS, columns=["Authentication Errors"])

    filepath = f"{FolderPath}\\{SiteName}_CDP Switch Audit.xlsx"
    excel_template = "1 - CDP Switch Audit _ Template.xlsx"
    shutil.copy2(src=excel_template, dst=filepath)

    wb = openpyxl.load_workbook(filepath)
    ws1 = wb["Audit"]
    ws1["B4"] = SiteName            # Site Code
    ws1["B5"] = DATE_NOW            # Date
    ws1["B6"] = TIME_NOW            # Time
    ws1["B7"] = IPAddr1             # Seed IP Address 1
    ws1["B8"] = IPAddr2             # Seed IP Address 2
    wb.save(filepath)
    wb.close()

    writer = pandas.ExcelWriter(filepath, engine='openpyxl', if_sheet_exists="overlay", mode="a")
    audit_array.to_excel(writer, index=False, sheet_name="Audit", header=False, startrow=11)
    dns_array.to_excel(writer, index=False, sheet_name="DNS Resolved", header=False, startrow=4)
    conn_array.to_excel(writer, index=False, sheet_name="Connection Errors", header=False, startrow=4)
    auth_array.to_excel(writer, index=False, sheet_name="Authentication Errors", header=False, startrow=4)

    writer.close()
    print(f"Script finished in {end - start:0.4f} seconds")

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())
