import os

from Exceptions import *
import utils
from systeminfo import systeminfo
import compatibility
from GetAndUpdateNodeDetails import SMP_OPT


def Run( vars, log ):
    """
    See if a node installation is valid. More checks should certainly be
    done in the future, but for now, make sure that the sym links kernel-boot
    and initrd-boot exist in /boot
    
    Expect the following variables to be set:
    SYSIMG_PATH              the path where the system image will be mounted
                             (always starts with TEMP_PATH)
    BOOT_CD_VERSION          A tuple of the current bootcd version
    ROOT_MOUNTED             the node root file system is mounted
    NODE_ID                  The db node_id for this machine
    PLCONF_DIR               The directory to store the configuration file in
    
    Set the following variables upon successfully running:
    ROOT_MOUNTED             the node root file system is mounted
    """

    log.write( "\n\nStep: Validating node installation.\n" )

    # make sure we have the variables we need
    try:
        BOOT_CD_VERSION= vars["BOOT_CD_VERSION"]
        if BOOT_CD_VERSION == "":
            raise ValueError, "BOOT_CD_VERSION"

        SYSIMG_PATH= vars["SYSIMG_PATH"]
        if SYSIMG_PATH == "":
            raise ValueError, "SYSIMG_PATH"

        NODE_ID= vars["NODE_ID"]
        if NODE_ID == "":
            raise ValueError, "NODE_ID"

        PLCONF_DIR= vars["PLCONF_DIR"]
        if PLCONF_DIR == "":
            raise ValueError, "PLCONF_DIR"
        
        NODE_MODEL_OPTIONS= vars["NODE_MODEL_OPTIONS"]

    except KeyError, var:
        raise BootManagerException, "Missing variable in vars: %s\n" % var
    except ValueError, var:
        raise BootManagerException, "Variable in vars, shouldn't be: %s\n" % var


    ROOT_MOUNTED= 0
    if 'ROOT_MOUNTED' in vars.keys():
        ROOT_MOUNTED= vars['ROOT_MOUNTED']

    # mount the root system image if we haven't already.
    # capture BootManagerExceptions during the vgscan/change and mount
    # calls, so we can return 0 instead
    if ROOT_MOUNTED == 0:
        # old cds need extra utilities to run lvm
        if BOOT_CD_VERSION[0] == 2:
            compatibility.setup_lvm_2x_cd( vars, log )
            
        # simply creating an instance of this class and listing the system
        # block devices will make them show up so vgscan can find the planetlab
        # volume group
        systeminfo().get_block_device_list()

        try:
            utils.sysexec( "vgscan", log )
            utils.sysexec( "vgchange -ay planetlab", log )
        except BootManagerException, e:
            log.write( "BootManagerException during vgscan/vgchange: %s\n" %
                       str(e) )
            return 0
            
        utils.makedirs( SYSIMG_PATH )

        try:
            utils.sysexec( "mount /dev/planetlab/root %s" % SYSIMG_PATH, log )
            utils.sysexec( "mount /dev/planetlab/vservers %s/vservers" %
                           SYSIMG_PATH, log )
            utils.sysexec( "mount -t proc none %s/proc" % SYSIMG_PATH, log )
        except BootManagerException, e:
            log.write( "BootManagerException during vgscan/vgchange: %s\n" %
                       str(e) )
            return 0

        ROOT_MOUNTED= 1
        vars['ROOT_MOUNTED']= 1
        
    
    # get the kernel version
    option = ''
    if NODE_MODEL_OPTIONS & SMP_OPT:
        option = 'smp'

    files = ("kernel-boot%s" % option, "initrd-boot%s" % option)
    valid= 1
    for filepath in files:
        if not os.access("%s/boot/%s"%(SYSIMG_PATH,filepath),os.F_OK|os.R_OK):
            log.write( "Node not properly installed:\n")
            log.write( "\tmissing file /boot/%s\n" % filepath )
            valid= 0
    
    if not valid:
        return 0

    # write out the node id to /etc/planetlab/node_id. if this fails, return
    # 0, indicating the node isn't a valid install.
    try:
        node_id_file_path= "%s/%s/node_id" % (SYSIMG_PATH,PLCONF_DIR)
        node_id_file= file( node_id_file_path, "w" )
        node_id_file.write( str(NODE_ID) )
        node_id_file.close()
        node_id_file= None
        log.write( "Updated /etc/planetlab/node_id" )
    except IOError, e:
        log.write( "Unable to write out /etc/planetlab/node_id" )
        return 0

    log.write( "Everything appears to be ok\n" )
    
    return 1
