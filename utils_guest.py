import re
import string
from vm import TestCmd
import paramiko
from pexpect import pxssh, TIMEOUT, EOF
import socket
import os


class GuestSession(TestCmd):
    # Class GuestSession maybe not supported in python3.6
    # and therer is a warning "No handlers could be found
    # for logger "paramiko.transport""
    def __init__(self, ip, case_id, params):
        self._ip = ip
        self._params = params
        self._passwd = params.get('guest_passwd')
        super(GuestSession, self).__init__(case_id=case_id, params=params)
        dir_timestamp = self.params.get('sub_dir_timestamp')
        sub_log_dir = os.path.join(self.params.get('log_dir'),
                                   self.case_id + '-'
                                   + dir_timestamp + '_logs')
        paramiko.util.log_to_file(os.path.join(sub_log_dir, 'paramiko.log'))
        self._ssh = paramiko.SSHClient()
        self._ssh.load_system_host_keys()
        self._ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self._ssh.connect(hostname=ip, port=22, username='root',
                          timeout=60, password=self._passwd)

    def close(self):
        TestCmd.test_print(self,
                        'Closed the guest session(%s).' % (self._ip))
        self._ssh.close()

    def __del__(self):
        TestCmd.test_print(self,
                        'Closed the guest session(%s).' % (self._ip))
        self._ssh.close()

    def guest_cmd_output(self, cmd, timeout=300):
        output = ''
        errput = ''
        allput = ''
        TestCmd.test_print(self, '[root@guest ~]# %s' % cmd)

        stdin, stdout, stderr = self._ssh.exec_command(command=cmd,
                                                       timeout=timeout)
        errput = stderr.read()
        output = stdout.read()
        # Here need to remove command echo and blank space again
        output = TestCmd.remove_cmd_echo_blank_space(self, output=output, cmd=cmd)

        if errput:
            TestCmd.test_print(self, errput)
        if output:
            TestCmd.test_print(self, output)
        allput = errput + output
        if re.findall(r'command not found', allput) or re.findall(r'-bash', allput):
            TestCmd.test_error(self, 'Command %s failed' % cmd)
        return allput

    def guest_system_dev(self, enable_output=True):
        cmd = 'ls /dev/[svh]d*'
        output = self.guest_cmd_output(cmd)
        system_dev = re.findall('/dev/[svh]d\w+\d+', output)[0]
        system_dev = system_dev.rstrip(string.digits)
        if enable_output == True:
            info = 'system device : %s' % system_dev
            TestCmd.test_print(self, info=info)
        return system_dev, output

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


class GuestSessionV2(TestCmd):
    # Class GuestSessionV2 is supported python2 and python3.
    # It is implemented with pexcept(Pexpect is a pure Python module
    # for spawning child applications; controlling them; and responding
    # to expected patterns in their output).
    def __init__(self, ip, case_id, params):
        self._ip = ip
        self._params = params
        self._passwd = params.get('guest_passwd')
        self._cmd = 'ssh root@%s' % self._ip
        super(GuestSessionV2, self).__init__(case_id=case_id, params=params)

        self._ssh = pxssh.pxssh(options={"StrictHostKeyChecking": "no",
                                         "UserKnownHostsFile": "/dev/null"})
        self._ssh.login(server=self._ip, username='root', port=22,
                        password=self._passwd, login_timeout=60)

    def close(self):
        TestCmd.test_print(self,
                        'Closed the guest session(%s).' % (self._ip))
        self._ssh.logout()

    def __del__(self):
        TestCmd.test_print(self,
                        'Closed the guest session(%s).' % (self._ip))
        self._ssh.logout()

    def guest_logout(self):
        TestCmd.test_print(self,
                        'Closed the guest session(%s).' % (self._ip))
        self._ssh.logout()

    def guest_cmd_output(self, cmd, timeout=300):
        output = ''
        TestCmd.test_print(self, '[root@guest ~]# %s' % cmd)
        self._ssh.sendline(cmd)
        if self._ssh.prompt(timeout=timeout):
            output = self._ssh.before
        else:
            TestCmd.test_error(self,
                               'Failed to run \"%s\" under %s sec.'
                               % (cmd, timeout))
        # Here need to remove command echo and blank space again
        output = TestCmd.remove_cmd_echo_blank_space(self, output=output, cmd=cmd)
        TestCmd.test_print(self, output)
        if re.findall(r'command not found', output) or re.findall(r'-bash', output):
            TestCmd.test_error(self, 'Command %s failed' % cmd)
        return output

    def guest_system_dev(self, enable_output=True):
        cmd = 'ls /dev/[svh]d*'
        output = self.guest_cmd_output(cmd)
        system_dev = re.findall('/dev/[svh]d\w+\d+', output)[0]
        system_dev = system_dev.rstrip(string.digits)
        if enable_output == True:
            info = 'system device : %s' % system_dev
            TestCmd.test_print(self, info=info)
        return system_dev, output

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
