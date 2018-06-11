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
    test = CreateTest(case_id='rhel7_49062', params=params)
    id = test.get_id()
    src_host_session = HostSession(id, params)
    val_M = '2000'
    val_s = '10000'

    test.main_step_log('1. Launch guest on source host')
    src_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_guest(cmd=src_qemu_cmd, vm_alias='src')
    src_remote_qmp = RemoteQMPMonitor(id, params, src_host_ip, qmp_port)
    src_serial = RemoteSerialMonitor(id, params, src_host_ip, serial_port)
    src_guest_ip = src_serial.serial_login()
    src_guest_session = GuestSession(case_id=id, params=params,
                                     ip=src_guest_ip)

    test.sub_step_log('2. stress guest(migration could finish for scenario1/'
                      'could never finish for scenario 2)')
    utils_migration.stressapptest(guest_session=src_guest_session,
                                  val_M=val_M, val_s=val_s)

    test.main_step_log('3. Launch guest on destination host')
    incoming_val = 'tcp:0:%s' % incoming_port
    params.vm_base_cmd_add('incoming', incoming_val)
    dst_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_remote_guest(cmd=dst_qemu_cmd, ip=dst_host_ip,
                                       vm_alias='dst')
    dst_remote_qmp = RemoteQMPMonitor(id, params, dst_host_ip, qmp_port)

    test.main_step_log('4. On source qemu & dst qemu, set postcopy mode on')
    test.sub_step_log('set src host postcopy-ram on')
    utils_migration.set_migration_capabilities(remote_qmp=src_remote_qmp,
                                               capabilities='postcopy-ram',
                                               state='true')
    test.sub_step_log('set dst host postcopy-ram on')
    utils_migration.set_migration_capabilities(remote_qmp=dst_remote_qmp,
                                               capabilities='postcopy-ram',
                                               state='true')

    test.main_step_log('5. migrate guest to destination')
    cmd = '{"execute":"migrate", "arguments": { "uri": "tcp:%s:%s" }}' \
          % (dst_host_ip, incoming_port)
    src_remote_qmp.qmp_cmd_output(cmd=cmd)

    test.sub_step_log('6. Change into postcopy mode')
    output = utils_migration.query_migration(remote_qmp=src_remote_qmp,
                                             chk_timeout=300)
    if (output == False):
        test.test_print('Migration can not finish without postcopy')
        cmd = '{"execute":"migrate-start-postcopy"}'
        src_remote_qmp.qmp_cmd_output(cmd=cmd)
        info = utils_migration.query_migration(remote_qmp=src_remote_qmp)
        if (info == False):
            test.test_error('Migration timeout with postcopy')
    else:
        test.test_print('Migration finished without postcopy')

    test.main_step_log('7. Check guest status before and after migration finished')
    dst_serial = RemoteSerialMonitor(id, params, dst_host_ip, serial_port)
    output = dst_serial.serial_cmd_output('dmesg')
    if re.findall(r'Call Trace:', output):
        test.test_error('Guest hit call trace after migration')
    dst_serial.serial_cmd(cmd='reboot')
    dst_guest_ip = dst_serial.serial_login()
    dst_guest_session = GuestSession(case_id=id, params=params,
                                     ip=dst_guest_ip)
    dst_guest_session.guest_ping_test(dst_ip='www.redhat.com', count=10)

    test.main_step_log('8. Check postcopy statistics')
    cmd = '{"execute":"query-migrate"}'
    output = src_remote_qmp.qmp_cmd_output(cmd=cmd)
    if re.findall(r'"postcopy-requests": 0', output):
        test.test_error('the value postcopy-requests is zero')
    else:
        test.test_print('the value postcopy-requests is not zero')

    test.main_step_log('9.repeat step2~8 to migrate guest back to source host.')
    test.sub_step_log('9.1 quit src qemu')
    src_remote_qmp.qmp_cmd_output(cmd='{"execute":"quit"}')
    src_host_session.check_guest_process(src_ip=src_host_ip)

    test.sub_step_log('9.2 boot src guest again')
    src_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_guest(cmd=src_qemu_cmd, vm_alias='src')
    src_remote_qmp = RemoteQMPMonitor(id, params, src_host_ip, qmp_port)

    test.sub_step_log('9.3 stress guest')
    utils_migration.stressapptest(guest_session=dst_guest_session,
                                  val_M=val_M, val_s=val_s)

    test.sub_step_log('9.4 set src and dst postcopy-ram on')
    test.sub_step_log('set src host postcopy-ram on')
    utils_migration.set_migration_capabilities(remote_qmp=src_remote_qmp,
                                               capabilities='postcopy-ram',
                                               state='true')
    test.sub_step_log('set dst host postcopy-ram on')
    utils_migration.set_migration_capabilities(remote_qmp=dst_remote_qmp,
                                               capabilities='postcopy-ram',
                                               state='true')

    test.sub_step_log('9.5 migrate guest to source')
    cmd = '{"execute":"migrate", "arguments": { "uri": "tcp:%s:%s" }}' \
          % (src_host_ip, incoming_port)
    dst_remote_qmp.qmp_cmd_output(cmd=cmd)

    test.sub_step_log('9.6. Change into postcopy mode')
    output = utils_migration.query_migration(remote_qmp=dst_remote_qmp,
                                             chk_timeout=300)
    if (output == False):
        test.test_print('Migration can not finish without postcopy')
        cmd = '{"execute":"migrate-start-postcopy"}'
        dst_remote_qmp.qmp_cmd_output(cmd=cmd)
        info = utils_migration.query_migration(remote_qmp=dst_remote_qmp)
        if (info == False):
            test.test_error('Migration timeout with postcopy')
    else:
        test.test_print('Migration finished without postcopy')

    test.main_step_log('9.7. Check guest status before and after migration finished')
    src_serial = RemoteSerialMonitor(id, params, src_host_ip, serial_port)
    output = src_serial.serial_cmd_output('dmesg')
    if re.findall(r'Call Trace:', output):
        test.test_error('Guest hit call trace after migration')
    src_serial.serial_cmd(cmd='reboot')
    src_guest_ip = src_serial.serial_login()
    src_guest_session = GuestSession(case_id=id, params=params,
                                     ip=src_guest_ip)
    src_guest_session.guest_ping_test(dst_ip='www.redhat.com', count=10)

    test.main_step_log('9.8. Check postcopy statistics')
    cmd = '{"execute":"query-migrate"}'
    output = dst_remote_qmp.qmp_cmd_output(cmd=cmd)
    if re.findall(r'"postcopy-requests": 0', output):
        test.test_error('the value postcopy-requests is zero')
    else:
        test.test_print('the value postcopy-requests is not zero')
