#!/usr/bin/python2
#
# Copyright (c) 2003 Intel Corporation
# All rights reserved.
#
# Copyright (c) 2004-2006 The Trustees of Princeton University
# All rights reserved.


import os

from Exceptions import *
import utils


# if this file is present in the vservers /etc directory,
# the resolv.conf and hosts files will automatically be updated
# by the bootmanager
UPDATE_FILE_FLAG = "AUTO_UPDATE_NET_FILES"


def Run(vars, log):
    """
    Reconfigure a node if necessary, including rewriting any network init
    scripts based on what PLC has. Also, update any slivers on the machine
    incase their network files are out of date (primarily /etc/hosts).

    Also write out /etc/planetlab/session, a random string that gets
    a new value at every request of BootGetNodeDetails (ie, every boot)

    This step expects the root to be already mounted on SYSIMG_PATH.
    
    Except the following keys to be set:
    SYSIMG_PATH              the path where the system image will be mounted
                             (always starts with TEMP_PATH)
    ROOT_MOUNTED             the node root file system is mounted
    INTERFACE_SETTINGS  A dictionary of the values from the network
                                configuration file
    """
    
    log.write("\n\nStep: Updating node configuration.\n")

    # make sure we have the variables we need
    try:
        INTERFACE_SETTINGS = vars["INTERFACE_SETTINGS"]
        if INTERFACE_SETTINGS == "":
            raise ValueError("INTERFACE_SETTINGS")

        SYSIMG_PATH = vars["SYSIMG_PATH"]
        if SYSIMG_PATH == "":
            raise ValueError("SYSIMG_PATH")

        ROOT_MOUNTED = vars["ROOT_MOUNTED"]
        if ROOT_MOUNTED == "":
            raise ValueError("ROOT_MOUNTED")

    except KeyError as var:
        raise BootManagerException("Missing variable in vars: {}\n".format(var))
    except ValueError as var:
        raise BootManagerException("Variable in vars, shouldn't be: {}\n".format(var))

    try:
        ip = INTERFACE_SETTINGS['ip']
        method = INTERFACE_SETTINGS['method']
        hostname = INTERFACE_SETTINGS['hostname']
        domainname = INTERFACE_SETTINGS['domainname']
    except KeyError as var:
        raise BootManagerException(
              "Missing network value {} in var INTERFACE_SETTINGS\n".format(var))

    
    if not ROOT_MOUNTED:
        raise BootManagerException("Root isn't mounted on SYSIMG_PATH\n")

    log.write("Updating vserver's /etc/hosts and /etc/resolv.conf files\n")

    # create a list of the full directory paths of all the vserver images that
    # need to be updated.
    update_path_list = []

    for base_dir in ('/vservers', '/vservers/.vref', '/vservers/.vcache'):
        try:
            full_dir_path = "{}/{}".format(SYSIMG_PATH, base_dir)
            slices = os.listdir(full_dir_path)

            try:
                slices.remove("lost+found")
            except ValueError as e:
                pass
            
            update_path_list = update_path_list + \
                               ["{}/{}".format(full_dir_path, x) for x in slices]

        except OSError as e:
            continue


    log.write("Updating network configuration in:\n")
    if len(update_path_list) == 0:
        log.write("No vserver images found to update.\n")
    else:
        for base_dir in update_path_list:
            log.write("{}\n".format(base_dir))


    # now, update /etc/hosts and /etc/resolv.conf in each dir if
    # the update flag is there
    for base_dir in update_path_list:
        update_vserver_network_files(base_dir, vars, log)
    
    return



def update_vserver_network_files(vserver_dir, vars, log):
    """
    Update the /etc/resolv.conf and /etc/hosts files in the specified
    vserver directory. If the files do not exist, write them out. If they
    do exist, rewrite them with new values if the file UPDATE_FILE_FLAG
    exists it /etc. if this is called with the vserver-reference directory,
    always update the network config files and create the UPDATE_FILE_FLAG.

    This is currently called when setting up the initial vserver reference,
    and later when nodes boot to update existing vserver images.

    Expect the following variables from the store:
    SYSIMG_PATH        the path where the system image will be mounted
                       (always starts with TEMP_PATH)
    INTERFACE_SETTINGS   A dictionary of the values from the network
                       configuration file
    """

    try:
        SYSIMG_PATH = vars["SYSIMG_PATH"]
        if SYSIMG_PATH == "":
            raise ValueError("SYSIMG_PATH")

        INTERFACE_SETTINGS = vars["INTERFACE_SETTINGS"]
        if INTERFACE_SETTINGS == "":
            raise ValueError("INTERFACE_SETTINGS")

    except KeyError as var:
        raise BootManagerException("Missing variable in vars: {}\n".format(var))
    except ValueError as var:
        raise BootManagerException("Variable in vars, shouldn't be: {}\n".format(var))

    try:
        ip = INTERFACE_SETTINGS['ip']
        method = INTERFACE_SETTINGS['method']
        hostname = INTERFACE_SETTINGS['hostname']
        domainname = INTERFACE_SETTINGS['domainname']
    except KeyError as var:
        raise BootManagerException(
              "Missing network value {} in var INTERFACE_SETTINGS\n".format(var))

    try:
        os.listdir(vserver_dir)
    except OSError:
        log.write("Directory {} does not exist to write network conf in.\n"
                  .format(vserver_dir))
        return

    file_path = "{}/etc/{}".format(vserver_dir, UPDATE_FILE_FLAG)
    update_files = 0
    if os.access(file_path, os.F_OK):
        update_files = 1

        
    # Thierry - 2012/03 - I'm renaming vserver-reference into sliceimage
    # however I can't quite grasp the reason for this test below, very likely 
    # compatibility with very old node images or something
    if '/.vref/' in vserver_dir or \
       '/.vcache/' in vserver_dir or \
       '/vserver-reference' in vserver_dir:
        log.write("Forcing update on vserver reference directory:\n{}\n"
                  .format(vserver_dir))
        utils.sysexec_noerr("echo '{}' > {}/etc/{}"
                            .format(UPDATE_FILE_FLAG, vserver_dir, UPDATE_FILE_FLAG),
                             log)
        update_files = 1
        

    if update_files:
        log.write("Updating network files in {}.\n".format(vserver_dir))
        try:
            # NOTE: this works around a recurring problem on public pl,
            # suspected to be due to mismatch between 2.6.12 bootcd and
            # 2.6.22/f8 root environment.  files randomly show up with the
            # immutible attribute set.  this clears it before trying to write
            # the files below.
            utils.sysexec("chattr -i {}/etc/hosts".format(vserver_dir), log)
            utils.sysexec("chattr -i {}/etc/resolv.conf".format(vserver_dir), log)
        except:
            pass

        
        file_path = "{}/etc/hosts".format(vserver_dir)
        hosts_file = file(file_path, "w")
        hosts_file.write("127.0.0.1       localhost\n")
        if method == "static":
            hosts_file.write("{} {}.{}\n".format(ip, hostname, domainname))
        hosts_file.close()
        hosts_file = None

        file_path = "{}/etc/resolv.conf".format(vserver_dir)
        if method == "dhcp":
            # copy the resolv.conf from the boot cd env.
            utils.sysexec("cp /etc/resolv.conf {}/etc".format(vserver_dir), log)
        else:
            # copy the generated resolv.conf from the system image, since
            # we generated it via static settings
            utils.sysexec("cp {}/etc/resolv.conf {}/etc"
                          .format(SYSIMG_PATH, vserver_dir), log)
            
    return 
