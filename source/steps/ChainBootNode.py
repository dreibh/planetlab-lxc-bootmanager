#!/usr/bin/python
#
# Copyright (c) 2003 Intel Corporation
# All rights reserved.
#
# Copyright (c) 2004-2006 The Trustees of Princeton University
# All rights reserved.


import string
import re
import os
import time

import utils
import systeminfo
import notify_messages
import BootAPI
import ModelOptions
from Exceptions import BootManagerException

import UpdateNodeConfiguration
import StopRunlevelAgent
import MakeInitrd

def Run( vars, log ):
    """
    Load the kernel off of a node and boot to it.
    This step assumes the disks are mounted on SYSIMG_PATH.
    If successful, this function will not return. If it returns, no chain
    booting has occurred.
    
    Expect the following variables:
    SYSIMG_PATH           the path where the system image will be mounted
                          (always starts with TEMP_PATH)
    ROOT_MOUNTED          the node root file system is mounted
    NODE_SESSION             the unique session val set when we requested
                             the current boot state
    PLCONF_DIR               The directory to store PL configuration files in
    
    Sets the following variables:
    ROOT_MOUNTED          the node root file system is mounted
    """

    log.write( "\n\nStep: Chain booting node.\n" )

    # make sure we have the variables we need
    try:
        SYSIMG_PATH= vars["SYSIMG_PATH"]
        if SYSIMG_PATH == "":
            raise ValueError, "SYSIMG_PATH"

        PLCONF_DIR= vars["PLCONF_DIR"]
        if PLCONF_DIR == "":
            raise ValueError, "PLCONF_DIR"

        # its ok if this is blank
        NODE_SESSION= vars["NODE_SESSION"]

        NODE_MODEL_OPTIONS= vars["NODE_MODEL_OPTIONS"]

        PARTITIONS= vars["PARTITIONS"]
        if PARTITIONS == None:
            raise ValueError, "PARTITIONS"

    except KeyError, var:
        raise BootManagerException, "Missing variable in vars: %s\n" % var
    except ValueError, var:
        raise BootManagerException, "Variable in vars, shouldn't be: %s\n" % var

    ROOT_MOUNTED= 0
    if vars.has_key('ROOT_MOUNTED'):
        ROOT_MOUNTED= vars['ROOT_MOUNTED']
    
    if ROOT_MOUNTED == 0:
        log.write( "Mounting node partitions\n" )

        # simply creating an instance of this class and listing the system
        # block devices will make them show up so vgscan can find the planetlab
        # volume group
        systeminfo.get_block_device_list(vars, log)
        
        utils.sysexec( "vgscan", log )
        utils.sysexec( "vgchange -ay planetlab", log )

        utils.makedirs( SYSIMG_PATH )

        cmd = "mount %s %s" % (PARTITIONS["root"],SYSIMG_PATH)
        utils.sysexec( cmd, log )
        cmd = "mount -t proc none %s/proc" % SYSIMG_PATH
        utils.sysexec( cmd, log )
        cmd = "mount %s %s/vservers" % (PARTITIONS["vservers"],SYSIMG_PATH)
        utils.sysexec( cmd, log )

        ROOT_MOUNTED= 1
        vars['ROOT_MOUNTED']= 1
        

    # write out the session value /etc/planetlab/session
    try:
        session_file_path= "%s/%s/session" % (SYSIMG_PATH,PLCONF_DIR)
        session_file= file( session_file_path, "w" )
        session_file.write( str(NODE_SESSION) )
        session_file.close()
        session_file= None
        log.write( "Updated /etc/planetlab/session\n" )
    except IOError, e:
        log.write( "Unable to write out /etc/planetlab/session, continuing anyway\n" )

    # update configuration files
    log.write( "Updating configuration files.\n" )
    # avoid using conf_files initscript as we're moving to systemd on some platforms

    if (vars['ONE_PARTITION']!='1'):
        try:
            cmd = "/usr/bin/env python /usr/share/NodeManager/conf_files.py --noscripts"
            utils.sysexec_chroot( SYSIMG_PATH, cmd, log )
        except IOError, e:
            log.write("conf_files failed with \n %s" % e)

        # update node packages
        log.write( "Running node update.\n" )
        if os.path.exists( SYSIMG_PATH + "/usr/bin/NodeUpdate.py" ):
            cmd = "/usr/bin/NodeUpdate.py start noreboot"
        else:
            # for backwards compatibility
            cmd = "/usr/local/planetlab/bin/NodeUpdate.py start noreboot"
        utils.sysexec_chroot( SYSIMG_PATH, cmd, log )

    # Re-generate initrd right before kexec call
    # this is not required anymore on recent depls.
    if vars['virt'] == 'vs':
        MakeInitrd.Run( vars, log )

    # the following step should be done by NM
    UpdateNodeConfiguration.Run( vars, log )

    log.write( "Updating ssh public host key with PLC.\n" )
    ssh_host_key= ""
    try:
        ssh_host_key_file= file("%s/etc/ssh/ssh_host_rsa_key.pub"%SYSIMG_PATH,"r")
        ssh_host_key= ssh_host_key_file.read().strip()
        ssh_host_key_file.close()
        ssh_host_key_file= None
    except IOError, e:
        pass

    update_vals= {}
    update_vals['ssh_rsa_key']= ssh_host_key
    BootAPI.call_api_function( vars, "BootUpdateNode", (update_vals,) )


    # get the kernel version
    option = ''
    if NODE_MODEL_OPTIONS & ModelOptions.SMP:
        option = 'smp'

    log.write( "Copying kernel and initrd for booting.\n" )
    if vars['virt'] == 'vs':
        utils.sysexec( "cp %s/boot/kernel-boot%s /tmp/kernel" % (SYSIMG_PATH,option), log )
        utils.sysexec( "cp %s/boot/initrd-boot%s /tmp/initrd" % (SYSIMG_PATH,option), log )
    else:
        # Use chroot to call rpm, b/c the bootimage&nodeimage rpm-versions may not work together
        try:
            kversion = os.popen("chroot %s rpm -qa kernel | tail -1 | cut -c 8-" % SYSIMG_PATH).read().rstrip()
            major_version = int(kversion[0]) # Check if the string looks like a kernel version
        except:
            # Try a different method for non-rpm-based distributions
            kversion = os.popen("ls -lrt %s/lib/modules | tail -1 | awk '{print $9;}'"%SYSIMG_PATH).read().rstrip()

        utils.sysexec( "cp %s/boot/vmlinuz-%s /tmp/kernel" % (SYSIMG_PATH,kversion), log )
        candidates=[]
        # f16/18: expect initramfs image here
        candidates.append ("/boot/initramfs-%s.img"%(kversion))
        # f20: uses a uid of some kind, e.g. /boot/543f88c129de443baaa65800cf3927ce/<kversion>/initrd
        candidates.append ("/boot/*/%s/initrd"%(kversion))
        # Ubuntu:
        candidates.append ("/boot/initrd.img-%s"%(kversion))
        def find_file_in_sysimg (candidates):
            import glob
            for pattern in candidates:
                matches=glob.glob(SYSIMG_PATH+pattern)
                log.write("locating initrd: found %d matches in %s\n"%(len(matches),pattern))
                if matches: return matches[0]
        initrd=find_file_in_sysimg(candidates)
        if initrd:
            utils.sysexec( "cp %s /tmp/initrd" % initrd, log )
        else:
            raise Exception,"Unable to locate initrd - bailing out"

    BootAPI.save(vars)

    log.write( "Unmounting disks.\n" )
    utils.sysexec( "umount %s/vservers" % SYSIMG_PATH, log )
    utils.sysexec( "umount %s/proc" % SYSIMG_PATH, log )
    utils.sysexec_noerr( "umount %s/dev" % SYSIMG_PATH, log )
    utils.sysexec_noerr( "umount %s/sys" % SYSIMG_PATH, log )
    utils.sysexec( "umount %s" % SYSIMG_PATH, log )
    utils.sysexec( "vgchange -an", log )

    ROOT_MOUNTED= 0
    vars['ROOT_MOUNTED']= 0

    # Change runlevel to 'boot' prior to kexec.
    StopRunlevelAgent.Run( vars, log )

    log.write( "Unloading modules and chain booting to new kernel.\n" )

    # further use of log after Upload will only output to screen
    log.Upload("/root/.bash_eternal_history")

    # regardless of whether kexec works or not, we need to stop trying to
    # run anything
    cancel_boot_flag= "/tmp/CANCEL_BOOT"
    utils.sysexec( "touch %s" % cancel_boot_flag, log )

    # on 2.x cds (2.4 kernel) for sure, we need to shutdown everything
    # to get kexec to work correctly. Even on 3.x cds (2.6 kernel),
    # there are a few buggy drivers that don't disable their hardware
    # correctly unless they are first unloaded.
    
    utils.sysexec_noerr( "ifconfig eth0 down", log )

    utils.sysexec_noerr( "killall dhclient", log )
        
    if vars['virt'] == 'vs':
        utils.sysexec_noerr( "umount -a -r -t ext2,ext3", log )
    else:
        utils.sysexec_noerr( "umount -a -r -t ext2,ext3,btrfs", log )
    utils.sysexec_noerr( "modprobe -r lvm-mod", log )
    
    # modules that should not get unloaded
    # unloading cpqphp causes a kernel panic
    blacklist = [ "floppy", "cpqphp", "i82875p_edac", "mptspi"]
    try:
        modules= file("/tmp/loadedmodules","r")
        
        for line in modules:
            module= string.strip(line)
            if module in blacklist :
                log.write("Skipping unload of kernel module '%s'.\n"%module)
            elif module != "":
                log.write( "Unloading %s\n" % module )
                utils.sysexec_noerr( "modprobe -r %s" % module, log )
                if "e1000" in module:
                    log.write("Unloading e1000 driver; sleeping 4 seconds...\n")
                    time.sleep(4)

        modules.close()
    except IOError:
        log.write( "Couldn't read /tmp/loadedmodules, continuing.\n" )

    try:
        modules= file("/proc/modules", "r")

        # Get usage count for USB
        usb_usage = 0
        for line in modules:
            try:
                # Module Size UsageCount UsedBy State LoadAddress
                parts= string.split(line)

                if parts[0] == "usb_storage":
                    usb_usage += int(parts[2])
            except IndexError, e:
                log.write( "Couldn't parse /proc/modules, continuing.\n" )

        modules.seek(0)

        for line in modules:
            try:
                # Module Size UsageCount UsedBy State LoadAddress
                parts= string.split(line)

                # While we would like to remove all "unused" modules,
                # you can't trust usage count, especially for things
                # like network drivers or RAID array drivers. Just try
                # and unload a few specific modules that we know cause
                # problems during chain boot, such as USB host
                # controller drivers (HCDs) (PL6577).
                # if int(parts[2]) == 0:
                if False and re.search('_hcd$', parts[0]):
                    if usb_usage > 0:
                        log.write( "NOT unloading %s since USB may be in use\n" % parts[0] )
                    else:
                        log.write( "Unloading %s\n" % parts[0] )
                        utils.sysexec_noerr( "modprobe -r %s" % parts[0], log )
            except IndexError, e:
                log.write( "Couldn't parse /proc/modules, continuing.\n" )
    except IOError:
        log.write( "Couldn't read /proc/modules, continuing.\n" )


    kargs = "root=%s ramdisk_size=8192" % PARTITIONS["mapper-root"]
    if NODE_MODEL_OPTIONS & ModelOptions.SMP:
        kargs = kargs + " " + "acpi=off"
    try:
        kargsfb = open("/kargs.txt","r")
        moreargs = kargsfb.readline()
        kargsfb.close()
        moreargs = moreargs.strip()
        log.write( 'Parsed in "%s" kexec args from /kargs.txt\n' % moreargs )
        kargs = kargs + " " + moreargs
    except IOError:
        # /kargs.txt does not exist, which is fine. Just kexec with default
        # kargs, which is ramdisk_size=8192
        pass 

    utils.sysexec_noerr( 'hwclock --systohc --utc ', log )
    utils.breakpoint ("Before kexec");
    try:
        utils.sysexec( 'kexec --force --initrd=/tmp/initrd --append="%s" /tmp/kernel' % kargs, log)
    except BootManagerException, e:
        # if kexec fails, we've shut the machine down to a point where nothing
        # can run usefully anymore (network down, all modules unloaded, file
        # systems unmounted. write out the error, and cancel the boot process

        log.write( "\n\n" )
        log.write( "-------------------------------------------------------\n" )
        log.write( "kexec failed with the following error. Please report\n" )
        log.write( "this problem to support@planet-lab.org.\n\n" )
        log.write( str(e) + "\n\n" )
        log.write( "The boot process has been canceled.\n" )
        log.write( "-------------------------------------------------------\n\n" )

    return
