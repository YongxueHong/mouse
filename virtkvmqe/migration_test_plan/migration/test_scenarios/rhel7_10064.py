import time
from utils_host import HostSession
from utils_guest import GuestSession
from monitor import RemoteSerialMonitor, RemoteQMPMonitor
import re
from vm import CreateTest
import utils_migration

def run_case(params):
    src_host_ip = params.get('src_host_ip')
    dst_host_ip = params.get('dst_host_ip')
    qmp_port = int(params.get('qmp_port'))
    serial_port = int(params.get('serial_port'))
    incoming_port = params.get('incoming_port')
    paused_timeout = 60

    test = CreateTest(case_id='rhel7_10064', params=params)
    id = test.get_id()
    src_host_session = HostSession(id, params)
    src_qemu_cmd = params.create_qemu_cmd()

    test.main_step_log('1. Start VM in src host')
    src_host_session.boot_guest(cmd=src_qemu_cmd, vm_alias='src')
    src_remote_qmp = RemoteQMPMonitor(id, params, src_host_ip, qmp_port)

    test.sub_step_log('Connecting to src serial')
    src_serial = RemoteSerialMonitor(id, params, src_host_ip, serial_port)
    src_guest_ip = src_serial.serial_login()

    src_guest_session = GuestSession(case_id=id, params=params,
                                     ip=src_guest_ip)
    test.sub_step_log('Check dmesg info ')
    cmd = 'dmesg'
    output = src_guest_session.guest_cmd_output(cmd)
    if re.findall(r'Call Trace:', output):
        src_guest_session.test_error('Guest hit call trace')

    test.main_step_log('2. Start listening mode in dst host ')
    incoming_val = 'tcp:0:%s' % (incoming_port)
    params.vm_base_cmd_add('incoming', incoming_val)
    dst_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_remote_guest(cmd=dst_qemu_cmd,ip=dst_host_ip,
                                       vm_alias='dst')
    dst_remote_qmp = RemoteQMPMonitor(id, params, dst_host_ip, qmp_port)

    test.main_step_log('3. Do I/O operations load(iozone) in the guest')
    test.sub_step_log('run iozone -a')
    utils_migration.iozone_test(guest_session=src_guest_session)

    test.main_step_log('4. Stop guest on src guest before migration')
    cmd = '{"execute":"stop"}'
    src_remote_qmp.qmp_cmd_output(cmd)
    flag_paused = False
    end_time = time.time() + paused_timeout
    while time.time() < end_time:
        output = src_remote_qmp.qmp_cmd_output('{"execute":"query-status"}',
                                               recv_timeout=3)
        if re.findall(r'"status": "paused"', output):
            flag_paused = True
            break
    if (flag_paused == False):
        test.test_error('Guest could not become to paused within %d'
                        % paused_timeout)

    test.main_step_log('5. Start migration from src  to dst host')
    flag = utils_migration.do_migration(src_remote_qmp, incoming_port, dst_host_ip)
    if (flag == False):
        test.test_error('migration timeout')
   
    test.main_step_log('6.After migration finished ,check guests status.')
    flag_paused = False
    end_time = time.time() + paused_timeout
    while time.time() < end_time:
        output = dst_remote_qmp.qmp_cmd_output('{"execute":"query-status"}')
        if re.findall(r'"status": "paused"', output):
            flag_paused = True
            break
    if (flag_paused == False):
        test.test_error('Guest is not paused on dst side '
                        'after migration finished')

    dst_remote_qmp.qmp_cmd_output('{"execute":"cont"}')
    output=dst_remote_qmp.qmp_cmd_output('{"execute":"query-status"}')
    if not re.findall(r'"status": "running"', output):
        dst_remote_qmp.test_error('migration status Error')

    test.main_step_log('7. Check if guest works well.')
    test.sub_step_log('7.1 Guest mouse and keyboard.')
    test.sub_step_log('7.2 Check dmesg info ')
    dst_serial = RemoteSerialMonitor(case_id=id, params=params, ip=dst_host_ip,
                                     port=serial_port)
    cmd = 'dmesg'
    output = dst_serial.serial_cmd_output(cmd)
    if re.findall(r'Call Trace:', output):
        test.test_error('Guest hit call trace')

    test.sub_step_log('8. Reboot and then shutdown guest.')
    dst_serial.serial_cmd(cmd='reboot')
    dst_guest_ip=dst_serial.serial_login()
    guest_session = GuestSession(case_id=id, params=params, ip=dst_guest_ip)
    test.sub_step_log(' Can access guest from external host')

    guest_session.guest_ping_test('www.redhat.com', 10)

    test.sub_step_log('quit qemu on src end and shutdown vm on dst end')
    output = src_remote_qmp.qmp_cmd_output('{"execute":"quit"}',
                                           recv_timeout=3)
    if output:
        src_remote_qmp.test_error('Failed to quit qemu on src host')

    dst_serial.serial_shutdown_vm()

