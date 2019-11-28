#!/usr/bin/python2
#
# Copyright (c) 2003 Intel Corporation
# All rights reserved.
#
# Copyright (c) 2004-2006 The Trustees of Princeton University
# All rights reserved.
# expected /proc/partitions format

import os
import popen2
import string

import systeminfo
from Exceptions import *
import utils
import notify_messages
import BootAPI


def Run(vars, log):
    """
    Make sure the hardware we are running on is sufficient for
    the PlanetLab OS to be installed on. In the process, identify
    the list of block devices that may be used for a node installation,
    and identify the cdrom device that we booted off of.

    Return 1 if requiremenst met, 0 if requirements not met. Raise
    BootManagerException if any problems occur that prevent the requirements
    from being checked.

    Expect the following variables from the store:

    MINIMUM_MEMORY          minimum amount of memory in kb required
                            for install
    NODE_ID                 the node_id from the database for this node
    MINIMUM_DISK_SIZE       any disks smaller than this size, in GB, are not used
    TOTAL_MINIMUM_DISK_SIZE total disk size in GB, if all usable disks
                            meet this number, there isn't enough disk space for
                            this node to be usable after install
    SKIP_HARDWARE_REQUIREMENT_CHECK
                            If set, don't check if minimum requirements are met
    Sets the following variables:
    INSTALL_BLOCK_DEVICES    list of block devices to install onto
    """

    log.write("\n\nStep: Checking if hardware requirements met.\n")        
        
    try:
        MINIMUM_MEMORY = int(vars["MINIMUM_MEMORY"])
        if MINIMUM_MEMORY == "":
            raise ValueError("MINIMUM_MEMORY")

        NODE_ID = vars["NODE_ID"]
        if NODE_ID == "":
            raise ValueError("NODE_ID")

        MINIMUM_DISK_SIZE = int(vars["MINIMUM_DISK_SIZE"])

        # use vs_ or lxc_variants
        varname = vars['virt'] + "_TOTAL_MINIMUM_DISK_SIZE"
        TOTAL_MINIMUM_DISK_SIZE = int(vars[varname])

        SKIP_HARDWARE_REQUIREMENT_CHECK = int(vars["SKIP_HARDWARE_REQUIREMENT_CHECK"])
        
    except KeyError as var:
        raise BootManagerException("Missing variable in install store: {}".format(var))
    except ValueError as var:
        raise BootManagerException("Variable in install store blank, shouldn't be: {}".format(var))

    # lets see if we have enough memory to run
    log.write("Checking for available memory.\n")

    total_mem = systeminfo.get_total_phsyical_mem(vars, log)
    if total_mem is None:
        raise BootManagerException("Unable to read total physical memory")
        
    if total_mem < MINIMUM_MEMORY:
        if not SKIP_HARDWARE_REQUIREMENT_CHECK:
            log.write("Insufficient memory to run node: {} kb\n".format(total_mem))
            log.write("Required memory: {} kb\n".format(MINIMUM_MEMORY))

            include_pis = 0
            include_techs = 1
            include_support = 0
            
            sent = 0
            try:
                sent = BootAPI.call_api_function(vars, "BootNotifyOwners",
                                                 (notify_messages.MSG_INSUFFICIENT_MEMORY,
                                                  include_pis,
                                                  include_techs,
                                                  include_support))
            except BootManagerException as e:
                log.write("Call to BootNotifyOwners failed: {}.\n".format(e))
                
            if sent == 0:
                log.write("Unable to notify site contacts of problem.\n")
            else:
                log.write("Notified contacts of problem.\n")
                
            return 0
        else:
            log.write("Memory requirements not met, but running anyway: {} kb\n"
                      .format(total_mem))
    else:
        log.write("Looks like we have enough memory: {} kb\n".format(total_mem))



    # get a list of block devices to attempt to install on
    # (may include cdrom devices)
    install_devices = systeminfo.get_block_devices_dict(vars, log)

    # save the list of block devices in the log
    log.write("Detected block devices:\n")
    log.write(repr(install_devices) + "\n")

    if not install_devices or len(install_devices) == 0:
        log.write("No block devices detected.\n")
        
        include_pis = 0
        include_techs = 1
        include_support = 0
        
        sent = 0
        try:
            sent = BootAPI.call_api_function(vars, "BootNotifyOwners",
                                             (notify_messages.MSG_INSUFFICIENT_DISK,
                                              include_pis,
                                              include_techs,
                                              include_support))
        except BootManagerException as e:
            log.write("Call to BootNotifyOwners failed: {}.\n".format(e))
            
        if sent == 0:
            log.write("Unable to notify site contacts of problem.\n")

        return 0

    # now, lets remove any block devices we know won't work (readonly,cdroms),
    # or could be other writable removable disks (usb keychains, zip disks, etc)
    # i'm not aware of anything that helps with the latter test, so,
    # what we'll probably do is simply not use any block device below
    # some size threshold (set in installstore)

    # also, keep track of the total size for all devices that appear usable
    total_size = 0

    # do not modify subject of current loop
    ignored_devices = []
    for device, details in install_devices.items():

        major, minor, blocks, gb_size, readonly = details
        
        # if the device string starts with
        # planetlab or dm- (device mapper), ignore it (could be old lvm setup)
        if device[:14] == "/dev/planetlab" or device[:8] == "/dev/dm-":
            ignored_devices.append(device)
            continue

        if gb_size < MINIMUM_DISK_SIZE:
            log.write("Device is too small to use: {} \n"
                      "(appears to be {:4.2f} Gb)\n".format(device, gb_size))
            ignored_devices.append(device)
            continue

        if readonly:
            log.write("Device is readonly, not using: {}\n".format(device))
            ignored_devices.append(device)
            continue
            
        # add this sector count to the total count of usable
        # sectors we've found.
        total_size = total_size + gb_size

    # delayed erasure
    for device in ignored_devices:
        try:
            del install_devices[device]
        except KeyError as e:
            pass

    if len(install_devices) == 0:
        log.write("No suitable block devices found for install.\n")

        include_pis = 0
        include_techs = 1
        include_support = 0
        
        sent = 0
        try:
            sent = BootAPI.call_api_function(vars, "BootNotifyOwners",
                                             (notify_messages.MSG_INSUFFICIENT_DISK,
                                              include_pis,
                                              include_techs,
                                              include_support))
        except BootManagerException as e:
            log.write("Call to BootNotifyOwners failed: {}.\n".format(e))
            
        if sent == 0:
            log.write("Unable to notify site contacts of problem.\n")

        return 0


    # show the devices we found that are usable
    log.write("Usable block devices:\n")
    log.write(repr(install_devices.keys()) + "\n")

    # save the list of devices for the following steps
    vars["INSTALL_BLOCK_DEVICES"] = install_devices.keys()


    # ensure the total disk size is large enough. if
    # not, we need to email the tech contacts the problem, and
    # put the node into debug mode.
    if total_size < TOTAL_MINIMUM_DISK_SIZE:
        if not SKIP_HARDWARE_REQUIREMENT_CHECK:
            log.write("The total usable disk size of all disks is " \
                       "insufficient to be usable as a PlanetLab node.\n")
            include_pis = 0
            include_techs = 1
            include_support = 0
            
            sent = 0
            try:
                sent = BootAPI.call_api_function(vars, "BootNotifyOwners",
                                                 (notify_messages.MSG_INSUFFICIENT_DISK,
                                                  include_pis,
                                                  include_techs,
                                                  include_support))
            except BootManagerException as e:
                log.write("Call to BootNotifyOwners failed: {}.\n".format(e))
            
            if sent == 0:
                log.write("Unable to notify site contacts of problem.\n")

            return 0
        
        else:
            log.write("The total usable disk size of all disks is " \
                       "insufficient, but running anyway.\n")
            
    log.write("Total size for all usable block devices: {:4.2f} Gb\n".format(total_size))

    return 1
