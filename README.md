# CDP Network Audit - AsyncSSH Version

This script takes in an IP Addresses, preferably the core switches, runs the "Show CDP Neighbors Detail" command and saves the information to a list of dictionaries.
Each dictionary is then parsed for the neighbouring IP Address for each CDP neighbour and saved to a separate list. Another list is used to store the IP Addresses of those that have been processed so no switch is connected too more than once.
Each IP Address in the list is connected to, multiple at a time, equal to the amount of cores in your machine, to retrieve the same information. This recursion goes on until there are no more IP Addresses to connect to.
The information is then converted to a numpy array and saved to an Excel spreadsheet.
AsyncSSH and AsyncIO are used for concurrency and multiprocessing.

The following information is retrieved from the CDP output and recorded in an Excel sheet for each switch that is logged into:

Local Interface
Local Serial
Local IP
Destination Host
Rmote Port
Remote IP
Platform
Software Version
Capabilities
