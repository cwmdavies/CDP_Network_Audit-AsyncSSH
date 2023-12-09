import asyncio
import asyncssh
import textfsm


class CiscoDevice(asyncssh.client.SSHClient):
    def __init__(self, ipaddr, username, password):
        self.connection = None
        self.ipaddr = ipaddr
        self.hostname = None
        self.serial_numbers = None
        self.uptime = None
        self.username = username
        self.password = password

    async def connect(self):
        encryption_algs_list = ["aes128-cbc", "3des-cbc", "aes192-cbc", "aes256-cbc", "aes256-ctr"]
        kex_algs_list = ["diffie-hellman-group-exchange-sha1", "diffie-hellman-group14-sha1",
                         "diffie-hellman-group1-sha1"]
        self.connection = await asyncssh.connect(
            self.ipaddr,
            username=self.username,
            password=self.password,
            known_hosts=None,
            encryption_algs=encryption_algs_list,
            kex_algs=kex_algs_list,
            connect_timeout=10,
        )

    async def get_cdp_neighbors(self):
        show_cdp_neighbours = await self.connection.run('show cdp neighbors detail')
        with open(f"textfsm/cisco_ios_show_cdp_neighbors_detail.textfsm") as f:
            re_table = textfsm.TextFSM(f)
            output = re_table.ParseText(show_cdp_neighbours.stdout)
        get_cdp_neighbors_parsed = [dict(zip(re_table.header, entry)) for entry in output]

        get_cdp_neighbors_parsed[0]["LOCAL_IP"] = self.ipaddr
        get_cdp_neighbors_parsed[0]["LOCAL_HOST"] = self.hostname
        get_cdp_neighbors_parsed[0]["LOCAL_SERIAL"] = self.serial_numbers
        get_cdp_neighbors_parsed[0]["LOCAL_UPTIME"] = self.uptime
        dest_host = get_cdp_neighbors_parsed[0]['DESTINATION_HOST']
        head, sep, tail = dest_host.partition('.')
        get_cdp_neighbors_parsed[0]['DESTINATION_HOST'] = head.upper()

        return get_cdp_neighbors_parsed

    async def get_version(self):
        show_version = await self.connection.run('show version')
        with open(f"textfsm/cisco_ios_show_version.textfsm") as f:
            re_table = textfsm.TextFSM(f)
            output = re_table.ParseText(show_version.stdout)
        get_version_results_parsed = [dict(zip(re_table.header, entry)) for entry in output]

        self.hostname = get_version_results_parsed[0].get("HOSTNAME")
        self.serial_numbers = get_version_results_parsed[0].get("SERIAL")
        self.uptime = get_version_results_parsed[0].get("UPTIME")

        return get_version_results_parsed

    async def close(self):
        self.connection.close()
        await self.connection.wait_closed()


# Usage
async def main():
    device = CiscoDevice('', '', '')

    await device.connect()
    cdp_output = await device.get_cdp_neighbors()
    await device.close()

    await device.connect()
    version_output = await device.get_version()
    await device.close()

    print(cdp_output)
    print(version_output)


asyncio.run(main())