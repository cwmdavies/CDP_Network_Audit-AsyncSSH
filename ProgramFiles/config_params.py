import configparser
import os
import logging.config

logging.config.fileConfig(fname='config_files/logging_configuration.conf',
                          disable_existing_loggers=False,
                          )
log = logging.getLogger(__name__)

parser = configparser.ConfigParser()

try:
    if os.path.isfile("config_files/global_config.ini"):
        parser.read("config_files/global_config.ini")
    else:
        raise FileNotFoundError
except FileNotFoundError:
    log.error("Error: Configuration file not found. Please check and try again")

Settings = parser["Settings"]
Jump_Servers = parser["Jump_Server"]
