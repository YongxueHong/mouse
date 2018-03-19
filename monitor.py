import os, sys
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.extend([BASE_DIR])
import socket
import select
import re
import time
from vm import Test

class RemoteMonitor(Test):
    CONNECT_TIMEOUT = 60
    DATA_AVAILABLE_TIMEOUT = 0
    def __init__(self, case_id, params, ip, port):
        Test.__init__(self, case_id=case_id, params=params)
        self._ip = ip
        self._qmp_port = int(params.get('vm_cmd_base')['qmp'][0].split(',')[0].split(':')[2])
        self._serail_port = int(params.get('vm_cmd_base')['serial'][0].split(',')[0].split(':')[2])
        self._guest_passwd = params.get('guest_passwd')
        self._port = port
        self.address = (ip, port)
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.settimeout(self.CONNECT_TIMEOUT)
        try:
            self._socket.connect(self.address)
            Test.test_print(self, 'Connect to monitor(%s:%s) successfully.' %(ip, port))
        except socket.error:
            Test.test_error(self, 'Fail to connect to monitor(%s:%s).' %(ip, port))

    def __del__(self):
        self._socket.close()

    def close(self):
        self._socket.close()

    def data_availabl(self, timeout=DATA_AVAILABLE_TIMEOUT):
        try:
            return bool(select.select([self._socket], [], [], timeout)[0])
        except socket.error:
            Test.test_error(self, 'Verifying data on monitor(%s:%s) socket.' % (self._ip, self._port))

    def send_cmd(self, cmd):
        try:
            self._socket.sendall(cmd + '\n')
        except socket.error:
            Test.test_error(self, 'Fail to send command to monitor(%s:%s).'%(self._ip, self._port))

    def rec_data(self, recv_timeout=DATA_AVAILABLE_TIMEOUT, max_recv_data=1024):
        s = ''
        data = ''
        max_recv_data = max_recv_data
        while self.data_availabl(timeout=recv_timeout):
            try:
                data = self._socket.recv(max_recv_data)
            except socket.error:
                Test.test_error(self, 'Fail to receive data from monitor(%s:%s).'%(self._ip, self._port))
                return s

            if not data:
                break
            s += data
        return s

    def remove_cmd_echo_blank_space(self, output, cmd):
        if output:
            lines = output.splitlines()
            for line in lines:
                if line == cmd or line == ' ':
                    lines.remove(line)
                    continue
            output = "\n".join(lines)
        return output

class RemoteQMPMonitor(RemoteMonitor):
    def __init__(self, case_id, params, ip, port):
        self._ip = ip
        self._port = port
        self._address = (self._ip, self._port)
        RemoteMonitor.__init__(self, case_id=case_id, params=params, ip=ip, port=port)
        self.qmp_initial()

    def qmp_initial(self):
        cmd = '{"execute":"qmp_capabilities"}'
        RemoteMonitor.test_print(self, cmd)
        RemoteMonitor.send_cmd(self, cmd)
        output = RemoteMonitor.rec_data(self, recv_timeout=3)
        RemoteMonitor.test_print(self, output)

        cmd = '{"execute":"query-status"}'
        RemoteMonitor.test_print(self, cmd)
        RemoteMonitor.send_cmd(self, cmd)
        output = RemoteMonitor.rec_data(self, recv_timeout=3)
        RemoteMonitor.test_print(self, output)

    def qmp_cmd_output(self, cmd, echo_cmd=True, verbose=True, recv_timeout=3, timeout=1800):
        output =''
        if echo_cmd == True:
            RemoteMonitor.test_print(self, cmd)
        if re.search(r'quit', cmd):
            RemoteMonitor.send_cmd(self, cmd)
        else:
            RemoteMonitor.send_cmd(self, cmd)
            endtime = time.time() + timeout
            while time.time() < endtime:
                output = RemoteMonitor.rec_data(self, recv_timeout=recv_timeout)
                if output:
                    break
            if not output:
                err_info = '%s TIMEOUT' % cmd
                RemoteMonitor.test_error(self, err_info)
            if verbose == True:
                RemoteMonitor.test_print(self, output)
            return output

class RemoteSerialMonitor(RemoteMonitor):
    def __init__(self, case_id, params, ip, port):
        self._ip = ip
        self._port = port
        self._parmas = params
        self._guest_passwd = params.get('guest_passwd')
        RemoteMonitor.__init__(self, case_id=case_id, ip=ip, port=port, params=params)

    def serial_login(self, timeout=300):
        output = ''
        end_time = time.time() + timeout
        while time.time() < end_time:
            output = RemoteMonitor.rec_data(self)
            RemoteMonitor.test_print(self, info=output, serial_debug=True)
            if re.findall(r'Call Trace:', output):
                RemoteQMPMonitor.test_error(self, 'Guest hit call trace')
            if re.search(r"login:", output):
                break
        if not output and not re.search(r"login:", output):
            RemoteMonitor.test_error(self, 'LOGIN TIMEOUT!')

        cmd = 'root'
        RemoteMonitor.send_cmd(self, cmd)
        output = RemoteMonitor.rec_data(self, recv_timeout=8)
        RemoteMonitor.test_print(self, info=output, serial_debug=True)

        RemoteMonitor.send_cmd(self, self._guest_passwd)
        RemoteMonitor.test_print(self, info=self._guest_passwd, serial_debug=True)
        output = RemoteMonitor.rec_data(self, recv_timeout=8)
        RemoteMonitor.test_print(self, info=output, serial_debug=True)

        if re.findall(r'Login incorrect', output):
            RemoteMonitor.test_print(self, info='Try to login agine.')
            cmd = 'root'
            RemoteMonitor.send_cmd(self, cmd)
            output = RemoteMonitor.rec_data(self, recv_timeout=10)
            RemoteMonitor.test_print(self, info=output, serial_debug=True)

            RemoteMonitor.send_cmd(self, self._guest_passwd)
            RemoteMonitor.test_print(self, info=self._guest_passwd, serial_debug=True)
            output = RemoteMonitor.rec_data(self, recv_timeout=10)
            RemoteMonitor.test_print(self, info=output, serial_debug=True)

        ip = self.serial_get_ip()
        return ip

    def serial_output(self, max_recv_data=1024):
        output = RemoteMonitor.rec_data(self, max_recv_data=max_recv_data)
        return output

    def serial_cmd(self, cmd):
        RemoteMonitor.test_print(self, info=cmd, serial_debug=True)
        RemoteMonitor.send_cmd(self, cmd)

    def serial_cmd_output(self, cmd, echo_cmd=True, verbose=True, recv_timeout=3, timeout=300):
        output = ''
        if echo_cmd == True:
            RemoteMonitor.test_print(self, info=cmd, serial_debug=True)
        RemoteMonitor.send_cmd(self, cmd)
        endtime = time.time() + timeout
        while time.time() < endtime:
            output = RemoteMonitor.rec_data(self, recv_timeout=recv_timeout)
            if output:
                break
        if not output:
            err_info = '%s TIMEOUT' % cmd
            RemoteMonitor.test_error(self, err_info)
        output = RemoteMonitor.remove_cmd_echo_blank_space(self, cmd=cmd, output=output)
        if verbose == True:
            RemoteMonitor.test_print(self, info=output, serial_debug=True)
        if re.findall(r'command not found', output) or re.findall(r'-bash', output):
            RemoteMonitor.test_error(self, 'Command %s failed' %cmd)
        return output

    def serial_cmd_output_v2(self, cmd, echo_cmd=True, verbose=True, timeout=300):
        output = ''
        if echo_cmd == True:
            RemoteMonitor.test_print(self, info=cmd, serial_debug=True)
        RemoteMonitor.send_cmd(self, cmd)
        output = RemoteMonitor.rec_data(self, recv_timeout=timeout)
        output = RemoteMonitor.remove_cmd_echo_blank_space(self, cmd=cmd, output=output)
        if verbose == True:
            RemoteMonitor.test_print(self, info=output, serial_debug=True)
        if re.findall(r'command not found', output) or re.findall(r'-bash', output):
            RemoteMonitor.test_error(self, 'Command %s failed' %cmd)
        return output

    def serial_get_ip(self):
        ip = ''
        output = ''
        cmd = "ifconfig | grep -E 'inet ' | awk '{ print $2}'"
        output = self.serial_cmd_output(cmd, recv_timeout=5)
        for ip in output.splitlines():
            if ip == '127.0.0.1':
                continue
            else:
                if not ip:
                    RemoteMonitor.test_error(self, 'Could not get ip address!')
                return ip

