#!/usr/bin/python
#
# Copyright (c) 2003 Intel Corporation
# All rights reserved.
#
# Copyright (c) 2004-2006 The Trustees of Princeton University
# All rights reserved.

from __future__ import print_function

import sys
import os
import re
import string
import urllib
import tempfile

import pycurl

# if there is no cStringIO, fall back to the original
try:
    from cStringIO import StringIO
except:
    from StringIO import StringIO



class BootServerRequest:

    # all possible places to check the cdrom mount point.
    # /mnt/cdrom is typically after the machine has come up,
    # and /usr is when the boot cd is running
    CDROM_MOUNT_PATH = ("/mnt/cdrom/", "/usr/")
    BOOTSERVER_CERTS = {}
    MONITORSERVER_CERTS = {}
    BOOTCD_VERSION = ""
    HTTP_SUCCESS = 200
    HAS_BOOTCD = 0
    USE_PROXY = 0
    PROXY = 0

    # in seconds, how maximum time allowed for connect
    DEFAULT_CURL_CONNECT_TIMEOUT = 30
    # in seconds, maximum time allowed for any transfer
    DEFAULT_CURL_MAX_TRANSFER_TIME = 3600
    # location of curl executable, if pycurl isn't available
    # and the DownloadFile method is called (backup, only
    # really need for the boot cd environment where pycurl
    # doesn't exist
    CURL_CMD = 'curl'

    # use TLSv1 and not SSLv3 anymore
    CURL_SSL_VERSION = pycurl.SSLVERSION_TLSv1

    def __init__(self, vars, verbose=0):

        self.VERBOSE = verbose
        self.VARS = vars

        # see if we have a boot cd mounted by checking for the version file
        # if HAS_BOOTCD == 0 then either the machine doesn't have
        # a boot cd, or something else is mounted
        self.HAS_BOOTCD = 0

        for path in self.CDROM_MOUNT_PATH:
            self.Message("Checking existance of boot cd on {}".format(path))

            os.system("/bin/mount {} > /dev/null 2>&1".format(path))

            version_file = self.VARS['BOOTCD_VERSION_FILE'].format(path=path)
            self.Message("Looking for version file {}".format(version_file))

            if os.access(version_file, os.R_OK) == 0:
                self.Message("No boot cd found.")
            else:
                self.Message("Found boot cd.")
                self.HAS_BOOTCD = 1
                break

        if self.HAS_BOOTCD:

            # check the version of the boot cd, and locate the certs
            self.Message("Getting boot cd version.")

            versionRegExp = re.compile(r"PlanetLab BootCD v(\S+)")

            bootcd_version_f = file(version_file, "r")
            line = string.strip(bootcd_version_f.readline())
            bootcd_version_f.close()

            match = versionRegExp.findall(line)
            if match:
                (self.BOOTCD_VERSION) = match[0]

            # right now, all the versions of the bootcd are supported,
            # so no need to check it

            self.Message("Getting server from configuration")

            bootservers = [ self.VARS['BOOT_SERVER'] ]
            for bootserver in bootservers:
                bootserver = string.strip(bootserver)
                cacert_path = "{}/{}/{}".format(
                    self.VARS['SERVER_CERT_DIR'].format(path=path),
                    bootserver,
                    self.VARS['CACERT_NAME'])
                if os.access(cacert_path, os.R_OK):
                    self.BOOTSERVER_CERTS[bootserver] = cacert_path

            monitorservers = [ self.VARS['MONITOR_SERVER'] ]
            for monitorserver in monitorservers:
                monitorserver = string.strip(monitorserver)
                cacert_path = "{}/{}/{}".format(
                    self.VARS['SERVER_CERT_DIR'].format(path=path),
                    monitorserver,
                    self.VARS['CACERT_NAME'])
                if os.access(cacert_path, os.R_OK):
                    self.MONITORSERVER_CERTS[monitorserver] = cacert_path

            self.Message("Set of servers to contact: {}".format(self.BOOTSERVER_CERTS))
            self.Message("Set of servers to upload to: {}".format(self.MONITORSERVER_CERTS))
        else:
            self.Message("Using default boot server address.")
            self.BOOTSERVER_CERTS[self.VARS['DEFAULT_BOOT_SERVER']] = ""
            self.MONITORSERVER_CERTS[self.VARS['DEFAULT_BOOT_SERVER']] = ""


    def CheckProxy(self):
        # see if we have any proxy info from the machine
        self.USE_PROXY = 0
        self.Message("Checking existance of proxy config file...")

        if os.access(self.VARS['PROXY_FILE'], os.R_OK) and \
               os.path.isfile(self.VARS['PROXY_FILE']):
            self.PROXY = string.strip(file(self.VARS['PROXY_FILE'], 'r').readline())
            self.USE_PROXY = 1
            self.Message("Using proxy {}.".format(self.PROXY))
        else:
            self.Message("Not using any proxy.")



    def Message(self, Msg):
        if(self.VERBOSE):
            print(Msg)

    def Error(self, Msg):
        sys.stderr.write(Msg + "\n")

    def Warning(self, Msg):
        self.Error(Msg)

    def MakeRequest(self, PartialPath, GetVars,
                    PostVars, DoSSL, DoCertCheck,
                    ConnectTimeout=DEFAULT_CURL_CONNECT_TIMEOUT,
                    MaxTransferTime=DEFAULT_CURL_MAX_TRANSFER_TIME,
                    FormData=None):

        fd, buffer_name = tempfile.mkstemp("MakeRequest-XXXXXX")
        os.close(fd)
        buffer = open(buffer_name, "w+b")

        # the file "buffer_name" will be deleted by DownloadFile()

        ok = self.DownloadFile(PartialPath, GetVars, PostVars,
                               DoSSL, DoCertCheck, buffer_name,
                               ConnectTimeout,
                               MaxTransferTime,
                               FormData)

        # check the ok code, return the string only if it was successfull
        if ok:
            buffer.seek(0)
            ret = buffer.read()
        else:
            ret = None

        buffer.close()
        try:
            # just in case it is not deleted by DownloadFile()
            os.unlink(buffer_name)
        except OSError:
            pass

        return ret

    def DownloadFile(self, PartialPath, GetVars, PostVars,
                     DoSSL, DoCertCheck, DestFilePath,
                     ConnectTimeout = DEFAULT_CURL_CONNECT_TIMEOUT,
                     MaxTransferTime = DEFAULT_CURL_MAX_TRANSFER_TIME,
                     FormData = None):

        self.Message("Attempting to retrieve {}".format(PartialPath))

        # we can't do ssl and check the cert if we don't have a bootcd
        if DoSSL and DoCertCheck and not self.HAS_BOOTCD:
            self.Error("No boot cd exists (needed to use -c and -s.\n")
            return 0

        # ConnectTimeout has to be greater than 0
        if ConnectTimeout <= 0:
            self.Error("Connect timeout must be greater than zero.\n")
            return 0


        self.CheckProxy()

        dopostdata = 0

        # setup the post and get vars for the request
        if PostVars:
            dopostdata = 1
            postdata = urllib.urlencode(PostVars)
            self.Message("Posting data:\n{}\n".format(postdata))

        getstr = ""
        if GetVars:
            getstr = "?" + urllib.urlencode(GetVars)
            self.Message("Get data:\n{}\n".format(getstr))

        # now, attempt to make the request, starting at the first
        # server in the list
        if FormData:
            cert_list = self.MONITORSERVER_CERTS
        else:
            cert_list = self.BOOTSERVER_CERTS

        for server in cert_list:
            self.Message("Contacting server {}.".format(server))

            certpath = cert_list[server]


            # output what we are going to be doing
            self.Message("Connect timeout is {} seconds".format(ConnectTimeout))
            self.Message("Max transfer time is {} seconds".format(MaxTransferTime))

            if DoSSL:
                url = "https://{}/{}{}".format(server, PartialPath, getstr)

                if DoCertCheck:
                    self.Message("Using SSL version {} and verifying peer."
                                 .format(self.CURL_SSL_VERSION))
                else:
                    self.Message("Using SSL version {}."
                                 .format(self.CURL_SSL_VERSION))
            else:
                url = "http://{}/{}{}".format(server, PartialPath, getstr)

            self.Message("URL: {}".format(url))

            # setup a new pycurl instance
            curl = pycurl.Curl()

            # don't want curl sending any signals
            curl.setopt(pycurl.NOSIGNAL, 1)

            curl.setopt(pycurl.CONNECTTIMEOUT, ConnectTimeout)
            curl.setopt(pycurl.TIMEOUT, MaxTransferTime)

            # do not follow location when attempting to download a file
            curl.setopt(pycurl.FOLLOWLOCATION, 0)

            if self.USE_PROXY:
                curl.setopt(pycurl.PROXY, self.PROXY)

            if DoSSL:
                curl.setopt(pycurl.SSLVERSION, self.CURL_SSL_VERSION)

                if DoCertCheck:
                    curl.setopt(pycurl.CAINFO, certpath)
                    curl.setopt(pycurl.SSL_VERIFYPEER, 2)
                else:
                    curl.setopt(pycurl.SSL_VERIFYPEER, 0)

            if dopostdata:
                curl.setopt(pycurl.POSTFIELDS, postdata)

            # setup multipart/form-data upload
            if FormData:
                curl.setopt(pycurl.HTTPPOST, FormData)

            curl.setopt(pycurl.URL, url)

            try:
                # setup the output file
                with open(DestFilePath, "wb") as outfile:

                    self.Message("Opened output file {}".format(DestFilePath))

                    curl.setopt(pycurl.WRITEDATA, outfile)

                    self.Message("Fetching...")
                    curl.perform()
                    self.Message("Done.")

                    http_result = curl.getinfo(pycurl.HTTP_CODE)
                    curl.close()

                self.Message("Results saved in {}".format(DestFilePath))

                # check the code, return 1 if successfull
                if http_result == self.HTTP_SUCCESS:
                    self.Message("Successfull!")
                    return 1
                else:
                    self.Message("Failure, resultant http code: {}"
                                 .format(http_result))

            except pycurl.error as err:
                errno, errstr = err
                self.Error("connect to {} failed; curl error {}: '{}'\n"
                           .format(server, errno, errstr))

        self.Error("Unable to successfully contact any boot servers.\n")
        return 0



def usage():
    print(
    """
Usage: BootServerRequest.py [options] <partialpath>
Options:
 -c/--checkcert        Check SSL certs. Ignored if -s/--ssl missing.
 -h/--help             This help text
 -o/--output <file>    Write result to file
 -s/--ssl              Make the request over HTTPS
 -v                    Makes the operation more talkative
""");



if __name__ == "__main__":
    import getopt

    # check out our command line options
    try:
        opt_list, arg_list = getopt.getopt(sys.argv[1:],
                                           "o:vhsc",
                                           [ "output=", "verbose", \
                                             "help","ssl","checkcert"])

        ssl = 0
        checkcert = 0
        output_file = None
        verbose = 0

        for opt, arg in opt_list:
            if opt in ("-h","--help"):
                usage(0)
                sys.exit()

            if opt in ("-c","--checkcert"):
                checkcert = 1

            if opt in ("-s","--ssl"):
                ssl = 1

            if opt in ("-o","--output"):
                output_file = arg

            if opt == "-v":
                verbose = 1

        if len(arg_list) != 1:
            raise Exception

        partialpath = arg_list[0]
        if string.lower(partialpath[:4]) == "http":
            raise Exception

    except:
        usage()
        sys.exit(2)

    # got the command line args straightened out
    requestor = BootServerRequest(verbose)

    if output_file:
        requestor.DownloadFile(partialpath, None, None, ssl,
                               checkcert, output_file)
    else:
        result = requestor.MakeRequest(partialpath, None, None, ssl, checkcert)
        if result:
            print(result)
        else:
            sys.exit(1)
