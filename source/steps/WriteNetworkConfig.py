#!/usr/bin/python2
#
# Copyright (c) 2003 Intel Corporation
# All rights reserved.
#
# Copyright (c) 2004-2006 The Trustees of Princeton University
# All rights reserved.
# expected /proc/partitions format

import os, string
import traceback

import utils
import urlparse
import httplib

from Exceptions import *
import BootServerRequest
import ModelOptions
import BootAPI
import plnet

class BootAPIWrap:
    def __init__(self, vars):
        self.vars = vars
    def call(self, func, *args):
        return BootAPI.call_api_function(self.vars, func, args)
    def __getattr__(self, func):
        return lambda *args: self.call(func, *args)

class logger:
    def __init__(self, log):
        self._log = log
    def log(self, msg, level=3):
        self._log.write(msg + "\n")
    def verbose(self, msg):
        self.log(msg, 0)

def Run(vars, log):
    """
    Write out the network configuration for this machine:
    /etc/hosts
    /etc/sysconfig/network-scripts/ifcfg-<ifname>
    /etc/resolv.conf (if applicable)
    /etc/sysconfig/network

    The values to be used for the network settings are to be set in vars
    in the variable 'INTERFACE_SETTINGS', which is a dictionary
    with keys:

     Key               Used by this function
     -----------------------------------------------
     node_id
     node_key
     method            x
     ip                x
     mac               x (optional)
     gateway           x
     network           x
     broadcast         x
     netmask           x
     dns1              x
     dns2              x (optional)
     hostname          x
     domainname        x

    Expect the following variables from the store:
    SYSIMG_PATH             the path where the system image will be mounted
                                (always starts with TEMP_PATH)
    INTERFACES              All the interfaces associated with this node
    INTERFACE_SETTINGS      dictionary
    Sets the following variables:
    None
    """

    log.write("\n\nStep: Install: Writing Network Configuration files.\n")

    try:
        SYSIMG_PATH = vars["SYSIMG_PATH"]
        if SYSIMG_PATH == "":
            raise ValueError("SYSIMG_PATH")

    except KeyError as var:
        raise BootManagerException("Missing variable in vars: {}\n".format(var))
    except ValueError as var:
        raise BootManagerException("Variable in vars, shouldn't be: {}\n".format(var))


    try:
        INTERFACE_SETTINGS = vars['INTERFACE_SETTINGS']
    except KeyError as e:
        raise BootManagerException("No interface settings found in vars.")

    try:
        hostname = INTERFACE_SETTINGS['hostname']
        domainname = INTERFACE_SETTINGS['domainname']
        method = INTERFACE_SETTINGS['method']
        ip = INTERFACE_SETTINGS['ip']
        gateway = INTERFACE_SETTINGS['gateway']
        network = INTERFACE_SETTINGS['network']
        netmask = INTERFACE_SETTINGS['netmask']
        dns1 = INTERFACE_SETTINGS['dns1']
        mac = INTERFACE_SETTINGS['mac']
    except KeyError as e:
        raise BootManagerException("Missing value {} in interface settings.".format(e))

    # dns2 is not required to be set
    dns2 = INTERFACE_SETTINGS.get('dns2','')

    # Node Manager needs at least PLC_API_HOST and PLC_BOOT_HOST
    log.write("Writing /etc/planetlab/plc_config\n")
    utils.makedirs("{}/etc/planetlab".format(SYSIMG_PATH))
    with open("{}/etc/planetlab/plc_config".format(SYSIMG_PATH), "w") as plc_config:

        api_url = vars['BOOT_API_SERVER']
        (scheme, netloc, path, params, query, fragment) = urlparse.urlparse(api_url)
        parts = netloc.split(':')
        host = parts[0]
        if len(parts) > 1:
            port = parts[1]
        else:
            port = '80'
        try:
            log.write("getting via https://{}/PlanetLabConf/get_plc_config.php ".format(host))
            bootserver = httplib.HTTPSConnection(host, int(port))
            bootserver.connect()
            bootserver.request("GET","https://{}/PlanetLabConf/get_plc_config.php".format(host))
            plc_config.write("{}".format(bootserver.getresponse().read()))
            bootserver.close()
            log.write("Done\n")
        except:
            log.write(" .. Failed.  Using old method. -- stack trace follows\n")
            traceback.print_exc(file=log.OutputFile)
            bs = BootServerRequest.BootServerRequest(vars)
            if bs.BOOTSERVER_CERTS:
                plc_config.write("PLC_BOOT_HOST='{}'\n".format(bs.BOOTSERVER_CERTS.keys()[0]))
            plc_config.write("PLC_API_HOST='{}'\n".format(host))
            plc_config.write("PLC_API_PORT='{}'\n".format(port))
            plc_config.write("PLC_API_PATH='{}'\n".format(path))

    log.write("Writing /etc/hosts\n")
    with open("{}/etc/hosts".format(SYSIMG_PATH), "w") as hosts_file:
        hosts_file.write("127.0.0.1       localhost\n")
        if method == "static":
            hosts_file.write("{} {}.{}\n".format(ip, hostname, domainname))

    data =  {'hostname': '{}.{}'.format(hostname, domainname),
             'interfaces': vars['INTERFACES']}
    plnet.InitInterfaces(
        logger(log), BootAPIWrap(vars),
        data, SYSIMG_PATH,
        files_only=True, program="BootManager")
