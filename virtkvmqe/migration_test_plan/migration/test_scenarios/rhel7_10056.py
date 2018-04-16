import time
from utils_host import HostSession
from utils_guest import GuestSession
from monitor import RemoteSerialMonitor, RemoteQMPMonitor
import re
from vm import CreateTest
from utils_migration import do_migration, query_migration
import threading

def run_case(params):
    src_host_ip = params.get('src_host_ip')
    dst_host_ip = params.get('dst_host_ip')
    qmp_port = int(params.get('qmp_port'))
    serial_port = int(params.get('serial_port'))
    incoming_port = params.get('incoming_port')
    test = CreateTest(case_id='rhel7_10056', params=params)
    id = test.get_id()
    src_host_session = HostSession(id, params)
    speed = '1073741824'
    chk_time_1 = 20
    chk_time_2 = 1200
    stress_time = 120

    test.main_step_log('1. Start VM with high load, with each method is ok')
    src_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_guest(cmd=src_qemu_cmd, vm_alias='src')
    src_remote_qmp = RemoteQMPMonitor(id, params, src_host_ip, qmp_port)

    test.sub_step_log('1.1 Connecting to src serial')
    src_serial = RemoteSerialMonitor(id, params, src_host_ip, serial_port)
    src_guest_ip = src_serial.serial_login()
    src_guest_session = GuestSession(case_id=id, params=params, ip=src_guest_ip)

    test.sub_step_log('1.2 Running stress in src guest')
    chk_cmd = 'yum list installed | grep stress.`arch`'
    output = src_guest_session.guest_cmd_output(cmd=chk_cmd)
    if not output:
        install_cmd = 'yum install -y stress.`arch`'
        install_info = src_guest_session.guest_cmd_output(cmd=install_cmd)
        if re.findall('Complete', install_info):
            test.test_print('Guest install stress pkg successfully')
        else:
            test.test_error('Guest failed to install stress pkg')

    stress_cmd = 'stress --cpu 4 --vm 4 --vm-bytes 256M --timeout %d' \
                 % stress_time
    thread = threading.Thread(target=src_guest_session.guest_cmd_output,
                              args=(stress_cmd, 1200))
    thread.name = 'stress'
    thread.daemon = True
    thread.start()
    time.sleep(10)
    output = src_guest_session.guest_cmd_output('pgrep -x stress')
    if not output:
        test.test_error('Stress is not running in guest')

    test.main_step_log('2. Start listening mode on dst host and '
                       'on src host do migration')
    test.sub_step_log('2.1 Start listening mode on dst host')
    incoming_val = 'tcp:0:%s' % incoming_port
    params.vm_base_cmd_add('incoming', incoming_val)
    dst_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_remote_guest(cmd=dst_qemu_cmd, ip=dst_host_ip,
                                       vm_alias='dst')
    dst_remote_qmp = RemoteQMPMonitor(id, params, dst_host_ip, qmp_port)

    test.sub_step_log('2.2. Do live migration from src to dst')
    check_info = do_migration(remote_qmp=src_remote_qmp,
                              migrate_port=incoming_port, dst_ip=dst_host_ip,
                              chk_timeout=chk_time_1)

    test.main_step_log('3.Enlarge migration speed')
    test.sub_step_log('3.1 enlarge migration speed if it is not finished in %d'
                      % chk_time_1)
    if (check_info == False):
        test.test_print('Migration does not finish in %d seconds' % chk_time_1)
        speed_cmd = '{"execute":"migrate-set-parameters","arguments":' \
                    '{"max-bandwidth": %s}}' % speed
        src_remote_qmp.qmp_cmd_output(cmd=speed_cmd)
        paras_chk_cmd = '{"execute":"query-migrate-parameters"}'
        output = src_remote_qmp.qmp_cmd_output(cmd=paras_chk_cmd)
        if re.findall(r'"max-bandwidth": %s' % speed, output):
            test.test_print('Change speed successfully')
        else:
            test.test_error('Failed to change speed')
    test.sub_step_log('3.2 Check migration status again')
    flag_1 = query_migration(remote_qmp=src_remote_qmp,chk_timeout=chk_time_2)
    if (flag_1 == False):
        test.test_error('Migration timeout after changing speed')

    test.main_step_log('4. After migration, check if guest works well.')
    test.sub_step_log('4.1 Guest mouse and keyboard')

    test.sub_step_log('4.2. Reboot guest')
    dst_serial = RemoteSerialMonitor(id, params, dst_host_ip, serial_port)
    cmd = 'dmesg'
    output = dst_serial.serial_cmd_output(cmd=cmd)
    if re.findall(r'Call Trace:', output):
        test.test_error('Guest hit call trace')
    dst_serial.serial_cmd(cmd='reboot')
    dst_guest_ip = dst_serial.serial_login()

    test.sub_step_log('4.3 Ping external host')
    external_host_ip = 'www.redhat.com'
    cmd_ping = 'ping %s -c 10' % external_host_ip
    dst_guest_session = GuestSession(case_id=id, params=params, ip=dst_guest_ip)
    output = dst_guest_session.guest_cmd_output(cmd=cmd_ping)
    if re.findall(r'100% packet loss', output):
        dst_guest_session.test_error('Ping failed')

    test.sub_step_log('4.4 dd a file inside guest')
    cmd_dd = 'dd if=/dev/zero of=file1 bs=100M count=10 oflag=direct'
    output = dst_guest_session.guest_cmd_output(cmd=cmd_dd, timeout=600)
    if not output or re.findall('error', output):
        test.test_error('Failed to dd a file in guest')

    test.sub_step_log('4.5 Shutdown guest successfully')
    dst_serial.serial_shutdown_vm()

    output = src_remote_qmp.qmp_cmd_output('{"execute":"quit"}', recv_timeout=3)
    if output:
        src_remote_qmp.test_error('Failed to quit qemu on src end')