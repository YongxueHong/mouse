import re
import string
from vm import TestCmd

class GuestSession(TestCmd):
    def __init__(self, ip, case_id, params):
        self.__ip = ip
        self.__passwd = params.get('guest_passwd')
        TestCmd.__init__(self, case_id=case_id, params=params)

    def exec_cmd_guest(self, ip, passwd, cmd, timeout):
        output = ''
        errput = ''
        output, errput = TestCmd.remote_ssh_cmd(self, ip=ip, passwd=passwd,
                                                cmd=cmd, timeout=timeout)
        return output, errput

    def guest_cmd_output(self, cmd, timeout=300):
        output = ''
        errput = ''
        allput = ''
        TestCmd.test_print(self, cmd)
        output, errput = self.exec_cmd_guest(ip=self.__ip, passwd=self.__passwd,
                                             cmd=cmd, timeout=timeout)
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
