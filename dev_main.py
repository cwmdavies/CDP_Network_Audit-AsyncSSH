import asyncio
import asyncssh
import textfsm


class Device(asyncssh.client.SSHClient):
    def __init__(self, site_name, ipaddr, username, password):
        self.site_name = site_name
        self.ipaddr = ipaddr
        self.username = username
        self.password = password
        self.jump_connection = None
        self.connection = None
        self.hostname = None
        self.serial_numbers = None
        self.uptime = None
        self.cdp_neighbour_information = None
        self.device_information = None
        self.encryption_algs_list = ["aes128-cbc", "3des-cbc", "aes192-cbc", "aes256-cbc", "aes256-ctr"]
        self.kex_algs_list = ["diffie-hellman-group-exchange-sha1", "diffie-hellman-group14-sha1",
                              "diffie-hellman-group1-sha1"]

    async def connect(self):
        self.connection = \
            await asyncssh.connect(
                self.ipaddr,
                username=self.username,
                password=self.password,
                known_hosts=None,
                encryption_algs=self.encryption_algs_list,
                kex_algs=self.kex_algs_list,
                connect_timeout=10,
            )

    async def get_cdp_neighbors(self):
        show_cdp_neighbours = await self.connection.run('show cdp neighbors detail')
        with open(f"textfsm/cisco_ios_show_cdp_neighbors_detail.textfsm") as f:
            re_table = textfsm.TextFSM(f)
            output = re_table.ParseText(show_cdp_neighbours.stdout)
        self.cdp_neighbour_information = [dict(zip(re_table.header, entry)) for entry in output]

        self.cdp_neighbour_information[0]["LOCAL_IP"] = self.ipaddr
        self.cdp_neighbour_information[0]["LOCAL_HOST"] = self.hostname
        self.cdp_neighbour_information[0]["LOCAL_SERIAL"] = self.serial_numbers
        self.cdp_neighbour_information[0]["LOCAL_UPTIME"] = self.uptime
        dest_host = self.cdp_neighbour_information[0]['DESTINATION_HOST']
        head, sep, tail = dest_host.partition('.')
        self.cdp_neighbour_information[0]['DESTINATION_HOST'] = head.upper()
        await self.close()

        return self.cdp_neighbour_information[0]

    async def get_device_info(self):
        show_version = await self.connection.run('show version')
        with open(f"textfsm/cisco_ios_show_version.textfsm") as f:
            re_table = textfsm.TextFSM(f)
            output = re_table.ParseText(show_version.stdout)
        self.device_information = [dict(zip(re_table.header, entry)) for entry in output]

        self.hostname = self.device_information[0].get("HOSTNAME")
        self.serial_numbers = self.device_information[0].get("SERIAL")
        self.uptime = self.device_information[0].get("UPTIME")
        await self.close()

        return self.device_information[0]

    def get_info(self, string):
        device_information = {**self.cdp_neighbour_information[0], **self.device_information[0]}
        return device_information[string]

    async def close(self):
        self.connection.close()
        await self.connection.wait_closed()


# Usage
async def main():
    device = Device('', '', '', '')

    await device.connect()
    cdp_output = await device.get_cdp_neighbors()

    await device.connect()
    version_output = await device.get_device_info()

    merged = {**cdp_output, **version_output}
    print(merged)

    if device:
        print(device.hostname)


asyncio.run(main())
