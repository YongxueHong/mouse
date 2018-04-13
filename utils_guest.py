import re
import string
from vm import TestCmd
import paramiko

class GuestSession(TestCmd):
    def __init__(self, ip, case_id, params):
        self.__ip = ip
        self.__passwd = params.get('guest_passwd')
        self.__ssh = paramiko.SSHClient()
        self.__ssh.load_system_host_keys()
        self.__ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.__ssh.connect(hostname=ip, port=22, username='root',
                    timeout=60, password=self.__passwd)
        TestCmd.__init__(self, case_id=case_id, params=params)

    def close(self):
        self.__ssh.close()

    def __del__(self):
        self.__ssh.close()

    def guest_cmd_output(self, cmd, timeout=300):
        output = ''
        errput = ''
        allput = ''
        TestCmd.test_print(self, '[root@guest ~]# %s' % cmd)
        stdin, stdout, stderr = self.__ssh.exec_command(command=cmd, timeout=timeout)
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
