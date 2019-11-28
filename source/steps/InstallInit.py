#!/usr/bin/python2
#
# Copyright (c) 2003 Intel Corporation
# All rights reserved.
#
# Copyright (c) 2004-2006 The Trustees of Princeton University
# All rights reserved.
# expected /proc/partitions format

import os, sys, string

import utils
from Exceptions import *

def Run(vars, log):
    """
    Setup the install environment:
    - unmount anything in the temp/sysimg path (possible from previous
      aborted installs)
    - create temp directories
    
    Expect the following variables from the store:
    TEMP_PATH         the path to download and store temp files to
    SYSIMG_DIR        the directory name of the system image
                      contained in TEMP_PATH
    PLCONF_DIR        The directory to store the configuration file in
    
    Sets the following variables:
    SYSIMG_PATH       the directory where the system image will be mounted,
                      (= TEMP_PATH/SYSIMG_DIR)
    """

    log.write( "\n\nStep: Install: Initializing.\n" )
    
    # make sure we have the variables we need
    try:
        TEMP_PATH = vars["TEMP_PATH"]
        if TEMP_PATH == "":
            raise ValueError("TEMP_PATH")

        SYSIMG_PATH = vars["SYSIMG_PATH"]
        if SYSIMG_PATH == "":
            raise ValueError("SYSIMG_PATH")

        PLCONF_DIR = vars["PLCONF_DIR"]
        if PLCONF_DIR == "":
            raise ValueError("PLCONF_DIR")

    except KeyError as var:
        raise BootManagerException("Missing variable in vars: {}\n".format(var))
    except ValueError as var:
        raise BootManagerException("Variable in vars, shouldn't be: {}\n".format(var))

    # if this is a fresh install, then nothing should be
    # here, but we support restarted installs without rebooting
    # so who knows what the current state is

    log.write("Unmounting any previous mounts\n")

    try:
        # backwards compat, though, we should never hit this case post PL 3.2
        os.stat("{}/rcfs/taskclass".format(SYSIMG_PATH))
        utils.sysexec_chroot_noerr( SYSIMG_PATH, "umount /rcfs", log )
    except OSError, e:
        pass

    # NOTE: added /sys and /dev b/c some nodes fail due to this when disk is
    # nearly full.
    utils.sysexec_noerr("umount {}/proc".format(SYSIMG_PATH), log )
    utils.sysexec_noerr("umount {}/mnt/cdrom".format(SYSIMG_PATH), log )
    utils.sysexec_noerr("umount {}/vservers".format(SYSIMG_PATH), log )
    utils.sysexec_noerr("umount {}/sys".format(SYSIMG_PATH), log )
    utils.sysexec_noerr("umount {}/dev".format(SYSIMG_PATH), log )
    utils.sysexec_noerr("umount {}".format(SYSIMG_PATH), log )
    vars['ROOT_MOUNTED'] = 0

#    log.write( "Removing any old files, directories\n" )
#    utils.removedir(TEMP_PATH)
    
    log.write("Cleaning up any existing PlanetLab config files\n")
    try:
        flist = os.listdir(PLCONF_DIR)
        for file in flist:
            utils.removedir(file)
    except OSError:
        pass
    
    # create the temp path and sysimg path. since sysimg
    # path is in temp path, both are created here
    log.write( "Creating system image path\n" )
    utils.makedirs(SYSIMG_PATH)

    return 1
