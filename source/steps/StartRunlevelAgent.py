#!/usr/bin/python2
#
# Copyright (c) 2003 Intel Corporation
# All rights reserved.
#
# Copyright (c) 2004-2006 The Trustees of Princeton University
# All rights reserved.


import os

from Exceptions import *
import BootAPI

def Run(vars, log):
    """
        Start the RunlevelAgent.py script.  Should follow
        AuthenticateWithPLC() in order to guarantee that
        /etc/planetlab/session is present.
    """

    log.write("\n\nStep: Starting RunlevelAgent.py\n")

    try:
        cmd = "{}/RunlevelAgent.py".format(vars['BM_SOURCE_DIR'])
        # raise error if script is not present.
        os.stat(cmd)
        # init script only starts RLA once.
        os.system("/usr/bin/python2 {} start bootmanager &".format(cmd))
    except KeyError as var:
        raise BootManagerException("Missing variable in vars: {}\n".format(var))
    except ValueError as var:
        raise BootManagerException("Variable in vars, shouldn't be: {}\n".format(var))

    return 1
    

