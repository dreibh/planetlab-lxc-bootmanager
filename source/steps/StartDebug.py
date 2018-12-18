#!/usr/bin/python
#
# Copyright (c) 2003 Intel Corporation
# All rights reserved.
#
# Copyright (c) 2004-2006 The Trustees of Princeton University
# All rights reserved.

from __future__ import print_function

import os

from Exceptions import *
import utils


warning_message = \
"""
---------------------------------------------------------
This machine has entered a temporary debug state, so
Planetlab Support can login and fix any problems that
might have occurred.

Please do not reboot this machine at this point, unless
specifically asked to.

Thank you.
---------------------------------------------------------
"""

# this can be invoked 
# either at the end of the bm logic, because something failed (last_resort = True)
# and/or it can be invoked as a fallback very early in the bootmanager logic,
# so we can reach the node regardless of what happens (e.g. bm sometimes hangs)

def Run(vars, log, last_resort = True):

    """
    Bring up sshd inside the boot cd environment for debug purposes.

    Once its running, touch the file /tmp/SSHD_RUNNING so future
    calls to this function don't do anything.

    Expect the following variables in vars to be set:
    BM_SOURCE_DIR     The source dir for the boot manager sources that
                        we are currently running from
    """

    if last_resort:
        message = "Starting debug mode"
    else:
        message = "Starting fallback sshd"


    log.write("\n\nStep: %s.\n"%message)
    
    # make sure we have the variables we need
    try:
        BM_SOURCE_DIR = vars["BM_SOURCE_DIR"]
        if BM_SOURCE_DIR == "":
            raise ValueError, "BM_SOURCE_DIR"

    except KeyError, var:
        raise BootManagerException, "Missing variable in vars: %s\n" % var
    except ValueError, var:
        raise BootManagerException, "Variable in vars, shouldn't be: %s\n" % var

    # constants
    ssh_source_files = "%s/debug_files/" % BM_SOURCE_DIR    
    ssh_dir = "/etc/ssh/"
    key_gen_prog = "ssh-keygen"
    ssh_home = "/root/.ssh"
    cancel_boot_flag = "/tmp/CANCEL_BOOT"
    sshd_started_flag = "/tmp/SSHD_RUNNING"

    # pre-sshd
    pre_sshd_script = os.path.join(ssh_source_files, "pre-sshd")
    if os.path.exists(pre_sshd_script):
        utils.sysexec_noerr(pre_sshd_script, log)
    
    # create host keys if needed
    if not os.path.isdir (ssh_dir):
        utils.makedirs (ssh_dir)

    # original code used to specify -b 1024 for the rsa1 key
    # fedora23 seems to come with a release of openssh that lacks suppport
    # for ssh1, and thus rsa1 keys; so we consider that failing to produce
    # the rsa1 key is not a showstopper
    key_specs = [
        ("/etc/ssh/ssh_host_key",     'rsa1', "SSH1 RSA", False),
        ("/etc/ssh/ssh_host_rsa_key", 'rsa',  "SSH2 RSA", True),
        ("/etc/ssh/ssh_host_dsa_key", 'dsa',  "SSH2 DSA", True),
    ]

    for key_file, key_type, label, mandatory in key_specs:
        if not os.path.exists(key_file):
            log.write("Creating {} host key {}\n".format(label, key_file))
            if mandatory:
                run = utils.sysexec
            else:
                run = utils.sysexec_noerr
            run("{} -q -t {} -f {} -C '' -N ''"\
                .format(key_gen_prog, key_type, key_file), log)
            run("chmod 600 {}".format(key_file), log)
            run("chmod 644 {}.pub".format(key_file), log)

    # (over)write sshd config
    utils.sysexec("cp -f {}/sshd_config {}/sshd_config".format(ssh_source_files, ssh_dir), log)
    
    ### xxx ### xxx ### xxx ### xxx ### xxx 

    # always update the key, may have changed in this instance of the bootmanager
    log.write("Installing debug ssh key for root user\n")
    if not os.path.isdir (ssh_home):
        utils.makedirs(ssh_home)
    utils.sysexec("cp -f {}/debug_root_ssh_key {}/authorized_keys".format(ssh_source_files, ssh_home), log)
    utils.sysexec("chmod 700 {}".format(ssh_home), log)
    utils.sysexec("chmod 600 {}/authorized_keys".format(ssh_home), log)

    # start sshd
    if not os.path.isfile(sshd_started_flag):
        log.write("Starting sshd\n")
        utils.sysexec("service sshd start || systemctl start sshd",
                      log, shell=True)
        # flag that ssh is running
        utils.sysexec("touch {}".format(sshd_started_flag), log)
    else:
        # it is expected that sshd is already running when last_resort==True
        if not last_resort:
            log.write("sshd is already running\n")

    if last_resort:
        # this will make the initial script stop requesting scripts from PLC
        utils.sysexec("touch {}".format(cancel_boot_flag), log)

    if last_resort:
        print(warning_message)
    
    return
