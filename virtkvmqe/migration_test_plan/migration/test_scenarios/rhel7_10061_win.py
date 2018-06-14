import time
from utils_host import HostSession
from monitor import RemoteQMPMonitor
import re
from vm import CreateTest
import utils_migration

def run_case(params):
    src_host_ip = params.get('src_host_ip')
    dst_host_ip = params.get('dst_host_ip')
    qmp_port = int(params.get('qmp_port'))
    serial_port = int(params.get('serial_port'))
    incoming_port = params.get('incoming_port')
    test = CreateTest(case_id='rhel7_10061_win', params=params)
    id = test.get_id()
    guest_name = test.guest_name
    src_host_session = HostSession(id, params)

    test.main_step_log('1. Start VM in the src host')
    src_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_guest(cmd=src_qemu_cmd, vm_alias='src')
    src_remote_qmp = RemoteQMPMonitor(id, params, src_host_ip, qmp_port)
    test.sub_step_log('Wait 90s for guest boot up')
    time.sleep(90)

    test.sub_step_log('1.1 Connecting to src serial --- ignore for windows guest')
    #src_serial = RemoteSerialMonitor(id, params, src_host_ip, serial_port)
    #src_guest_ip = src_serial.serial_login()
    #src_guest_session = GuestSession(case_id=id, params=params, ip=src_guest_ip)

    test.sub_step_log('1.2 Running stress in src guest --- ignore for windows guest')
    #utils_migration.stress_test(guest_session=src_guest_session)

    test.main_step_log('2. Start listening mode in the dst host.')
    incoming_val = 'tcp:0:%s' % incoming_port
    params.vm_base_cmd_add('incoming', incoming_val)
    dst_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_remote_guest(cmd=dst_qemu_cmd, ip=dst_host_ip,
                                       vm_alias='dst')
    dst_remote_qmp = RemoteQMPMonitor(id, params, dst_host_ip, qmp_port)

    test.main_step_log('3. Do live migration')
    cmd = '{"execute":"migrate", "arguments": {"uri": "tcp:%s:%s"}}' % (
    dst_host_ip, incoming_port)
    src_remote_qmp.qmp_cmd_output(cmd=cmd)

    test.sub_step_log('Check the status of migration')
    flag_active = utils_migration.query_status(remote_qmp=src_remote_qmp,
                                               status='active')
    if (flag_active == False):
        test.test_error('Migration is not active')

    test.main_step_log('4. During migration in progress, cancel migration')
    cmd = '{"execute":"migrate_cancel"}'
    src_remote_qmp.qmp_cmd_output(cmd=cmd, recv_timeout=3)
    output = src_remote_qmp.qmp_cmd_output('{"execute":"query-migrate"}',
                                           recv_timeout=3)
    if re.findall(r'"status": "cancelled"', output):
        src_remote_qmp.test_print('Src cancel migration successfully')
    else:
        src_remote_qmp.test_error('Failed to cancel migration')

    test.main_step_log('5. Start listening mode againg in the dst host')
    test.sub_step_log('5.1 Check if the dst qemu quit automatically')
    dst_chk_cmd = 'ssh root@%s ps -axu | grep %s | grep -v grep' \
                  % (dst_host_ip, guest_name)
    output = src_host_session.host_cmd_output(cmd=dst_chk_cmd)
    if not output:
        src_host_session.test_print('DST QEMU quit automatically after '
                                    'src cancelling migration')
    else:
        src_host_session.test_error('DST QEMU does not quit automatically '
                                    'after src cancelling migration')
    test.sub_step_log('5.2 Start listening mode again in dst host')
    src_host_session.boot_remote_guest(cmd=dst_qemu_cmd, ip=dst_host_ip,
                                       vm_alias='dst')
    dst_remote_qmp = RemoteQMPMonitor(id, params, dst_host_ip, qmp_port)

    test.main_step_log('6. Do live migration again')
    output = utils_migration.do_migration(remote_qmp=src_remote_qmp,
                                          migrate_port=incoming_port,
                                          dst_ip=dst_host_ip)
    if (output == False):
        test.test_error('Migration timeout')

    test.main_step_log('7. After migration succeed, '
                       'checking  the status of guest on the dst host')

    test.sub_step_log('7.1 Check dst guest status')
    status = dst_remote_qmp.qmp_cmd_output('{"execute":"query-status"}')
    if '\"status\": \"running\"' not in status:
        dst_remote_qmp.test_error('Dst vm is not running')

    test.sub_step_log('7.2 Reboot guest')
    dst_remote_qmp.qmp_cmd_output('{"execute":"system_reset"}')

    output = src_remote_qmp.qmp_cmd_output('{"execute":"quit"}', recv_timeout=3)
    if output:
        src_remote_qmp.test_error('Failed to quit qemu on src end')

    time.sleep(30)
    status = dst_remote_qmp.qmp_cmd_output('{"execute":"query-status"}')
    if '\"status\": \"running\"' not in status:
        dst_remote_qmp.test_error('Dst vm is not running after reboot')

    output = dst_remote_qmp.qmp_cmd_output('{"execute":"quit"}')
    if output:
        dst_remote_qmp.test_error('Failed to quit qemu on dst end')

    