import asyncio
import asyncssh
import textfsm

class CiscoDevice(asyncssh.client.SSHClient):
    def __init__(self, host, username, password):
        self.connection = None
        self.host = host
        self.username = username
        self.password = password

    async def connect(self):
        self.connection = await asyncssh.connect(
            self.host,
            username=self.username,
            password=self.password
        )

    async def run_command(self, command):
        result = await self.connection.run(command)

        with open(f"textfsm/cisco_ios_show_cdp_neighbors_detail.textfsm") as f:
            re_table = textfsm.TextFSM(f)
            output = re_table.ParseText(result.stdout)
        get_cdp_neighbors_parsed = [dict(zip(re_table.header, entry)) for entry in output]
        get_cdp_neighbors_parsed[0]["LOCAL_IP"] = self.host

        return get_cdp_neighbors_parsed

    async def close(self):
        self.connection.close()
        await self.connection.wait_closed()


# Usage
async def main():
    device = CiscoDevice('', '', '')
    await device.connect()
    output = await device.run_command('show cdp neighbors detail')
    print(output)
    await device.close()

asyncio.run(main())