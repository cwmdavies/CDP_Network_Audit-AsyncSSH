import configparser
import os

parser = configparser.ConfigParser()

try:
    if os.path.isfile("ProgramFiles/config_files/global_config.ini"):
        parser.read("ProgramFiles/config_files/global_config.ini")
    else:
        raise FileNotFoundError
except FileNotFoundError:
    print("Error: Configuration file not found. Please check and try again")

Jump_Servers = parser["Jump_Server"]
Settings = parser["Settings"]
