import re
import string
from vm import TestCmd
import paramiko
from pexpect import pxssh, TIMEOUT, EOF
import socket
import os
import aexpect
import time
from utils_session import ShellSession


class GuestSession(ShellSession):
    # implement to connecting to guest session with axpect.
    def __init__(self, ip, case_id, params):
        super(GuestSession, self).__init__(id=case_id, params=params, ip=ip,
                                           prompt=r'^\[.*\][\#\$]\s*$',
                                           cmd_custom_prompt='[root@guest ~]#')

    def guest_cmd_output_safe(self, cmd, timeout=300, verbose=True):
        return ShellSession.cmd_output_safe(self, cmd, timeout, verbose)

    def guest_cmd_status_output(self, cmd, timeout=300, verbose=True):
        return ShellSession.cmd_status_output(self, cmd, timeout, verbose)

    def guest_cmd_status(self, cmd, timeout=300, verbose=True):
        return ShellSession.cmd_status(self, cmd, timeout, verbose)

    def guest_cmd_output(self, cmd, timeout=300, verbose=True):
        return ShellSession.cmd_output(self, cmd, timeout, verbose)

    def guest_system_dev(self, verbose=True):
        cmd = 'ls /dev/[svh]d*'
        output = self.guest_cmd_output(cmd, verbose=verbose)
        system_dev = re.findall('/dev/[svh]d\w+\d+', output)[0]
        system_dev = system_dev.rstrip(string.digits)
        if verbose:
            info = 'system device : %s' % system_dev
            TestCmd.test_print(self, info=info)
        return system_dev, output

    def get_data_disk(self, verbose=True):
        data_disk = []
        cmd = 'lsblk --list | grep disk | awk {\'print $1\'}'
        output = self.guest_cmd_output(cmd, verbose=True)
        sys_dev, _ = self.guest_system_dev(verbose=False)
        for dev in output.splitlines():
            if sys_dev not in ('/dev/' + dev):
                data_disk.append('/dev/' + dev)
        if verbose:
            info = 'data disk : %s' % data_disk
            TestCmd.test_print(self, info=info)
        return data_disk

    def guest_ping_test(self, dst_ip, count):
        cmd_ping = 'ping %s -c %d' % (dst_ip, count)
        output = self.guest_cmd_output(cmd=cmd_ping)
        if re.findall(r'100% packet loss', output):
            TestCmd.test_error(self, 'Ping failed')

    def guest_dmesg_check(self):
        cmd = 'dmesg'
        output = self.guest_cmd_output(cmd)
        if re.findall(r'Call Trace:', output):
            TestCmd.test_error(self, 'Guest hit call trace')

    def guest_get_disk_size(self, dev, verbose=True):
        return self.guest_cmd_output(
            'lsblk -s %s | sed -n \'2p\' | awk {\'print $4\'}' % dev, verbose)

    def guest_create_parts(self, dev, num, fs_type='xfs', verbose=True):
        self.guest_cmd_output(cmd='parted %s -s mklabel gpt'
                                  % dev, verbose=verbose)
        dev_size = re.findall(r"\d+\.?\d*", self.guest_get_disk_size(dev))[0]
        offset_size = (int(dev_size) / num) * 1024
        start = 1
        end = offset_size
        for i in range(0, num):
            self.guest_cmd_output('parted %s -s mkpart primary %s %sMB %sMB'
                                  % (dev, fs_type, start, end), verbose)
            start = end
            end = start + offset_size
        self.guest_cmd_output('parted %s -s p' % dev)