import os
import time
import subprocess
import socket
import usr_exceptions
import threading
import re
import paramiko

class Test():
    def __init__(self, case_id, params):
        self.case_id = case_id
        self.pid_list = []
        self.start_time = time.time()
        self.params = params

    def log_echo_file(self, log_str, short_debug=True, serial_debug=False):
        prefix_file = self.case_id
        log_file_list = []
        if not prefix_file:
            prefix_file = 'Untitled'
        sub_log_dir = os.path.join(self.params.get('log_dir'), self.case_id + '_logs')

        if not os.path.exists(sub_log_dir):
            os.mkdir(sub_log_dir)
        if short_debug == True and serial_debug == False:
            log_file = sub_log_dir + '/' + 'short_debug.log'
            log_file_list.append(log_file)
        if short_debug == True or serial_debug == True:
            log_file = sub_log_dir + '/' + 'long_debug.log'
            log_file_list.append(log_file)
        if serial_debug == True:
            log_file = sub_log_dir + '/' + 'serial_debug.log'
            log_file_list.append(log_file)
        for log_file in log_file_list:
            if os.path.exists(log_file):
                try:
                    run_log = open(log_file, "a")
                    for line in log_str.splitlines():
                        timestamp = time.strftime("%Y-%m-%d-%H:%M:%S")
                        run_log.write("%s: %s\n" % (timestamp, line))

                except Exception, err:
                    txt = "Fail to record log to %s.\n" % log_file
                    txt += "Log content: %s\n" % log_str
                    txt += "Exception error: %s" % err
                    self.test_error(err_info=txt)
            else:
                try:
                    run_log = open(log_file, "a")
                    for line in log_str.splitlines():
                        timestamp = time.strftime("%Y-%m-%d-%H:%M:%S")
                        run_log.write("%s: %s\n" % (timestamp, line))

                except Exception, err:
                    txt = "Fail to record log to %s.\n" % log_file
                    txt += "Log content: %s\n" % log_str
                    txt += "Exception error: %s" % err
                    self.test_error(err_info=txt)

    def test_print(self, info, short_debug=True, serial_debug=False):
        if self.params.get('verbose') == 'yes':
            print (info)
        self.log_echo_file(log_str=info, short_debug=short_debug,
                           serial_debug=serial_debug)

    def total_test_time(self, start_time):
        self._passed = True
        test_time = time.time() - start_time
        if format == 'sec':
            print 'Total of test time :', test_time, 'sec'
        elif format == 'min':
            print 'Total of test time :', int(test_time / 60), 'min'
        else:
            time_info =  'Total of test time : %s min %s sec' \
                         % (int(test_time / 60),
                            int(test_time - int(test_time / 60) * 60))
            self.test_print(info=time_info)

    def open_vnc(self, ip, port, timeout=10):
        self.vnc_ip = ip
        self.vnc_port = port
        data = ''
        vnc_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        vnc_socket.connect((self.vnc_ip, self.vnc_port))
        requet = 'Trying to connect vnc'
        end_time = time.time() + timeout
        while time.time() < end_time:
            vnc_socket.send(requet)
            data = vnc_socket.recv(1024)
            if data:
                break
        print 'Client recevied :', data
        vnc_socket.close()

    def vnc_daemon(self, ip, port, timeout=10):
        thread = threading.Thread(target=self.open_vnc, args=(ip, port, timeout))
        thread.name = 'vnc'
        thread.daemon = True
        thread.start()

    def test_error(self, err_info):
        err_info = 'Case Error: ' + err_info
        self.log_echo_file(log_str=err_info)
        self.test_print(info=err_info)
        raise usr_exceptions.Error(err_info)


    def test_pass(self):
        pass_info = '%s \n' %('*' * 50)
        pass_info += 'Case %s --- Pass \n' % self.case_id.split(':')[0]
        self.test_print(info=pass_info)
        self.total_test_time(start_time=self.start_time)

    def test_timeout_daemon(self, passed, endtime):
        while time.time() < endtime:
            if passed == True:
                break
        if passed == False:
            err_info = 'Case Error: ' + 'RUN TIMEOUT'
            self.log_echo_file(log_str=err_info)


class TestCmd(Test):
    def __init__(self, case_id, params):
        Test.__init__(self, case_id=case_id, params=params)

    def subprocess_cmd_base(self, cmd, echo_cmd=True, verbose=True,
                            enable_output=True, timeout=300):
        output = ''
        errput = ''
        current_time = time.time()
        deadline = current_time + timeout
        pid = ''
        if echo_cmd == True:
            Test.test_print(self, cmd)
        sub = subprocess.Popen(cmd, shell=True, stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        while sub.poll() == None:
            if time.time() > deadline:
                err_info = 'Fail to run %s under %s sec.' % (cmd, timeout)
                TestCmd.test_error(self, err_info)

        fd = sub.stdout.fileno()
        pid = sub.pid
        if (enable_output == True):
            try:
                output = sub.communicate()[0]
            except ValueError:
                pass
            try:
                errput = sub.communicate()[1]
            except ValueError:
                pass
            allput = output + errput
            if verbose == True:
                self.test_print(info=allput)
            if re.findall(r'command not found', allput):
                TestCmd.test_error(self, 'Fail to run %s.' % cmd)
            return allput, fd
        elif (enable_output == False):
            return fd, pid

    def reader(self, name, stream, outbuf, vm_alias=None):
        while 1:
            s = stream.stdout.readline() + stream.stderr.readline()
            if not s:
                break
            s = s.decode('utf-8').rstrip()
            outbuf.append(s)
            if re.findall(r'QEMU', s) or re.findall(r'qemu-kvm:', s)\
                    or re.findall(r'(qemu)', s):
                if vm_alias:
                    Test.test_print(self, 'From %s->%s: %s' % (
                    vm_alias, name, s))
                else:
                    Test.test_print(self, '%s: %s' % (name, s))

    def subprocess_cmd_advanced(self, cmd, echo_cmd=True, vm_alias=None):
        pid = ''
        stdout = []
        if echo_cmd == True:
            Test.test_print(self, cmd)
        sub = subprocess.Popen(cmd, shell=True, stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        t1 = threading.Thread(target=self.reader,
                              args=('stdout', sub, stdout, vm_alias))
        t1.daemon = True
        t1.name = 'stdout_thread'
        t1.start()
        return sub.returncode, stdout

    def remove_cmd_echo_blank_space(self, output, cmd):
        if output:
            lines = output.splitlines()
            count = 0
            for line in lines:

                if line == cmd or line == '\n' \
                        or len(line) == 1 \
                        or len(line) == 0:

                    count = count + 1
                    lines.remove(line)
                    continue
                count = count + 1
            output = "\n".join(lines)
        return output

    # Fix command timeout unexpectedly sometimes.
    def remote_ssh_cmd(self, ip, passwd, cmd, timeout=300):
        errput = ''
        output = ''
        ssh = paramiko.SSHClient()
        ssh.load_system_host_keys()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(hostname=ip, port=22, username='root',
                    timeout=60, password=passwd)
        stdin, stdout, stderr = ssh.exec_command(command=cmd, timeout=timeout)
        errput = stderr.read()
        output = stdout.read()
        ssh.close()
        return output, errput

    def remote_scp(self, ip, cmd, passwd, timeout=1800):
        return self.remote_ssh_cmd(ip=ip, cmd=cmd, passwd=passwd, timeout=timeout)


class CreateTest(Test, TestCmd):
    def __init__(self, case_id, params):
        self.case_id = case_id
        self.id = case_id
        self.params = params
        self.dst_ip = params.get('dst_host_ip')
        self.src_ip = params.get('src_host_ip')
        self.timeout = params.get('timeout')
        self.passwd =params.get('host_passwd')
        passed = False
        endtime = time.time() + float(params.get('timeout'))
        thread = threading.Thread(target=Test.test_timeout_daemon,
                                  args=(self, passed, endtime,))
        thread.name = 'TimeoutThread'
        thread.daemon = True
        thread.start()
        Test.__init__(self, self.id, self.params)
        self.guest_name = params.get('vm_cmd_base')['name'][0]
        self.clear_env()

    def get_id(self):
        info = 'Start to run case : %s' % self.case_id
        Test.test_print(self, info)
        Test.test_print(self, '%s\n' % ('*' * 50))
        return self.id

    def check_guest_process(self):
        pid_list = []
        dst_pid_list = []
        output = ''

        if self.dst_ip:
            src_cmd_check = 'ssh root@%s ps -axu | grep %s | grep -v grep' \
                            % (self.dst_ip, self.guest_name)
            output, _ = TestCmd.subprocess_cmd_base(self, echo_cmd=False,
                                                    verbose=False, cmd=src_cmd_check)
            if output:
                pid = re.split(r"\s+", output)[1]
                info =  'Found a %s dst guest process : pid = %s' \
                        % (self.guest_name, pid)
                TestCmd.test_print(self, info)
                self.kill_dst_guest_process(pid)
            else:
                info = 'No found %s dst guest process' % self.guest_name
                TestCmd.test_print(self, info)
            time.sleep(3)

        src_cmd_check = 'ps -axu | grep %s | grep -v grep' % self.guest_name
        output, _ = TestCmd.subprocess_cmd_base(self, echo_cmd=False,
                                                verbose=False, cmd=src_cmd_check)
        if output:
            pid = re.split(r"\s+", output)[1]
            info =  'Found a %s guest process : pid = %s' % (self.guest_name, pid)
            TestCmd.test_print(self, info)
            self.kill_guest_process(pid)
        else:
            info = 'No found %s guest process' % self.guest_name
            TestCmd.test_print(self, info)

    def kill_guest_process(self, pid):
        cmd = 'kill -9 %s' % pid
        TestCmd.subprocess_cmd_base(self, cmd=cmd, enable_output=False)

    def kill_dst_guest_process(self, pid):
            cmd = 'ssh root@%s kill -9 %s' %(self.dst_ip, pid)
            TestCmd.subprocess_cmd_base(self, cmd=cmd, enable_output=False)

    def clear_env(self):
        pid_list = []
        dst_pid_list = []
        Test.test_print(self, '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~')
        Test.test_print(self, '======= Checking host kernel version: =======')
        TestCmd.subprocess_cmd_base(self, cmd='uname -r')
        if self.dst_ip:
            Test.test_print(self, '======= Checking host kernel '
                                  'version on dst host: =======')
            cmd = 'ssh root@%s uname -r' %(self.dst_ip)
            TestCmd.subprocess_cmd_base(self, cmd=cmd)

        Test.test_print(self, '======= Checking the version of qemu: =======')
        TestCmd.subprocess_cmd_base(self, cmd='/usr/libexec/qemu-kvm -version')
        if self.dst_ip:
            Test.test_print(self, '======= Checking the version of '
                                  'qemu on dst host: =======')
            cmd = 'ssh root@%s /usr/libexec/qemu-kvm -version' %(self.dst_ip)
            TestCmd.subprocess_cmd_base(self, cmd=cmd)

        Test.test_print(self,'======= Checking guest process existed =======')
        self.check_guest_process()
        Test.test_print(self, '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~')

    def main_step_log(self, log):
        log_tag = '='
        log_tag_rept = 7
        log_info = '%s Step %s %s' % (log_tag * log_tag_rept,
                                      log, log_tag * log_tag_rept)
        if self.params.get('verbose') == 'yes':
            print log_info
        Test.log_echo_file(self, log_str=log_info)

    def sub_step_log(self, str):
        log_tag = '-'
        log_tag_rept = 5
        log_info = '%s %s %s' % (log_tag * log_tag_rept,
                                 str, log_tag * log_tag_rept)
        Test.test_print(self, info=log_info)

