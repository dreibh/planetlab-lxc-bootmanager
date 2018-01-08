#!/usr/bin/python
#
# Copyright (c) 2003 Intel Corporation
# All rights reserved.
#
# Copyright (c) 2004-2007 The Trustees of Princeton University
# All rights reserved.
# expected /proc/partitions format

import os, string
import popen2
import shutil
import traceback 
import time

from Exceptions import *
import utils
import systeminfo
import BootServerRequest
import BootAPI


def Run(vars, upgrade, log):
    """
    Download core + extensions bootstrapfs tarballs and install on the hard drive

    the upgrade boolean is True when we are upgrading a node root install while 
    preserving its slice contents; in that case we just perform extra cleanup
    before unwrapping the bootstrapfs
    this is because the running system may have extraneous files
    that is to say, files that are *not* present in the bootstrapfs
    and that can impact/clobber the resulting upgrade
    
    Expect the following variables from the store:
    SYSIMG_PATH          the path where the system image will be mounted
    PARTITIONS           dictionary of generic part. types (root/swap)
                         and their associated devices.
    NODE_ID              the id of this machine
    
    Sets the following variables:
    TEMP_BOOTCD_PATH     where the boot cd is remounted in the temp
                         path
    ROOT_MOUNTED         set to 1 when the the base logical volumes
                         are mounted.
    """

    log.write("\n\nStep: Install: bootstrapfs tarball (upgrade={}).\n".format(upgrade))

    # make sure we have the variables we need
    try:
        SYSIMG_PATH = vars["SYSIMG_PATH"]
        if SYSIMG_PATH == "":
            raise ValueError("SYSIMG_PATH")

        PARTITIONS = vars["PARTITIONS"]
        if PARTITIONS == None:
            raise ValueError("PARTITIONS")

        NODE_ID = vars["NODE_ID"]
        if NODE_ID == "":
            raise ValueError("NODE_ID")

        VERSION = vars['VERSION'] or 'unknown'

    except KeyError as var:
        raise BootManagerException("Missing variable in vars: {}\n".format(var))
    except ValueError as var:
        raise BootManagerException("Variable in vars, shouldn't be: {}\n".format(var))


    try:
        # make sure the required partitions exist
        val = PARTITIONS["root"]
        val = PARTITIONS["swap"]
        val = PARTITIONS["vservers"]
    except KeyError as part:
        log.write("Missing partition in PARTITIONS: {}\n".format(part))
        return 0   

    bs_request = BootServerRequest.BootServerRequest(vars)
    
    # in upgrade mode, since we skip InstallPartitionDisks
    # we need to run this
    if upgrade:
        log.write("Upgrade mode init : Scanning for devices\n")
        systeminfo.get_block_devices_dict(vars, log)
        utils.sysexec_noerr("vgscan --mknodes", log)
        utils.sysexec_noerr("vgchange -ay", log)

    # debugging info - show in either mode
    utils.display_disks_status(PARTITIONS, "In InstallBootstrapFS", log)

    utils.breakpoint("we need to make /dev/mapper/* appear")

    log.write("turning on swap space\n")
    utils.sysexec("swapon {}".format(PARTITIONS["swap"]), log)

    # make sure the sysimg dir is present
    utils.makedirs(SYSIMG_PATH)

    log.write("mounting root file system\n")
    utils.sysexec("mount -t ext3 {} {}".format(PARTITIONS["root"], SYSIMG_PATH), log)

    fstype = 'ext3' if vars['virt']=='vs' else 'btrfs'

    one_partition = vars['ONE_PARTITION']=='1'

    if (not one_partition):
        log.write("mounting vserver partition in root file system (type {})\n".format(fstype))
        utils.makedirs(SYSIMG_PATH + "/vservers")
        utils.sysexec("mount -t {} {} {}/vservers"\
                      .format(fstype, PARTITIONS["vservers"], SYSIMG_PATH), log)

        #if vars['virt']=='lxc':
            # NOTE: btrfs quota is supported from version: >= btrfs-progs-0.20 (f18+)
            #       older versions will not recongize the 'quota' command.
            #log.write("Enabling btrfs quota on {}/vservers\n".format(SYSIMG_PATH))
            #utils.sysexec_noerr("btrfs quota enable {}/vservers".format(SYSIMG_PATH))

    vars['ROOT_MOUNTED'] = 1

    # this is now retrieved in GetAndUpdateNodeDetails
    nodefamily = vars['nodefamily']
    extensions = vars['extensions']

    # in upgrade mode: we need to cleanup the disk to make
    # it safe to just untar the new bootstrapfs tarball again
    # on top of the hard drive
    if upgrade:
        CleanupSysimgBeforeUpgrade(SYSIMG_PATH, nodefamily, log)

    # the 'plain' option is for tests mostly
    plain = vars['plain']
    if plain:
        download_suffix = ".tar"
        uncompress_option = ""
        log.write("Using plain bootstrapfs images\n")
    else:
        download_suffix = ".tar.bz2"
        uncompress_option = "-j"
        log.write("Using compressed bootstrapfs images\n")

    log.write ("Using nodefamily={}\n".format(nodefamily))
    if not extensions:
        log.write("Installing only core software\n")
    else:
        log.write("Requested extensions {}\n".format(extensions))
    
    bootstrapfs_names = [ nodefamily ] + extensions

    for name in bootstrapfs_names:
        tarball = "bootstrapfs-{}{}".format(name, download_suffix)
        source_file = "/boot/{}".format(tarball)
        dest_file = "{}/{}".format(SYSIMG_PATH, tarball)

        source_hash_file = "/boot/{}.sha1sum".format(tarball)
        dest_hash_file = "{}/{}.sha1sum".format(SYSIMG_PATH, tarball)

        time_beg = time.time()
        log.write("downloading {}\n".format(source_file))
        # 120 is the connect timeout, 86400 is the max transfer time in
        # seconds (1 day)
        result = bs_request.DownloadFile(source_file, None, None,
                                         1, 1, dest_file,
                                         120, 86400)
        time_end = time.time()
        duration = int(time_end - time_beg)
        log.write("Done downloading ({} seconds)\n".format(duration))
        if result:
            # Download SHA1 checksum file
            log.write("downloading sha1sum for {}\n".format(source_file))
            result = bs_request.DownloadFile(source_hash_file, None, None,
                                             1, 1, dest_hash_file,
                                             120, 86400)
 
            log.write("verifying sha1sum for {}\n".format(source_file))
            if not utils.check_file_hash(dest_file, dest_hash_file):
                raise BootManagerException(
                    "FATAL: SHA1 checksum does not match between {} and {}"\
                    .format(source_file, source_hash_file))
                
            
            time_beg = time.time()
            log.write("extracting {} in {}\n".format(dest_file, SYSIMG_PATH))
            result = utils.sysexec("tar -C {} -xpf {} {}".format(SYSIMG_PATH, dest_file, uncompress_option), log)
            time_end = time.time()
            duration = int(time_end - time_beg)
            log.write("Done extracting ({} seconds)\n".format(duration))
            utils.removefile(dest_file)
        else:
            # the main tarball is required
            if name == nodefamily:
                raise BootManagerException(
                    "FATAL: Unable to download main tarball {} from server."\
                    .format(source_file))
            # for extensions, just issue a warning
            else:
                log.write("WARNING: tarball for extension {} not found\n".format(name))

    # copy resolv.conf from the base system into our temp dir
    # so DNS lookups work correctly while we are chrooted
    log.write("Copying resolv.conf to temp dir\n")
    utils.sysexec("cp /etc/resolv.conf {}/etc/".format(SYSIMG_PATH), log)

    # Copy the boot server certificate(s) and GPG public key to
    # /usr/boot in the temp dir.
    log.write("Copying boot server certificates and public key\n")

    if os.path.exists("/usr/boot"):
        # do nothing in case of upgrade
        if not os.path.exists(SYSIMG_PATH + "/usr/boot"):
            utils.makedirs(SYSIMG_PATH + "/usr")
            shutil.copytree("/usr/boot", SYSIMG_PATH + "/usr/boot")
    elif os.path.exists("/usr/bootme"):
        # do nothing in case of upgrade
        if not os.path.exists(SYSIMG_PATH + "/usr/bootme"):
            utils.makedirs(SYSIMG_PATH + "/usr/boot")
            boot_server = file("/usr/bootme/BOOTSERVER").readline().strip()
            shutil.copy("/usr/bootme/cacert/" + boot_server + "/cacert.pem",
                        SYSIMG_PATH + "/usr/boot/cacert.pem")
            file(SYSIMG_PATH + "/usr/boot/boot_server", "w").write(boot_server)
            shutil.copy("/usr/bootme/pubring.gpg", SYSIMG_PATH + "/usr/boot/pubring.gpg")
        
    # For backward compatibility
    if os.path.exists("/usr/bootme"):
        # do nothing in case of upgrade
        if not os.path.exists(SYSIMG_PATH + "/mnt/cdrom/bootme"):
            utils.makedirs(SYSIMG_PATH + "/mnt/cdrom")
            shutil.copytree("/usr/bootme", SYSIMG_PATH + "/mnt/cdrom/bootme")

    # ONE_PARTITION => new distribution type
    if (vars['ONE_PARTITION'] != '1'):
        # Import the GPG key into the RPM database so that RPMS can be verified
        utils.makedirs(SYSIMG_PATH + "/etc/pki/rpm-gpg")
        utils.sysexec("gpg --homedir=/root --export --armor"
                      " --no-default-keyring --keyring {}/usr/boot/pubring.gpg"
                      " > {}/etc/pki/rpm-gpg/RPM-GPG-KEY-planetlab".format(SYSIMG_PATH, SYSIMG_PATH), log)
        utils.sysexec_chroot(SYSIMG_PATH, "rpm --import /etc/pki/rpm-gpg/RPM-GPG-KEY-planetlab", log)

    # keep a log on the installed hdd
    stamp = file(SYSIMG_PATH + "/bm-install.txt", 'a')
    now = time.strftime("%Y-%b-%d @ %H:%M %Z", time.gmtime())
    stamp.write("Hard drive installed by BootManager {}\n".format(VERSION))
    stamp.write("Finished extraction of bootstrapfs on {}\n".format(now))
    # do not modify this, the upgrade code uses this line for checking compatibility
    stamp.write("Using nodefamily {}\n".format(nodefamily))
    stamp.close()

    return 1

# the upgrade hook
def CleanupSysimgBeforeUpgrade(sysimg, target_nodefamily, log):

    areas_to_cleanup = [
        '/boot',
        '/usr',
        '/var',
        '/etc',
        '/run',
        '/vsys',
    ]

    target_pldistro, target_fcdistro, target_arch = target_nodefamily.split('-')

    # minimal check : not all configurations are possible...

    installed_pldistro, installed_fcdistro, installed_arch = None, None, None
    installed_virt = None
    prefix = "Using nodefamily "
    try:
        with open("{}/bm-install.txt".format(sysimg)) as infile:
            for line in infile:
                if line.startswith(prefix):
                    installed_nodefamily = line.replace(prefix,"").strip()
                    installed_pldistro, installed_fcdistro, installed_arch = installed_nodefamily.split('-')
                    # do not break here, bm-install is additive, we want the last one..
        with open("{}/etc/planetlab/virt".format(sysimg)) as infile:
            installed_virt = infile.read().strip()
    except Exception as e:
        traceback.print_exc()
        raise BootManagerException("Could not retrieve data about previous installation - cannot upgrade")

    # moving from vservers to lxc also means another filesystem
    # so plain reinstall is the only option
    if installed_virt != 'lxc':
        message = """Can only upgrade nodes already running lxc containers
a node running vservers has its /vservers/ partition formatted as ext3 
and we need btrfs to move to containers
your only option here is reinstall"""
        raise BootManagerException(message)

    # changing arch is not reasonable either
    if target_arch != installed_arch:
        raise BootManagerException("Cannot upgrade from arch={} to arch={}"
                                   .format(installed_arch, target_arch))

    if target_pldistro != installed_pldistro:
        log.write("\nWARNING: upgrading across pldistros {} to {} - might not work well..\n"
                  .format(installed_pldistro, target_pldistro))
    
    # otherwise at this point we do not do any more advanced checking
    log.write("\n\nPseudo step CleanupSysimgBeforeUpgrade : cleaning up hard drive\n")
    
    for area in areas_to_cleanup:
        utils.sysexec("rm -rf {}/{}".format(sysimg, area))
