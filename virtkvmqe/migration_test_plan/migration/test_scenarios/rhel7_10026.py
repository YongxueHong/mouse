from utils_host import HostSession
from utils_guest import GuestSession
from monitor import RemoteSerialMonitor, RemoteQMPMonitor
import re
import time
from vm import CreateTest
from utils_migration import do_migration

def run_case(params):
    src_host_ip = params.get('src_host_ip')
    dst_host_ip = params.get('dst_host_ip')
    qmp_port = int(params.get('qmp_port'))
    serial_port = int(params.get('serial_port'))
    incoming_port = params.get('incoming_port')
    guest_arch = params.get('guest_arch')
    test = CreateTest(case_id='rhel7_10026', params=params)
    id = test.get_id()
    guest_pwd = params.get('guest_passwd')
    src_host_session = HostSession(id, params)
    login_timeout = 1200

    test.main_step_log('1. Start vm on src host')
    src_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_guest(cmd=src_qemu_cmd, vm_alias='src')
    src_remote_qmp = RemoteQMPMonitor(id, params, src_host_ip, qmp_port)
    src_serial = RemoteSerialMonitor(id, params, src_host_ip, serial_port)
    src_guest_ip = src_serial.serial_login()

    test.main_step_log('2. Start listening mode on dst host')
    incoming_val = 'tcp:0:%s' % incoming_port
    params.vm_base_cmd_add('incoming', incoming_val)
    dst_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_remote_guest(cmd=dst_qemu_cmd, ip=dst_host_ip,
                                       vm_alias='dst')
    dst_remote_qmp = RemoteQMPMonitor(id, params, dst_host_ip, qmp_port)
    dst_serial = RemoteSerialMonitor(id, params, dst_host_ip, serial_port)

    test.main_step_log('3. keep reboot vm with system_reset, let guest '
                       'in bios stage, before kernel loading')
    src_remote_qmp.qmp_cmd_output('{"execute":"system_reset"}')
    if 'ppc64' in guest_arch:
        keyword = 'SLOF'
    elif 'x86_64' in guest_arch:
        keyword = '[    0.000000]'
    while 1:
        serial_output = src_serial.serial_output(max_recv_data=128,
                                                 search_str=keyword)
        test.test_print(serial_output)
        if re.findall(r'Found the searched keyword', serial_output):
            break
        if re.findall(r'login', serial_output):
            test.test_error('Failed to catch migration point')

    test.main_step_log('4. implement migrate during vm reboot')
    chk_info = do_migration(src_remote_qmp, incoming_port, dst_host_ip)
    if (chk_info == True):
        test.test_print('Migration succeed')
    elif (chk_info == False):
        test.test_error('Migration timeout')

    test.main_step_log('5. After migration, check if guest works well')
    end_time = time.time() + login_timeout
    flag = False
    while time.time() < end_time:
        usr_output =  dst_serial.serial_cmd_output('root')
        if re.findall(r'Password:', usr_output):
            output = dst_serial.serial_cmd_output(guest_pwd)
            if re.findall(r'Last login:', output):
                dst_guest_ip = dst_serial.serial_get_ip()
                flag = True
                break

    if (flag == False):
        test.test_error('Destination login timeout')

    dst_guest_session = GuestSession(case_id=id, params=params,ip=dst_guest_ip)
    test.sub_step_log('5.1 Guest mouse and keyboard')
    test.sub_step_log('5.2 DD a file inside guest')
    cmd_dd = 'dd if=/dev/zero of=file1 bs=1M count=100 oflag=direct'
    output = dst_guest_session.guest_cmd_output(cmd=cmd_dd, timeout=600)
    if not output or re.findall('error', output):
        dst_serial.test_error('Failed to dd a file inside guest')

    test.sub_step_log('check dmesg info')
    cmd = 'dmesg'
    output = dst_guest_session.guest_cmd_output(cmd=cmd)
    if re.findall(r'Call Trace:', output) or not output:
        dst_guest_session.test_error('Guest hit call trace')

    test.main_step_log('5.3 Reboot guest')
    dst_guest_session.guest_cmd_output(cmd='reboot')
    dst_guest_ip = dst_serial.serial_login()
    dst_guest_session = GuestSession(case_id=id, params=params,ip=dst_guest_ip)

    test.sub_step_log('5.4. Ping external host / copy file '
                      'between guest and host')
    external_host_ip = 'www.redhat.com'
    cmd_ping = 'ping %s -c 10' % external_host_ip
    output = dst_guest_session.guest_cmd_output(cmd=cmd_ping)
    if re.findall(r'100% packet loss', output):
        dst_serial.test_error('Ping failed')

    test.sub_step_log('5.5 Shutdown guest')
