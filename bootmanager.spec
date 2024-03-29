#
%define name bootmanager
%define version 6.0
%define taglevel 0

%define release %{taglevel}%{?pldistro:.%{pldistro}}%{?date:.%{date}}

Vendor: PlanetLab
Packager: PlanetLab Central <support@planet-lab.org>
Distribution: PlanetLab %{plrelease}
URL: %{SCMURL}

Summary: The PlanetLab Boot Manager
Name: %{name}
Version: %{version}
Release: %{release}
License: BSD
Group: System Environment/Base
Source0: %{name}-%{version}.tar.gz
BuildRoot: %{_tmppath}/%{name}-%{version}-%{release}-root
# in theory this should be a noarch rpm
# however because of libc-opendir-hack (which apparently targets f12 bootCDs)
# this is not true anymore and fedora23 won't let us build this as noarch anymore
# BuildArch: noarch

Requires: tar, sharutils, bzip2
# see myplc/plc.d/gpg for more details on the gnupg / gpg topic
%if "%{distro}" == "Fedora" && %{distrorelease} >= 31
Requires: gnupg1
%else
Requires: gnupg
%endif

# need the apache user at install-time
Requires: httpd 

Requires: plcapi >= 5.2
# we need to install these on the myplc side too, although this is suboptimal
# b/c this python code gets shipped on the nodes as well
Requires: pypcilib pyplnet

### avoid having yum complain about updates, as stuff is moving around
# plc.d/bootmanager
Conflicts: myplc <= 4.3
# nodeconfig/boot/*
Conflicts: nodeconfig <= 4.3

AutoReqProv: no
%define debug_package %{nil}

%description
The PlanetLab Boot Manager securely authenticates and boots PlanetLab
nodes.

%prep
%setup -q

%build
gcc -shared -fPIC -ldl -Os -o source/libc-opendir-hack.so source/libc-opendir-hack.c

%install
rm -rf $RPM_BUILD_ROOT

# Install source so that it can be rebuilt
find build.sh source | cpio -p -d -u $RPM_BUILD_ROOT/%{_datadir}/%{name}/regular/

install -m 644 README  $RPM_BUILD_ROOT/%{_datadir}/%{name}/README

# formerly in the nodeconfig module
install -D -m 755 nodeconfig/boot/index.php $RPM_BUILD_ROOT/var/www/html/boot/index.php
install -D -m 755 nodeconfig/boot/upload-bmlog.php $RPM_BUILD_ROOT/var/www/html/boot/upload-bmlog.php
install -D -m 755 nodeconfig/boot/getnodeid.php $RPM_BUILD_ROOT/var/www/html/boot/getnodeid.php

# formerly in the MyPLC module
install -D -m 755 plc.d/bootmanager $RPM_BUILD_ROOT/etc/plc.d/bootmanager

%clean
rm -rf $RPM_BUILD_ROOT

%post
# initialize the boot manager upload area
mkdir -p /var/log/bm
chown apache:apache /var/log/bm
chmod 700 /var/log/bm

%files
%defattr(-,root,root,-)
%{_datadir}/%{name}
/var/www/html/boot/index.php
/var/www/html/boot/upload-bmlog.php
/var/www/html/boot/getnodeid.php
/etc/plc.d/bootmanager

%changelog
* Mon Jan 07 2019 Thierry <Parmentelat> - bootmanager-6.0-0
- * this is STILL BASED ON PYTHON2, but relies on 2 accessory libraries that are pypcilib and pyplnet
- for this reason, the relevant files are COPIED at packaging time
- * new settings lxc_ROOT_SIZE=12G (was 70G) and SWAP_SIZE=4G (was 1G)
- and lxc_TOTAL_MINIMUM_DISK_SIZE=50 (was 120)
- * invoke conf_files.py as a plain script (i.e. expects a shebang) since we ideally can still
- use this code against a python2 nodemanager
- * skip nodeupdate step, will be redone later anyway
- * rely on NetworkManager utilities when ifconfig can't be found
- * tear down patch for very old 2.6.12 kernels
- * a little closer to python3 though

* Sun Jan 10 2016 Thierry Parmentelat <thierry.parmentelat@sophia.inria.fr> - bootmanager-5.3-4
- runlevelagent was not able to reach myplc because of
- server verification that is now implicit in python 2.7.9

* Tue Dec 08 2015 Thierry Parmentelat <thierry.parmentelat@sophia.inria.fr> - bootmanager-5.3-3
- patch for f23 as of dec. 2015 where kernel and initrd show up in
- a new location under /boot
- plus bugfix with format and single { and } for awk args

* Fri Nov 13 2015 Thierry Parmentelat <thierry.parmentelat@sophia.inria.fr> - bootmanager-5.3-2
- not a noarch package anymore (indeed it does come with binaries)
- fix ssl connection for runlevelagent for recent pythons
- for fedora23, ignore if rsa1 key generation fails

* Fri Jun 26 2015 Thierry Parmentelat <thierry.parmentelat@sophia.inria.fr> - bootmanager-5.3-1
- Use TLSv1 to connect to myplc, instead of SSLv3 that is known to be broken
- Can implement 'upgrade' in addition to 'reinstall' boot state
- upgrade does essentially the same as reinstall except that slices are preserved
- upgrade works only on nodes already running containers
- because /vservers/ needs to be a btrfs filesystem
- pycurl is now a strong requirement (old curl-based code removed)
- bugfix for ssh key generation (were all typed rsa1)
- a lot of prettification

* Wed Jul 16 2014 Thierry Parmentelat <thierry.parmentelat@sophia.inria.fr> - bootmanager-5.2-5
- runs AnsibleHook, that optionnally runs playbooks (by default, usual behaviour)
- introduces the ONE_PARTITION configuration variable
- some suport for chainbooting ubuntu

* Mon Apr 28 2014 Thierry Parmentelat <thierry.parmentelat@sophia.inria.fr> - bootmanager-5.2-4
- no functional change, only tweaks in Makefile for interating with test environment

* Tue Mar 25 2014 Thierry Parmentelat <thierry.parmentelat@sophia.inria.fr> - bootmanager-5.2-3
- some old f18 bootCDs do not support mkfs.btrfs -f
- so invoke this option only when supported

* Fri Mar 21 2014 Thierry Parmentelat <thierry.parmentelat@sophia.inria.fr> - bootmanager-5.2-2
- conf_files.py is expected in /usr/share/NodeManager, not in /etc/init.d any more
- smarter for locating initrd, for f20
- add -f to mkfs.btrfs - sometimes hangs otherwise

* Thu Mar 07 2013 Thierry Parmentelat <thierry.parmentelat@sophia.inria.fr> - bootmanager-5.2-1
- merged the branches for vserver and lxc
- requires the rest of 5.2 - notably 'virt' in GetNodeFlavour
- note that WriteModprobeConfig and MakeInitrd are turned off for lxc nodes
- also note that fsck management for btrfs/lxc is still weak
- vs_ROOT_SIZE=14G lxc_ROOT_SIZE=70G
- vs_TOTAL_MINIMUM_DISK_SIZE=50G lxc_TOTAL_MINIMUM_DISK_SIZE=120G
- expects ntpd to be turned on in the nodeimage

* Fri Feb 22 2013 Thierry Parmentelat <thierry.parmentelat@sophia.inria.fr> - bootmanager-5.1-5
- fix for heterogeneous bootimage/nodeimage

* Thu Feb 21 2013 Thierry Parmentelat <thierry.parmentelat@sophia.inria.fr> - bootmanager-5.1-4
- Turn off WriteModprobeConfig for f18
- enable btrfs quota
- fix very old ssh DSA key generation

* Tue Oct 16 2012 Thierry Parmentelat <thierry.parmentelat@sophia.inria.fr> - bootmanager-5.1-3
- run parted with --script to keep it from hanging

* Fri Aug 31 2012 Thierry Parmentelat <thierry.parmentelat@sophia.inria.fr> - bootmanager-5.0-24
- run parted with --script to avoid it to hang

* Wed Jul 18 2012 Thierry Parmentelat <thierry.parmentelat@sophia.inria.fr> - bootmanager-5.1-2
- pour the 5.0-22 and 5.0-23 features into the lxc mix

* Mon Jul 09 2012 Thierry Parmentelat <thierry.parmentelat@sophia.inria.fr> - bootmanager-5.0-23
- added support for disks larger than 2Tb using gpt instead of msdos

* Tue May 15 2012 Thierry Parmentelat <thierry.parmentelat@sophia.inria.fr> - bootmanager-5.0-22
- bootmanager log clearly states duration of download and extraction of node image

* Fri Apr 13 2012 Thierry Parmentelat <thierry.parmentelat@sophia.inria.fr> - bootmanager-5.1-1
- first working draft for dealing with f16 nodes
- not expected to work with mainline nodes (use 5.0 for that for now)

* Fri Apr 13 2012 Thierry Parmentelat <thierry.parmentelat@sophia.inria.fr> - bootmanager-5.0-21
- no significant change, just checkpoint as 5.1 is addressing lxc

* Thu Jul 07 2011 Thierry Parmentelat <thierry.parmentelat@sophia.inria.fr> - bootmanager-5.0-20
- be more explicit on the node conf_file actually used
- did this after a former PLC node tried to boot at PLE with its PLC plnode.txt still on a usb stick

* Fri Jun 10 2011 Thierry Parmentelat <thierry.parmentelat@sophia.inria.fr> - bootmanager-5.0-19
- nicer log - was intended for previous tag

* Wed Jun 08 2011 Thierry Parmentelat <thierry.parmentelat@sophia.inria.fr> - bootmanager-5.0-18
- {Start,Stop,}RunLevelAgent now ship with bootmanager
- new UpdateLastBootOnce
- root_size bumped to 14Gb which is more in line with modern h/w
- more safely tries to umount /dev/ and /sys
- support for raid partitions
- mkswap -f
- blacklist files from /etc/modprobe.conf/* instead

* Thu Feb 17 2011 Thierry Parmentelat <thierry.parmentelat@sophia.inria.fr> - bootmanager-5.0-17
- on install of boostrapfs, keep track in /bm-install.log with date & flavour

* Sun Jan 23 2011 Thierry Parmentelat <thierry.parmentelat@sophia.inria.fr> - bootmanager-5.0-16
- for f14 : try to mount /dev as devtmpfs before bind-mounting to on the hdd's /dev
- fix for chosing version of parted - for f14
- added support for virtio deveices in /dev/vd
- fixed scanning of new disks
- slightly reviewed logs - default mode is verbose
- removed deprecated mkinitrd.sh

* Fri Dec 10 2010 S.Çağlar Onur <caglar@cs.princeton.edu> - bootmanager-5.0-15
- Fix problems caused by shell redirection

* Thu Dec 09 2010 Thierry Parmentelat <thierry.parmentelat@sophia.inria.fr> - bootmanager-5.0-14
- tag 5.0-13 is broken

* Wed Dec 08 2010 S.Çağlar Onur <caglar@cs.princeton.edu> - bootmanager-5.0-13
- Add support for uploading bash_history to a central server for failboot nodes.
- Start to use subprocess instead of deprecated popen2 module
- Fix typo for VSERVERS_SIZE
- Add --allow-missing parameter to support different kernel configs with mkinitrd

* Thu Aug 26 2010 S.Çağlar Onur <caglar@cs.princeton.edu> - bootmanager-5.0-12
- Revert "replace deprecated popen2 with subprocess"

* Wed Aug 11 2010 S.Çağlar Onur <caglar@cs.princeton.edu> - bootmanager-5.0-11
- replace deprecated popen2 with subprocess and handle fsck return codes in a different code path

* Fri Jul 30 2010 S.Çağlar Onur <caglar@cs.princeton.edu> - bootmanager-5.0-10
- Fix typo

* Fri Jul 30 2010 Baris Metin <Talip-Baris.Metin@sophia.inria.fr> - bootmanager-5.0-9
- fix typo

* Wed Jul 28 2010 S.Çağlar Onur <caglar@cs.princeton.edu> - bootmanager-5.0-8
- disable time/count based filesystem checks

* Tue Jul 27 2010 S.Çağlar Onur <caglar@cs.princeton.edu> - bootmanager-5.0-7
- Fix new disk additions to LVM array

* Wed Jul 07 2010 Thierry Parmentelat <thierry.parmentelat@sophia.inria.fr> - BootManager-5.0-6
- bugfix for centos5/python2.4 missing hashlib

* Mon Jul 05 2010 Baris Metin <Talip-Baris.Metin@sophia.inria.fr> - BootManager-5.0-5
- check sha1sum of downloaded bootstrapfs
- try recovering filesystem errors

* Wed Jun 23 2010 Thierry Parmentelat <thierry.parmentelat@sophia.inria.fr> - BootManager-5.0-4
- nicer initscript now uses 'action' from /etc/init.d/functions
- bugfix for nodes with extensions

* Fri Apr 02 2010 Thierry Parmentelat <thierry.parmentelat@sophia.inria.fr> - BootManager-5.0-3
- create /etc/planetlab if missing
- uses key 'ssh_rsa_key' in BootUpdateNode (requires PLCAPI-5.0.5)

* Sat Feb 13 2010 Thierry Parmentelat <thierry.parmentelat@sophia.inria.fr> - BootManager-5.0-2
- caglar's change to run MkInitrd right before kexec
- plus clean up old code

* Fri Jan 29 2010 Thierry Parmentelat <thierry.parmentelat@sophia.inria.fr> - BootManager-5.0-1
- first working version of 5.0:
- pld.c/, db-config.d/ and nodeconfig/ scripts should now sit in the module they belong to
- uses PLCAPI's GetNodeFlavour to get all info on the bootstrapfs tarball(s) to install
- installation layout on the plc side has changed, more consistent for e.g. 'alpha' bootmanagers

* Sat Jan 09 2010 Thierry Parmentelat <thierry.parmentelat@sophia.inria.fr> - BootManager-4.3-16
- support for fedora 12

* Sat Dec 19 2009 Marc Fiuczynski <mef@cs.princeton.edu> - BootManager-4.3-15
- - support for when the node is behind a NAT
- - clean up RUN_LEVEL support
- - support for early sshd

* Thu Nov 19 2009 Daniel Hokka Zakrisson <daniel@hozac.com> - BootManager-4.3-14
- Add NAT model option for nodes which don't resolve properly.

* Mon Sep 07 2009 Stephen Soltesz <soltesz@cs.princeton.edu> - BootManager-4.3-12
- Moved some configuration values from BootServerRequest.py to 'configuration' file.
- BootServerRequest takes the 'VARS' variable to read these values.
- UPLOAD_LOG_SCRIPT can point optionally to the 'upload-bmlog.php' or 'monitor/upload'
- (or any other interface that accepts a POST file)
- build.sh bundles cacerts for boot and monitor servers (if present) to
- authenticate the UPLOAD_LOG_SCRIPT.
- Previously, these certs were re-used from the bootcd, now they are bundled
- with BM.  This allows the BM to point to a completely different myplc if
- desired, and it is still secure, because the original download is
- authenticated.

* Wed Aug 26 2009 Stephen Soltesz <soltesz@cs.princeton.edu> - BootManager-4.3-11
- raise a single exception for nodes with authentication errors
- fix syntax error in MakeInitrd.py

* Mon Aug 10 2009 Stephen Soltesz <soltesz@cs.princeton.edu> - BootManager-4.3-10
- Replace UpdateBootstate with UpdateRunlevel where appropriate.
- Removed failboot and install from forced states.
- Removed checks for initrd in Validate
- Added extra messages for Validate failures, not-installed, no kernel, failed fsck
- Added libc-opendir-hack.so patch from 3.2 branch for 2.6.12 bootcds on PL.

* Mon Jun 29 2009 Marc Fiuczynski <mef@cs.princeton.edu> - BootManager-4.3-9
- Special handling for "forcedeth" ethernet NIC.

* Mon Jun 15 2009 Stephen Soltesz <soltesz@cs.princeton.edu> - BootManager-4.3-8
- include a fix for public pl dealing with old/new boot images and root
- environments

* Fri May 15 2009 Thierry Parmentelat <thierry.parmentelat@sophia.inria.fr> - BootManager-4.3-7
- review selection nodefamily at bootstrapfs install-time
- now based on (1) tags (2) nodefamily and (3) defaults
- this is required on very old bootcd

* Wed Apr 29 2009 Marc Fiuczynski <mef@cs.princeton.edu> - BootManager-4.3-6
- Use modprobe module to write out /etc/modprobe.conf.

* Wed Apr 22 2009 Thierry Parmentelat <thierry.parmentelat@sophia.inria.fr> - BootManager-4.3-5
- minor updates - using the new modprobe module *not* in this tag

* Wed Apr 08 2009 Thierry Parmentelat <thierry.parmentelat@sophia.inria.fr> - BootManager-4.3-4
- load device mapper if needed, for centos5-based bootcd variant

* Wed Mar 25 2009 Thierry Parmentelat <thierry.parmentelat@sophia.inria.fr> - BootManager-4.3-3
- renumbered 4.3
- New step StartRunLevelAgent
- various other tweaks

* Wed Jan 28 2009 Thierry Parmentelat <thierry.parmentelat@sophia.inria.fr> - BootManager-4.3-2
- most of the actual network config job moved to (py)plnet
- support for RAWDISK
- network interfaces deterministically sorted
- does not use nodegroups anymore for getting node arch and other extensions
- drop yum-based extensions
- debug sshd started as early as possible
- timestamped and uploadable logs (requires upload-bmlog.php from nodeconfig/)
- cleaned up (drop support for bootcdv2)
- still needs testing

* Wed Sep 10 2008 Thierry Parmentelat <thierry.parmentelat@sophia.inria.fr> - BootManager-4.3-1
- reflects new names from the data model

* Sat May 24 2008 Thierry Parmentelat <thierry.parmentelat@sophia.inria.fr> - BootManager-3.2-7
- dont unload cpqphp

* Thu Apr 24 2008 Thierry Parmentelat <thierry.parmentelat@sophia.inria.fr> - BootManager-3.2-6
- changes in the state automaton logic 
- root+swap = 7G
- usb-key threshhold increased to 17 G
- bootstrafs selection logic altered - uses /etc/planetlab/nodefamily instead of GetPlcRelease

* Wed Mar 26 2008 Thierry Parmentelat <thierry.parmentelat@sophia.inria.fr> - BootManager-3.2-4 BootManager-3.2-5
- renamed step InstallBootstrapRPM into InstallBootstrapFS
- reviewed selection of bootstrapfs, based on nodegroups, for multi-arch deployment
- import pypcimap rather than pypciscan
- initial downlaoding of plc_config made more robust
- root and /vservers file systems mounted ext3
- calls to BootGetNodeDetails replaced with GetNodes/GetNodeNetworks
- also seems to be using session-based authentication rather than former hmac-based one

* Fri Feb 08 2008 Thierry Parmentelat <thierry.parmentelat@sophia.inria.fr> - bootmanager-3.2-3 bootmanager-3.2-4
- usage of wireless attributes fixed and tested
- breakpoints cleaned up (no change for production)
- less alarming message when floppy does not get unloaded

* Thu Jan 31 2008 Thierry Parmentelat <thierry.parmentelat@sophia.inria.fr> - bootmanager-3.2-2 bootmanager-3.2-3
- network config : support the full set of settings from ifup-wireless - see also http://svn.planet-lab.org/svn/MyPLC/tags/myplc-4.2-1/db-config
- removes legacy calls to PlanetLabConf.py 
- refrains from unloading floppy 
- first draft of the dual-method for implementing extensions (bootstrapfs-like images or yum install)

* Fri Sep  2 2005 Mark Huang <mlhuang@cotton.CS.Princeton.EDU> - 
- Initial build.

