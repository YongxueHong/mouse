import socket
import select
import re
import time
from vm import Test
from telnetlib import Telnet


class TelnetMonitor(Test):
    CONNECT_TIMEOUT = 60
    def __init__(self, case_id, params, ip, port):
        super(TelnetMonitor, self).__init__(case_id=case_id, params=params)
        self._ip = ip
        self._params = params
        self._guest_passwd = params.get('guest_passwd')
        self._port = port
        try:
            self._telnet_client = Telnet(host=self._ip, port=self._port)
        except EOFError:
            Test.test_error(self, 'Fail to connect to telnet server(%s:%s).'
                            % (ip, port))
        self._telnet_client.open(self._ip, port=self._port,
                                 timeout=self.CONNECT_TIMEOUT)

    def close(self):
        Test.test_print(self,
                        'Closed the telnet(%s:%s).' % (self._ip, self._port))
        self._telnet_client.close()

    def __del__(self):
        Test.test_print(self,
                        'Closed the telnet(%s:%s).' % (self._ip, self._port))
        self._telnet_client.close()


class TelnetSerial(TelnetMonitor):
    def __init__(self, case_id, params, ip, port):
        super(TelnetSerial, self).__init__(case_id, params, ip, port)
        self._params = params
        self._login_timeout = 300
        self._passwd_timeout = 5
        self._shell_timeout = 5
        self._guest_passwd = params.get('guest_passwd')

    def serial_login(self, timeout=300):
        output = ''
        allput = ''
        while 1:
            n, match, output = self._telnet_client.expect([b'\n', b'login:'], timeout)
            TelnetMonitor.test_print(self, output)
            allput = allput + output
            if 'login:' in output:
                break
        if not output:
            TelnetMonitor.test_error(self, 'No prompt \"login:\" under %s" '
                                     % self._login_timeout)
        else:
            if 'Call Trace:' in allput:
                TelnetMonitor.test_error(self, 'Hit Call Trace during guest boot.')
            TelnetMonitor.test_print(self, output)
        self._telnet_client.write('root'.encode('ascii') + b"\n")

        output = self._telnet_client.read_until(
            b'Password:', timeout=self._passwd_timeout)
        if not output:
            TelnetMonitor.test_error(self, 'No prompt \"Password:\" under %s" '
                                     % self._passwd_timeout)
        else:
            TelnetMonitor.test_print(self, output)
        TelnetMonitor.test_print(self, self._guest_passwd)
        self._telnet_client.write(self._guest_passwd.encode('ascii') + b"\n")

        output = self._telnet_client.read_until(
            b'#]', timeout=self._passwd_timeout)
        if not output:
            TelnetMonitor.test_error(self, 'No prompt \"#]:\" under %s" '
                                     % self._shell_timeout)
        else:
            TelnetMonitor.test_print(self, output)


class RemoteMonitor(Test):
    CONNECT_TIMEOUT = 60
    # The value of DATA_AVAILABLE_TIMEOUT is set 0.1 at least.
    DATA_AVAILABLE_TIMEOUT = 0.1
    MAX_RECEIVE_DATA = 1024

    def __init__(self, case_id, params, ip=None, port=None, filename=None):
        super(RemoteMonitor, self).__init__(case_id=case_id, params=params)
        if ip and port and not filename:
            self._ip = ip
            self._port = port
            self._address = (ip, port)
            self._filename = None
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        elif filename and not ip and not port:
            self._filename = filename
            self._ip = None
            self._port = None
            self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        else:
            Test.test_error(self, 'Initialize monitor with invalid arguments.')
        self._socket.settimeout(self.CONNECT_TIMEOUT)
        try:
            if self._ip and self._port and not self._filename:
                self._socket.connect(self._address)
                Test.test_print(self, 'Connect to monitor(%s:%s) successfully.'
                                % (self._ip, self._port))
            elif self._filename and not self._ip and not self._port:
                self._socket.connect(self._filename)
                Test.test_print(self, 'Connect to monitor(%s) successfully.'
                                % self._filename)
        except socket.error:
            if self._ip and self._port and not self._filename:
                Test.test_error(self, 'Fail to connect to monitor(%s:%s).'
                                % (self._ip, self._port))
            elif self._filename and not self._ip and not self._port:
                Test.test_error(self, 'Fail to connect to monitor(%s).'
                                % self._filename)

    def close(self):
        if self._ip and self._port and not self._filename:
            Test.test_print(self,
                            'Closed the monitor(%s:%s).'
                            % (self._ip, self._port))
        elif self._filename and not self._ip and not self._port:
            Test.test_print(self,
                            'Closed the monitor(%s).'
                            % self._filename)
        self._socket.close()

    def __del__(self):
        if self._ip and self._port and not self._filename:
            Test.test_print(self,
                            'Closed the monitor(%s:%s).'
                            % (self._ip, self._port))
        elif self._filename and not self._ip and not self._port:
            Test.test_print(self,
                            'Closed the monitor(%s).'
                            % self._filename)
        self._socket.close()

    def data_availabl(self, timeout=DATA_AVAILABLE_TIMEOUT):
        try:
            return bool(select.select([self._socket], [], [], timeout)[0])
        except socket.error:
            if self._ip and self._port and not self._filename:
                Test.test_error(self, 'Verifying data on monitor(%s:%s) socket.'
                                % (self._ip, self._port))
            elif self._filename and not self._ip and not self._port:
                Test.test_error(self, 'Verifying data on monitor(%s) socket.'
                                % self._filename)

    def send_cmd(self, cmd):
        try:
            self._socket.sendall(cmd + '\n')
        except socket.error:
            if self._ip and self._port and not self._filename:
                Test.test_error(self, 'Fail to send command to monitor(%s:%s).'
                                % (self._ip, self._port))
            elif self._filename and not self._ip and not self._port:
                Test.test_error(self, 'Fail to send command to monitor(%s:%s).'
                                % self._filename)

    def rec_data(self, recv_timeout=DATA_AVAILABLE_TIMEOUT,
                 max_recv_data=MAX_RECEIVE_DATA, search_str=None):
        s = ''
        data = ''
        alldata = ''
        while self.data_availabl(timeout=recv_timeout):
            try:
                data = self._socket.recv(max_recv_data)
            except socket.error:
                if self._ip and self._port and not self._filename:
                    Test.test_error(self, 'Fail to receive data from monitor(%s:%s).'
                                    % (self._ip, self._port))
                elif self._filename and not self._ip and not self._port:
                    Test.test_error(self, 'Fail to receive data from monitor(%s:%s).'
                                    % self._filename)
            if not data:
                break
            alldata = alldata + data
            if search_str:
                if re.findall(search_str, alldata):
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
    QMO_INIT_TIMEOUT = 0.1
    QMP_CMD_TIMEOUT = 1.0
    def __init__(self, case_id, params, ip=None, port=None, filename=None,
                 recv_timeout=QMO_INIT_TIMEOUT,
                 max_recv_data=RemoteMonitor.MAX_RECEIVE_DATA):
        self._params = params
        if ip and port and not filename:
            super(RemoteQMPMonitor, self).__init__(case_id=case_id,
                                                   params=params,
                                                   ip=ip, port=port)
        elif filename and not ip and not port:
            super(RemoteQMPMonitor, self).__init__(case_id=case_id,
                                                   params=params,
                                                   filename=filename)
        else:
            RemoteMonitor.test_error(self,
                                     'Initialize qmp monitor with invalid arguments.')
        self.qmp_initial(recv_timeout, max_recv_data)

    def qmp_initial(self, recv_timeout, max_recv_data):
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
                       recv_timeout=QMP_CMD_TIMEOUT,
                       max_recv_data=RemoteMonitor.MAX_RECEIVE_DATA):
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
            if not output:
                err_info = 'Failed to run %s under %s sec' % (cmd, recv_timeout)
                RemoteMonitor.test_error(self, err_info)
            if verbose == True:
                RemoteMonitor.test_print(self, output)
        return output


class RemoteSerialMonitor(RemoteMonitor):
    SERIAL_CMD_TIMEOUT = 1.0
    def __init__(self, case_id, params, ip=None, port=None, filename=None):
        self._params = params
        self._guest_passwd = params.get('guest_passwd')
        if ip and port and not filename:
            super(RemoteSerialMonitor, self).__init__(case_id=case_id,
                                                   params=params, ip=ip, port=port)
        elif filename and not ip and not port:
            super(RemoteSerialMonitor, self).__init__(case_id=case_id,
                                                   params=params, filename=filename)
        else:
            RemoteMonitor.test_error(self,
                                     'Initialize serial monitor with invalid arguments.')

    def prompt_password(self, output, recv_timeout=1,
                        max_recv_data=RemoteMonitor.MAX_RECEIVE_DATA,
                        sub_timeout=10):
        allput = ''
        end_time = time.time() + sub_timeout
        real_logined = False
        while time.time() < float(end_time):
            allput = allput + output
            if re.findall(r'Password:', allput):
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

    def prompt_shell(self, output, recv_timeout=1,
                     max_recv_data=RemoteMonitor.MAX_RECEIVE_DATA,
                     sub_timeout=10):
        allput = ''
        end_time = time.time() + sub_timeout
        real_logined = False
        while time.time() < float(end_time):
            allput = allput + output
            if re.findall(r']#', allput):
                real_logined = True
                break
            output = RemoteMonitor.rec_data(self,
                                            recv_timeout=recv_timeout,
                                            max_recv_data=max_recv_data,)
            RemoteMonitor.test_print(self, info=output, serial_debug=True)

        err_info = 'Failed to login under %s sec after type user and password.'\
                   % sub_timeout
        if real_logined == False:
            RemoteMonitor.test_error(self, err_info)

    def serial_login(self, recv_timeout=RemoteMonitor.DATA_AVAILABLE_TIMEOUT,
                     login_recv_timeout=8,
                     max_recv_data=RemoteMonitor.MAX_RECEIVE_DATA,
                     ip_timeout=1, timeout=300):
        output = ''
        allput = ''
        end_time = time.time() + timeout
        while time.time() < end_time:
            output = RemoteMonitor.rec_data(self,
                                            recv_timeout=recv_timeout,
                                            max_recv_data=max_recv_data)
            RemoteMonitor.test_print(self, info=output, serial_debug=True)
            allput = allput + output
            if re.findall(r'Call Trace:', allput):
                RemoteQMPMonitor.test_error(self, 'Guest hit call trace')
            if re.search(r"login:", allput):
                break
        if not output and not re.search(r"login:", allput):
            err_info = 'No prompt \"login:\" under %s sec' % timeout
            RemoteMonitor.test_error(self, err_info)

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

    def serial_output(self, max_recv_data=RemoteMonitor.MAX_RECEIVE_DATA,
                      recv_timeout=RemoteMonitor.DATA_AVAILABLE_TIMEOUT,
                      verbose=True, search_str=None):
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

    def serial_cmd_output(self, cmd, recv_timeout=SERIAL_CMD_TIMEOUT,
                          max_recv_data=RemoteMonitor.MAX_RECEIVE_DATA,
                          echo_cmd=True, verbose=True):
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

    def serial_get_ip(self, ip_timeout=1):
        ip = ''
        output = ''
        cmd = "ifconfig | grep -E 'inet ' | awk '{ print $2}'"
        output = self.serial_cmd_output(cmd, recv_timeout=ip_timeout)
        for ip in output.splitlines():
            ip = re.findall(r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b", ip)[0]
            if ip == '127.0.0.1':
                continue
            else:
                if not ip:
                    RemoteMonitor.test_error(self, 'Could not get ip address!')
                return ip

    def serial_shutdown_vm(self, recv_timeout=3.0, timeout=600):
        time.sleep(5)
        output = self.serial_cmd_output('shutdown -h now',
                                        recv_timeout=recv_timeout)
        downed = False
        end_time = time.time() + timeout
        while time.time() < float(end_time):
            output = output + self.serial_output()
            if re.findall(r'Power down', output):
                downed = True
                break
            if re.findall(r'Call Trace', output):
                RemoteMonitor.test_error(
                    self, 'Guest hit call trace.')
        if downed == False:
            RemoteMonitor.test_error(
                self, 'Failed to shutdown vm under %s sec.' % timeout)
