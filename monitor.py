import socket
import select
import re
import time
from vm import Test

class RemoteMonitor(Test):
    CONNECT_TIMEOUT = 60
    # The value of DATA_AVAILABLE_TIMEOUT is set 0.1 at least.
    DATA_AVAILABLE_TIMEOUT = 0.1
    MAX_RECEIVE_DATA = 1024

    def __init__(self, case_id, params, ip, port):
        Test.__init__(self, case_id=case_id, params=params)
        self._ip = ip
        self._qmp_port = int(params.get('qmp_port'))
        self._serial_port = int(params.get('serial_port'))
        self._guest_passwd = params.get('guest_passwd')
        self._port = port
        self.address = (ip, port)
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.settimeout(self.CONNECT_TIMEOUT)
        try:
            self._socket.connect(self.address)
            Test.test_print(self, 'Connect to monitor(%s:%s) successfully.'
                            % (ip, port))
        except socket.error:
            Test.test_error(self, 'Fail to connect to monitor(%s:%s).'
                            % (ip, port))

    def __del__(self):
        self._socket.close()

    def close(self):
        self._socket.close()

    def data_availabl(self, timeout=DATA_AVAILABLE_TIMEOUT):
        try:
            return bool(select.select([self._socket], [], [], timeout)[0])
        except socket.error:
            Test.test_error(self, 'Verifying data on monitor(%s:%s) socket.'
                            % (self._ip, self._port))

    def send_cmd(self, cmd):
        try:
            self._socket.sendall(cmd + '\n')
        except socket.error:
            Test.test_error(self, 'Fail to send command to monitor(%s:%s).'
                            % (self._ip, self._port))

    def rec_data(self, recv_timeout=None, max_recv_data=None, search_str=None):
        if not recv_timeout:
            recv_timeout = self.DATA_AVAILABLE_TIMEOUT
        if not max_recv_data:
            max_recv_data = self.MAX_RECEIVE_DATA
        s = ''
        data = ''
        max_recv_data = max_recv_data
        while self.data_availabl(timeout=recv_timeout):
            try:
                data = self._socket.recv(max_recv_data)
            except socket.error:
                Test.test_error(self, 'Fail to receive data from monitor(%s:%s).'
                                % (self._ip, self._port))
            if not data:
                break
            if search_str:
                if re.findall(search_str, data):
                    info = '===> Found the searched keyword \"%s\" on serial. ' \
                           % search_str
                    s += data + '\n' + info
                    return s
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
    QMP_CMD_TIMEOUT = 1.5
    def __init__(self, case_id, params, ip, port,
                 recv_timeout=None, max_recv_data=None):
        self._ip = ip
        self._port = port
        self._address = (self._ip, self._port)
        RemoteMonitor.__init__(self, case_id=case_id,
                               params=params, ip=ip, port=port)
        self.qmp_initial(recv_timeout, max_recv_data)

    def qmp_initial(self, recv_timeout=None, max_recv_data=None):
        if not recv_timeout:
            recv_timeout = self.QMP_CMD_TIMEOUT
        if not max_recv_data:
            max_recv_data = RemoteMonitor.MAX_RECEIVE_DATA
        cmd = '{"execute":"qmp_capabilities"}'
        RemoteMonitor.test_print(self, cmd)
        RemoteMonitor.send_cmd(self, cmd)
        output = RemoteMonitor.rec_data(self,
                                        recv_timeout=recv_timeout,
                                        max_recv_data=max_recv_data)
        RemoteMonitor.test_print(self, output)

        cmd = '{"execute":"query-status"}'
        RemoteMonitor.test_print(self, cmd)
        RemoteMonitor.send_cmd(self, cmd)
        output = RemoteMonitor.rec_data(self,
                                        recv_timeout=recv_timeout,
                                        max_recv_data=max_recv_data)
        RemoteMonitor.test_print(self, output)

    def qmp_cmd_output(self, cmd, echo_cmd=True, verbose=True,
                       recv_timeout=None, max_recv_data=None):
        if not recv_timeout:
            recv_timeout = self.QMP_CMD_TIMEOUT
        if not max_recv_data:
            max_recv_data = RemoteMonitor.MAX_RECEIVE_DATA
        output =''
        if echo_cmd == True:
            RemoteMonitor.test_print(self, cmd)
        if re.search(r'quit', cmd):
            RemoteMonitor.send_cmd(self, cmd)
        else:
            RemoteMonitor.send_cmd(self, cmd)
            output = RemoteMonitor.rec_data(self,
                                            recv_timeout=recv_timeout,
                                            max_recv_data=max_recv_data)
            err_info = 'Failed to run %s under %s sec' % (cmd, recv_timeout)
            RemoteMonitor.test_error(self, err_info)
            if verbose == True:
                RemoteMonitor.test_print(self, output)
            return output

class RemoteSerialMonitor(RemoteMonitor):
    SERIAL_CMD_TIMEOUT = 1.5
    def __init__(self, case_id, params, ip, port):
        self._ip = ip
        self._port = port
        self._parmas = params
        self._guest_passwd = params.get('guest_passwd')
        RemoteMonitor.__init__(self, case_id=case_id, ip=ip,
                               port=port, params=params)

    def prompt_password(self, output, recv_timeout=None,
                        max_recv_data=None, sub_timeout=None):
        if not recv_timeout:
            recv_timeout = 1
        if not max_recv_data:
            max_recv_data = RemoteMonitor.MAX_RECEIVE_DATA
        if not sub_timeout:
            sub_timeout = 10
        end_time = time.time() + sub_timeout
        real_logined = False
        while time.time() < float(end_time):
            if re.findall(r'Password:', output):
                real_logined = True
                break
            output = RemoteMonitor.rec_data(self,
                                            recv_timeout=recv_timeout,
                                            max_recv_data=max_recv_data,)
            RemoteMonitor.test_print(self, info=output, serial_debug=True)

        err_info = 'No prompt \"Pssword:\" under %s sec after type user.'\
                   % sub_timeout
        if real_logined == False:
            RemoteMonitor.test_error(self, err_info)

    def prompt_shell(self, output, recv_timeout=None,
                     max_recv_data=None, sub_timeout=None):
        if not sub_timeout:
            sub_timeout = 10
        if not recv_timeout:
            recv_timeout = 1
        if not max_recv_data:
            max_recv_data = RemoteMonitor.MAX_RECEIVE_DATA
        end_time = time.time() + sub_timeout
        real_logined = False
        sub_real_logined = False
        while time.time() < float(end_time):
            if re.findall(r'Last login:', output):
                if  re.findall(r']#', output):
                    real_logined = True
                    break
                else:
                    while time.time() < float(end_time):
                        output = RemoteMonitor.rec_data(self,
                                                        recv_timeout=recv_timeout,
                                                        max_recv_data=max_recv_data, )
                        RemoteMonitor.test_print(self, info=output,
                                                 serial_debug=True)
                        if re.findall(r']#', output):
                            sub_real_logined = True
                            break
                    err_info = 'No prompt \"[root@xxxx ~]# \" ' \
                               'under %s sec after type user and password.' \
                               % sub_timeout
                    if sub_real_logined == True:
                        real_logined = True
                        break
                    if sub_real_logined == False:
                        RemoteMonitor.test_error(self, err_info)
            output = RemoteMonitor.rec_data(self,
                                            recv_timeout=recv_timeout,
                                            max_recv_data=max_recv_data,)
            RemoteMonitor.test_print(self, info=output, serial_debug=True)

        err_info = 'Failed to login under %s sec after type user and password.'\
                   % sub_timeout
        if real_logined == False:
            RemoteMonitor.test_error(self, err_info)

    def serial_login(self, recv_timeout=None, login_recv_timeout=None,
                     max_recv_data=None, ip_timeout=None, timeout=300):
        if not recv_timeout:
            recv_timeout = RemoteMonitor.DATA_AVAILABLE_TIMEOUT
        if not max_recv_data:
            max_recv_data = RemoteMonitor.MAX_RECEIVE_DATA
        output = ''
        end_time = time.time() + timeout
        while time.time() < end_time:
            output = RemoteMonitor.rec_data(self,
                                            recv_timeout=recv_timeout,
                                            max_recv_data=max_recv_data)
            RemoteMonitor.test_print(self, info=output, serial_debug=True)
            if re.findall(r'Call Trace:', output):
                RemoteQMPMonitor.test_error(self, 'Guest hit call trace')
            if re.search(r"login:", output):
                break
        if not output and not re.search(r"login:", output):
            err_info = 'No prompt \"ligin:\" under %s sec' % timeout
            RemoteMonitor.test_error(self, err_info)

        if login_recv_timeout:
            login_recv_timeout = 8
        cmd = 'root'
        RemoteMonitor.send_cmd(self, cmd)
        output = RemoteMonitor.rec_data(self, recv_timeout=login_recv_timeout)
        RemoteMonitor.test_print(self, info=output, serial_debug=True)

        self.prompt_password(output)

        RemoteMonitor.send_cmd(self, self._guest_passwd)
        RemoteMonitor.test_print(self, info=self._guest_passwd,
                                 serial_debug=True)
        output = RemoteMonitor.rec_data(self, recv_timeout=login_recv_timeout)
        RemoteMonitor.test_print(self, info=output, serial_debug=True)

        if re.findall(r'Login incorrect', output):
            RemoteMonitor.test_print(self, info='Try to login again.')
            cmd = 'root'
            RemoteMonitor.send_cmd(self, cmd)
            output = RemoteMonitor.rec_data(self,
                                            recv_timeout=login_recv_timeout)
            RemoteMonitor.test_print(self, info=output, serial_debug=True)

            self.prompt_password(output)

            RemoteMonitor.send_cmd(self, self._guest_passwd)
            RemoteMonitor.test_print(self, info=self._guest_passwd,
                                     serial_debug=True)
            output = RemoteMonitor.rec_data(self,
                                            recv_timeout=login_recv_timeout)
            RemoteMonitor.test_print(self, info=output, serial_debug=True)

        self.prompt_shell(output)

        ip = self.serial_get_ip(ip_timeout=ip_timeout)
        return ip

    def serial_output(self, max_recv_data=None, recv_timeout=None,
                      verbose=True, search_str=None):
        if not recv_timeout:
            recv_timeout = RemoteMonitor.DATA_AVAILABLE_TIMEOUT
        if not max_recv_data:
            max_recv_data = RemoteMonitor.MAX_RECEIVE_DATA
        output = RemoteMonitor.rec_data(self, recv_timeout=recv_timeout,
                                        max_recv_data=max_recv_data,
                                        search_str=search_str)
        if verbose == True:
            RemoteMonitor.test_print(self, output)
        return output

    def serial_cmd(self, cmd, echo_cmd=True):
        if echo_cmd == True:
            RemoteMonitor.test_print(self,
                                     info='[root@guest ~]# %s' % cmd,
                                     serial_debug=True)
        RemoteMonitor.send_cmd(self, cmd)

    def serial_cmd_output(self, cmd, recv_timeout=None, max_recv_data=None,
                          echo_cmd=True, verbose=True):
        if not recv_timeout:
            recv_timeout = self.SERIAL_CMD_TIMEOUT
        if not max_recv_data:
            max_recv_data = RemoteMonitor.MAX_RECEIVE_DATA
        output = ''
        if echo_cmd == True:
            RemoteMonitor.test_print(self,
                                     info='[root@guest ~]# %s' % cmd,
                                     serial_debug=True)
        RemoteMonitor.send_cmd(self, cmd)
        output = RemoteMonitor.rec_data(self, recv_timeout=recv_timeout,
                                        max_recv_data=max_recv_data)
        if not output:
            err_info = 'Failed to run \"%s\" under %s sec' % (cmd, recv_timeout)
            RemoteMonitor.test_error(self, err_info)
        output = RemoteMonitor.remove_cmd_echo_blank_space(self,
                                                           cmd=cmd,
                                                           output=output)
        if verbose == True:
            RemoteMonitor.test_print(self, info=output, serial_debug=True)
        if re.findall(r'command not found', output) \
                or re.findall(r'-bash', output):
            RemoteMonitor.test_error(self, 'Command %s failed' % cmd)
        return output

    def serial_get_ip(self, ip_timeout=None):
        if not ip_timeout:
            ip_timeout = 1
        ip = ''
        output = ''
        cmd = "ifconfig | grep -E 'inet ' | awk '{ print $2}'"
        output = self.serial_cmd_output(cmd, recv_timeout=ip_timeout)
        for ip in output.splitlines():
            if ip == '127.0.0.1':
                continue
            else:
                if not ip:
                    RemoteMonitor.test_error(self, 'Could not get ip address!')
                return ip

    def serial_shutdown_vm(self, recv_timeout=None, timeout=600):
        if not recv_timeout:
            recv_timeout = 2.0
        output = self.serial_cmd_output('shutdown -h now',
                                        recv_timeout=recv_timeout)
        downed = False
        end_time = time.time() + timeout
        while time.time() < float(end_time):
            output = self.serial_output()
            if re.findall(r'Power down', output):
                downed = True
                break
            if re.findall(r'Call Trace', output):
                RemoteMonitor.test_error(
                    self, 'Guest hit call trace.')
        if downed == False:
            RemoteMonitor.test_error(
                self, 'Failed to shutdown vm under %s sec.' % timeout)
