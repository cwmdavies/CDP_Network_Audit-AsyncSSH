import ipaddress
import logging as log
import time
import textfsm
import asyncssh
import asyncio


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
}

# def ip_check(ip) -> bool:
#     """
#     Takes in an IP Address as a string.
#     Checks that the IP address is a valid one.
#     Returns True or false.
#     :param ip: Example: 192.168.1.1
#     :return: Boolean
#     """
#     try:
#         ipaddress.ip_address(ip)
#         return True
#     except ValueError:
#         log.error(
#             f"ip_check function ValueError: IP Address: {ip} is an invalid address. Please check and try again!",
#             exc_info=True
#             )
#         return False
#
#
# def dns_resolve(domain_name) -> None:
#     """
#     Takes in a domain name and does a DNS lookup on it.
#     Saves the information to a dictionary
#     :param domain_name: Domain name. Example: google.com
#     :return: None. Saves IP Address and domain name to a dictionary. Example: {"google.com": "142.250.200.14"}
#     """
#     try:
#         log.info(f"Attempting to retrieve DNS 'A' record for hostname: {domain_name}")
#         addr1 = socket.gethostbyname(domain_name)
#         DNS_IP[domain_name] = addr1
#         log.info(f"Successfully retrieved DNS 'A' record for hostname: {domain_name}")
#     except socket.gaierror:
#         log.error(f"Failed to retrieve DNS A record for hostname: {domain_name}",
#                   exc_info=True
#                   )
#         DNS_IP[domain_name] = "DNS Resolution Failed"
#
#
# def get_cdp_details(ip) -> "None, appends dictionaries to a global list":
#     """
#     Takes in an IP Address as a string.
#     Connects to the host's IP Address and runs the 'show cdp neighbors detail'
#     command and parses the output using TextFSM and saves it to a list of dicts.
#     Returns None.
#     :param ip: The IP Address you wish to connect to.
#     :return: None, appends dictionaries to a global list.
#     """
#     jump_box = None
#     if jump_server == "None":
#         ssh, connection = direct_session(ip)
#     else:
#         ssh, jump_box, connection = jump_session(ip)
#     if not connection:
#         return None
#     hostname = get_hostname(ip)
#     if hostname not in HOSTNAMES:
#         HOSTNAMES.append(hostname)
#         log.info(f"Attempting to retrieve CDP Details for IP: {ip}")
#         _, stdout, _ = ssh.exec_command("show cdp neighbors detail")
#         stdout = stdout.read()
#         stdout = stdout.decode("utf-8")
#         with THREADLOCK:
#             with open("textfsm/cisco_ios_show_cdp_neighbors_detail.textfsm") as f:
#                 re_table = textfsm.TextFSM(f)
#                 result = re_table.ParseText(stdout)
#         result = [dict(zip(re_table.header, entry)) for entry in result]
#         for entry in result:
#             entry['LOCAL_HOST'] = hostname.upper()
#             entry['LOCAL_IP'] = ip
#             text = entry['DESTINATION_HOST']
#             head, sep, tail = text.partition('.')
#             entry['DESTINATION_HOST'] = head.upper()
#             COLLECTION_OF_RESULTS.append(entry)
#             if entry["MANAGEMENT_IP"] not in IP_LIST:
#                 if 'Switch' in entry['CAPABILITIES'] and "Host" not in entry['CAPABILITIES']:
#                     IP_LIST.append(entry["MANAGEMENT_IP"])
#     log.info(f"Successfully retrieved CDP Details for IP: {ip}")
#     ssh.close()
#     if jump_box:
#         jump_box.close()
#
#
# def get_hostname(ip) -> "Hostname as a string":
#     """
#     Connects to the host's IP Address and runs the 'show run | inc hostname'
#     command and parses the output using TextFSM and saves it as a string.
#     Returns the hostname as a string.
#     :param ip: The IP Address you wish to connect to.
#     :return: Hostname(str).
#     """
#     jump_box = None
#     if jump_server == "None":
#         ssh, connection = direct_session(ip)
#     else:
#         ssh, jump_box, connection = jump_session(ip)
#     if not connection:
#         return None
#     log.info(f"Attempting to retrieve hostname for IP: {ip}")
#     _, stdout, _ = ssh.exec_command("show run | inc hostname")
#     stdout = stdout.read()
#     stdout = stdout.decode("utf-8")
#     try:
#         with open("textfsm/hostname.textfsm") as f:
#             re_table = textfsm.TextFSM(f)
#             result = re_table.ParseText(stdout)
#             hostname = result[0][0]
#             log.info(f"Successfully retrieved hostname for IP: {ip}")
#     except Exception as Err:
#         log.error(Err, exc_info=True)
#         hostname = "Not Found"
#     ssh.close()
#     if jump_box:
#         jump_box.close()
#     return hostname


async def run_client(host, command: str) -> asyncssh.SSHCompletedProcess:
    async with asyncssh.connect(JUMP_HOST, **credentials) as tunnel:
        async with asyncssh.connect(host, tunnel=tunnel, **credentials) as conn:
            return await conn.run(command)


async def main():
    start = time.perf_counter()
    queue = asyncio.Queue()
    queue.put_nowait(HOST)

    output = await run_client(HOST, "show cdp neighbors detail")
    get_hostname = await run_client(HOST, "show run | inc hostname")

    with open("textfsm/hostname.textfsm") as f:
        re_table = textfsm.TextFSM(f)
        result = re_table.ParseText(get_hostname.stdout)
        hostname = result[0][0]

    with open("textfsm/cisco_ios_show_cdp_neighbors_detail.textfsm") as f:
        re_table = textfsm.TextFSM(f)
        result = re_table.ParseText(output.stdout)
    result = [dict(zip(re_table.header, entry)) for entry in result]
    for entry in result:
        entry['LOCAL_IP'] = HOST
        entry['LOCAL_HOST'] = hostname.upper()
        text = entry['DESTINATION_HOST']
        head, sep, tail = text.partition('.')
        entry['DESTINATION_HOST'] = head.upper()
    print(result)

    end = time.perf_counter()
    print(f"Script finished in {end - start:0.4f} seconds")

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())
