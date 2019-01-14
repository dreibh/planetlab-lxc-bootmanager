#
# Copyright (c) 2003 Intel Corporation
# All rights reserved.
#
# Copyright (c) 2004-2006 The Trustees of Princeton University
# All rights reserved.
# expected /proc/partitions format

import os, sys
import string
import popen2
import time

from Exceptions import *
import utils
import BootServerRequest
import BootAPI
import ModelOptions

def Run(vars, log):
    """
    Setup the block devices for install, partition them w/ LVM

    Expect the following variables from the store:
    INSTALL_BLOCK_DEVICES    list of block devices to install onto
    TEMP_PATH                somewhere to store what we need to run
    ROOT_SIZE                the size of the root logical volume
    SWAP_SIZE                the size of the swap partition
    """

    log.write("\n\nStep: Install: partitioning disks.\n")

    # make sure we have the variables we need
    try:
        TEMP_PATH = vars["TEMP_PATH"]
        if TEMP_PATH == "":
            raise ValueError("TEMP_PATH")

        INSTALL_BLOCK_DEVICES = vars["INSTALL_BLOCK_DEVICES"]
        if(len(INSTALL_BLOCK_DEVICES) == 0):
            raise ValueError("INSTALL_BLOCK_DEVICES is empty")

        # use vs_ROOT_SIZE or lxc_ROOT_SIZE as appropriate
        varname = vars['virt'] + "_ROOT_SIZE"
        ROOT_SIZE = vars[varname]
        if ROOT_SIZE == "" or ROOT_SIZE == 0:
            raise ValueError("ROOT_SIZE invalid")

        SWAP_SIZE = vars["SWAP_SIZE"]
        if SWAP_SIZE == "" or SWAP_SIZE == 0:
            raise ValueError("SWAP_SIZE invalid")

        NODE_MODEL_OPTIONS = vars["NODE_MODEL_OPTIONS"]

        PARTITIONS = vars["PARTITIONS"]
        if PARTITIONS == None:
            raise ValueError("PARTITIONS")

        if NODE_MODEL_OPTIONS & ModelOptions.RAWDISK:
            VSERVERS_SIZE = "-1"
            if "VSERVERS_SIZE" in vars:
                VSERVERS_SIZE = vars["VSERVERS_SIZE"]
                if VSERVERS_SIZE == "" or VSERVERS_SIZE == 0:
                    raise ValueError("VSERVERS_SIZE")

    except KeyError as var:
        raise BootManagerException("Missing variable in vars: {}\n".format(var))
    except ValueError as var:
        raise BootManagerException("Variable in vars, shouldn't be: {}\n".format(var))

    bs_request = BootServerRequest.BootServerRequest(vars)


    # disable swap if its on
    utils.sysexec_noerr("swapoff {}".format(PARTITIONS["swap"]), log)

    # shutdown and remove any lvm groups/volumes
    utils.sysexec_noerr("vgscan", log)
    utils.sysexec_noerr("vgchange -ay", log)
    utils.sysexec_noerr("lvremove -f {}".format(PARTITIONS["root"]), log)
    utils.sysexec_noerr("lvremove -f {}".format(PARTITIONS["swap"]), log)
    utils.sysexec_noerr("lvremove -f {}".format(PARTITIONS["vservers"]), log)
    utils.sysexec_noerr("vgchange -an", log)
    utils.sysexec_noerr("vgremove -f planetlab", log)

    log.write("Running vgscan for devices\n")
    utils.sysexec_noerr("vgscan", log)

    used_devices = []

    INSTALL_BLOCK_DEVICES.sort()

    for device in INSTALL_BLOCK_DEVICES:
        if single_partition_device(device, vars, log):
            if (len(used_devices) > 0 and
                (vars['NODE_MODEL_OPTIONS'] & ModelOptions.RAWDISK)):
                log.write("Running in raw disk mode, not using {}.\n".format(device))
            else:
                used_devices.append(device)
                log.write("Successfully initialized {}\n".format(device))
        else:
            log.write("Unable to partition {}, not using it.\n".format(device))
            continue

    # list of devices to be used with vgcreate
    vg_device_list = ""

    # get partitions
    partitions = []
    for device in used_devices:
        part_path = get_partition_path_from_device(device, vars, log)
        partitions.append(part_path)

    # create raid partition
    raid_partition = create_raid_partition(partitions, vars, log)
    if raid_partition != None:
        partitions = [raid_partition]
    log.write("partitions={}\n".format(partitions))
    # initialize the physical volumes
    for part_path in partitions:
        if not create_lvm_physical_volume(part_path, vars, log):
            raise BootManagerException("Could not create lvm physical volume "
                                       "on partition {}".format(part_path))
        vg_device_list = vg_device_list + " " + part_path

    # create an lvm volume group
    utils.sysexec("vgcreate -s32M planetlab {}".format(vg_device_list), log)

    # create swap logical volume
    utils.sysexec("lvcreate -L{} -nswap planetlab".format(SWAP_SIZE), log)

    # check if we want a separate partition for VMs
    one_partition = vars['ONE_PARTITION']=='1'
    if one_partition:
        remaining_extents = get_remaining_extents_on_vg(vars, log)
        utils.sysexec("lvcreate -l{} -nroot planetlab".format(remaining_extents), log)
    else:
        utils.sysexec("lvcreate -L{} -nroot planetlab".format(ROOT_SIZE), log)
        if vars['NODE_MODEL_OPTIONS'] & ModelOptions.RAWDISK and VSERVERS_SIZE != "-1":
            utils.sysexec("lvcreate -L{} -nvservers planetlab".format(VSERVERS_SIZE), log)
            remaining_extents = get_remaining_extents_on_vg(vars, log)
            utils.sysexec("lvcreate -l{} -nrawdisk planetlab".format(remaining_extents), log)
        else:
            # create vservers logical volume with all remaining space
            # first, we need to get the number of remaining extents we can use
            remaining_extents = get_remaining_extents_on_vg(vars, log)
            utils.sysexec("lvcreate -l{} -nvservers planetlab".format(remaining_extents), log)

    # activate volume group (should already be active)
    #utils.sysexec(TEMP_PATH + "vgchange -ay planetlab", log)

    # make swap
    utils.sysexec("mkswap -f {}".format(PARTITIONS["swap"]), log)

    # check if badhd option has been set
    option = ''
    txt = ''
    if NODE_MODEL_OPTIONS & ModelOptions.BADHD:
        option = '-c'
        txt = " with bad block search enabled, which may take a while"

    # filesystems partitions names and their corresponding
    # reserved-blocks-percentages
    filesystems = {"root": 5, "vservers": 0}

    # ROOT filesystem is always with ext2
    fs = 'root'
    rbp = filesystems[fs]
    devname = PARTITIONS[fs]
    log.write("formatting {} partition ({}){}.\n".format(fs, devname, txt))
    utils.sysexec("mkfs.ext2 -q {} -m {} -j {}".format(option, rbp, devname), log)
    # disable time/count based filesystems checks
    utils.sysexec_noerr("tune2fs -c -1 -i 0 {}".format(devname), log)

    # VSERVER filesystem with btrfs to support snapshoting and stuff
    fs = 'vservers'
    rbp = filesystems[fs]
    devname = PARTITIONS[fs]
    if vars['virt'] == 'vs':
        log.write("formatting {} partition ({}){}.\n".format(fs, devname, txt))
        utils.sysexec("mkfs.ext2 -q {} -m {} -j {}".format(option, rbp, devname), log)
        # disable time/count based filesystems checks
        utils.sysexec_noerr("tune2fs -c -1 -i 0 {}".format(devname), log)
    elif not one_partition:
        log.write("formatting {} btrfs partition ({}).\n".format(fs, devname))
        # early BootCD's seem to come with a version of mkfs.btrfs that does not support -f
        # let's check for that before invoking it
        mkfs = "mkfs.btrfs"
        if os.system("mkfs.btrfs --help 2>&1 | grep force") == 0:
            mkfs += " -f"
        mkfs += " {}".format(devname)
        utils.sysexec(mkfs, log)
        # as of 2013/02 it looks like there's not yet an option to set fsck frequency with btrfs

    # save the list of block devices in the log
    log.write("Block devices used (in lvm): {}\n".format(repr(used_devices)))

    # list of block devices used may be updated
    vars["INSTALL_BLOCK_DEVICES"] = used_devices

    utils.display_disks_status(PARTITIONS, "End of InstallPartitionDisks", log)

    return 1


import parted
def single_partition_device(device, vars, log):
    """
    initialize a disk by removing the old partition tables,
    and creating a new single partition that fills the disk.

    return 1 if sucessful, 0 otherwise
    """

    # two forms, depending on which version of pyparted we have
    # v1 does not have a 'version' method
    # v2 and above does, but to make it worse,
    # parted-3.4 on f14 has parted.version broken and raises SystemError
    try:
        parted.version()
        return single_partition_device_2_x(device, vars, log)
    except AttributeError:
        # old parted does not have version at all
        return single_partition_device_1_x(device, vars, log)
    except SystemError:
        # let's assume this is >=2
        return single_partition_device_2_x(device, vars, log)
    except:
        raise

def single_partition_device_1_x(device, vars, log):

    lvm_flag = parted.partition_flag_get_by_name('lvm')

    try:
        log.write("Using pyparted 1.x\n")
        # wipe the old partition table
        utils.sysexec("dd if=/dev/zero of={} bs=512 count=1".format(device), log)

        # get the device
        dev = parted.PedDevice.get(device)

        # create a new partition table
        disk = dev.disk_new_fresh(parted.disk_type_get("msdos"))

        # create one big partition on each block device
        constraint = dev.constraint_any()

        new_part = disk.partition_new(
            parted.PARTITION_PRIMARY,
            parted.file_system_type_get("ext2"),
            0, 1)

        # make it an lvm partition
        new_part.set_flag(lvm_flag, 1)

        # actually add the partition to the disk
        disk.add_partition(new_part, constraint)

        disk.maximize_partition(new_part,constraint)

        disk.commit()
        del disk

    except BootManagerException as exc:
        log.write("BootManagerException while running: {}\n".format(str(exc)))
        return 0

    except parted.error as exc:
        log.write("parted exception while running: {}\n".format(str(exc)))
        return 0

    return 1



def single_partition_device_2_x(device, vars, log):
    try:
        log.write("Using pyparted 2.x\n")

        # Thierry june 2012 -- for disks larger than 2TB
        # calling this with part_type='msdos' would fail at the maximizePartition stage
        # create a new partition table
        def partition_table(device, part_type, fs_type):
            # wipe the old partition table
            utils.sysexec("dd if=/dev/zero of={} bs=512 count=1".format(device), log)
            # get the device
            dev = parted.Device(device)
            disk = parted.freshDisk(dev, part_type)
            # create one big partition on each block device
            constraint = parted.constraint.Constraint(device=dev)
            geometry = parted.geometry.Geometry(device=dev, start=0, end=1)
            fs = parted.filesystem.FileSystem(type=fs_type, geometry=geometry)
            new_part = parted.partition.Partition(disk, type=parted.PARTITION_NORMAL,
                                                  fs=fs, geometry=geometry)
            # make it an lvm partition
            new_part.setFlag(parted.PARTITION_LVM)
            # actually add the partition to the disk
            disk.addPartition(new_part, constraint)
            disk.maximizePartition(new_part, constraint)
            disk.commit()
            log.write("Current disk for {} - partition type {}\n{}\n".format(device, part_type, disk))
            log.write("Current dev for {}\n{}\n".format(device, dev))
            del disk

        try:
            partition_table(device, 'msdos', 'ext2')
        except:
            partition_table(device, 'gpt', 'ext2')

    except Exception as e:
        log.write("Exception inside single_partition_device_2_x : {}\n".format(str(e)))
        import traceback
        traceback.print_exc(file=log)
        return 0

    return 1



def create_lvm_physical_volume(part_path, vars, log):
    """
    make the specificed partition a lvm physical volume.

    return 1 if successful, 0 otherwise.
    """

    try:
        # again, wipe any old data, this time on the partition
        utils.sysexec("dd if=/dev/zero of={} bs=512 count=1".format(part_path), log)
        ### patch Thierry Parmentelat, required on some hardware
        import time
        time.sleep(1)
        utils.sysexec("pvcreate -ffy {}".format(part_path), log)
    except BootManagerException as e:
        log.write("create_lvm_physical_volume failed.\n")
        return 0

    return 1


def create_raid_partition(partitions, vars, log):
    """
    create raid array using specified partitions.
    """
    raid_part = None
    raid_enabled = False
    node_tags = BootAPI.call_api_function(vars, "GetNodeTags",
                                          ({'node_id': vars['NODE_ID']},))
    for node_tag in node_tags:
        if node_tag['tagname'] == 'raid_enabled' and \
           node_tag['value'] == '1':
            raid_enabled = True
            break
    if not raid_enabled:
        return raid_part

    try:
        log.write("Software raid enabled.\n")
        # wipe everything
        utils.sysexec_noerr("mdadm --stop /dev/md0", log)
        time.sleep(1)
        for part_path in partitions:
            utils.sysexec_noerr("mdadm --zero-superblock {} ".format(part_path), log)

        # assume each partiton is on a separate disk
        num_parts = len(partitions)
        if num_parts < 2:
            log.write("Not enough disks for raid. Found: {}\n".format(partitions))
            raise BootManagerException("Not enough disks for raid. Found: {}\n".format(partitions))
        if num_parts == 2:
            lvl = 1
        else:
            lvl = 5

        # make the array
        part_list = " ".join(partitions)
        raid_part = "/dev/md0"
        cmd = "mdadm --create {raid_part} --chunk=128 --level=raid{lvl} "\
              "--raid-devices={num_parts} {part_list}".format(**locals())
        utils.sysexec(cmd, log)

    except BootManagerException as e:
        log.write("create_raid_partition failed.\n")
        raid_part = None

    return raid_part


def get_partition_path_from_device(device, vars, log):
    """
    given a device, return the path of the first partition on the device
    """

    # those who wrote the cciss driver just had to make it difficult
    cciss_test = "/dev/cciss"
    if device[:len(cciss_test)] == cciss_test:
        part_path = device + "p1"
    else:
        part_path = device + "1"

    return part_path



def get_remaining_extents_on_vg(vars, log):
    """
    return the free amount of extents on the planetlab volume group
    """

    c_stdout, c_stdin = popen2.popen2("vgdisplay -c planetlab")
    result = string.strip(c_stdout.readline())
    c_stdout.close()
    c_stdin.close()
    remaining_extents = string.split(result, ":")[15]

    return remaining_extents
