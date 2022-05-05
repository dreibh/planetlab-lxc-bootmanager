#!/usr/bin/python2
#

import os

from Exceptions import *
import utils
import systeminfo

def run_ansible(ansible_path, ansible_hash, playbook_name, log):
    try:
        if (ansible_hash):
            hash_arg = '-U {}'.format(ansible_hash)
        else:
            hash_arg = ''
        utils.sysexec_noerr('ansible-pull -i hosts {} {} {}'.format(ansible_path, hash_arg, playbook_name), log )
    except:
        pass


def Run(vars, log):
    log.write("\n\nStep: Running Ansible Hook\n")
    # make sure we have the variables we need
    try:
        ansible_path = vars["ANSIBLE_PATH"]
        run_level = vars["RUN_LEVEL"]
        try:
            ansible_hash = vars["ANSIBLE_HASH"]
        except KeyError:
            ansible_hash = None

        if (ansible_path):
            run_ansible(ansible_path, ansible_hash, "{}.yml".format(run_level), log)
    except KeyError as var:
        log.write("No Ansible directive. Skipping.\n");
        pass
