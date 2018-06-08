from __future__ import division
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
    test = CreateTest(case_id='rhel7_10044', params=params)
    id = test.get_id()
    src_host_session = HostSession(id, params)
    speed = 33554432
    downtime = 10000
    gap_downtime = 5000
    script = 'migration_dirtypage_2.c'

    test.main_step_log('1. guest with heavy memory load with either of '
                       'the following methods')
    src_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_guest(cmd=src_qemu_cmd, vm_alias='src')

    test.sub_step_log('1.1 Connecting to src serial')
    src_serial = RemoteSerialMonitor(id, params, src_host_ip, serial_port)
    src_guest_ip = src_serial.serial_login()
    src_guest_session = GuestSession(case_id=id, params=params,
                                     ip=src_guest_ip)
    src_remote_qmp = RemoteQMPMonitor(id, params, src_host_ip, qmp_port)

    test.sub_step_log('1.2 Run some program to generate dirty page')
    utils_migration.dirty_page_test(host_session=src_host_session,
                                    guest_session=src_guest_session,
                                    guest_ip=src_guest_ip, script=script)

    test.main_step_log('2. Start listening mode on dst host')
    incoming_val = 'tcp:0:%s' % incoming_port
    params.vm_base_cmd_add('incoming', incoming_val)
    dst_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_remote_guest(cmd=dst_qemu_cmd, ip=dst_host_ip,
                                       vm_alias='dst')
    dst_remote_qmp = RemoteQMPMonitor(id, params, dst_host_ip, qmp_port)

    test.main_step_log('3. Set a reasonable migrate downtime')
    downtime_cmd = '{"execute":"migrate-set-parameters","arguments":' \
                '{"downtime-limit": %d}}' % downtime
    src_remote_qmp.qmp_cmd_output(cmd=downtime_cmd)
    paras_chk_cmd = '{"execute":"query-migrate-parameters"}'
    output = src_remote_qmp.qmp_cmd_output(cmd=paras_chk_cmd)
    if re.findall(r'"downtime-limit": %d' % downtime, output):
        test.test_print('Set migration downtime successfully')
    else:
        test.test_error('Failed to change downtime')

    test.main_step_log('4. Do live migration.')
    check_info = utils_migration.do_migration(remote_qmp=src_remote_qmp,
                                              migrate_port=incoming_port,
                                              dst_ip=dst_host_ip,
                                              downtime_val=downtime,
                                              speed_val=speed)
    if (check_info == False):
        test.test_error('Migration timeout')

    test.main_step_log('5. when the "Migration status" is "completed", '
                       'check the "downtime" value')
    output = eval(src_remote_qmp.qmp_cmd_output('{"execute":"query-migrate"}'))
    real_downtime = int(output.get('return').get('downtime'))
    src_remote_qmp.test_print('The real downtime is: %d' % real_downtime)
    gap_cal = real_downtime-downtime
    if (gap_cal > gap_downtime):
        test.test_error('The real downtime value is much more than the value '
                        'that you set by %s milliseconds' % gap_downtime)
    else:
        test.test_print('The real downtime value is not much more than '
                        'the value that you set')

    test.main_step_log('6 Check the status of guest')
    test.sub_step_log('6.1. Reboot guest')
    dst_serial = RemoteSerialMonitor(id, params, dst_host_ip, serial_port)
    dst_remote_qmp.qmp_cmd_output('{"execute":"system_reset"}')
    dst_guest_ip = dst_serial.serial_login()

    test.sub_step_log('6.2 Ping external host')
    dst_guest_session = GuestSession(case_id=id, params=params,
                                     ip=dst_guest_ip)
    dst_guest_session.guest_ping_test('www.redhat.com', 10)

    test.sub_step_log('6.3 Shutdown guest successfully')
    dst_serial.serial_shutdown_vm()

    output = src_remote_qmp.qmp_cmd_output('{"execute":"quit"}')
    if output:
        src_remote_qmp.test_error('Failed to quit qemu on src end')
