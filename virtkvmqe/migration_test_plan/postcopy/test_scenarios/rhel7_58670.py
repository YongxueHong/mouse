from utils_host import HostSession
from utils_guest import GuestSession
from monitor import RemoteSerialMonitor, RemoteQMPMonitor
import re
from vm import CreateTest
import utils_migration
import time

def run_case(params):
    src_host_ip = params.get('src_host_ip')
    dst_host_ip = params.get('dst_host_ip')
    qmp_port = int(params.get('qmp_port'))
    serial_port = int(params.get('serial_port'))
    incoming_port = params.get('incoming_port')
    test = CreateTest(case_id='rhel7_58670', params=params)
    id = test.get_id()
    src_host_session = HostSession(id, params)
    val_M = '2000'
    val_s = '10000'
    ping_file = '/tmp/ping'

    test.main_step_log('1. Launch guest on source host')
    src_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_guest(cmd=src_qemu_cmd, vm_alias='src')
    src_remote_qmp = RemoteQMPMonitor(id, params, src_host_ip, qmp_port)
    src_serial = RemoteSerialMonitor(id, params, src_host_ip, serial_port)
    src_guest_ip = src_serial.serial_login()
    src_guest_session = GuestSession(case_id=id, params=params,
                                     ip=src_guest_ip)

    test.sub_step_log('2. stress guest')
    utils_migration.stressapptest(guest_session=src_guest_session,
                                  val_M=val_M, val_s=val_s)

    test.main_step_log('3. ping guest from host, keep it during whole '
                       'migration process')
    flag = False
    endtime =time.time() + 300
    while time.time() < endtime:
        output = src_host_session.host_cmd_output(cmd='pgrep ping')
        if output:
            src_host_session.host_cmd(cmd='pgrep ping | xargs kill -9')
        else:
            flag = True
            break
    if flag == False:
        test.test_error('Failed to kill existing ping process')

    cmd = 'ping %s > %s &' % (src_guest_ip, ping_file)
    src_host_session.host_cmd(cmd=cmd)

    test.main_step_log('4. Launch guest on destination host ')
    incoming_val = 'tcp:0:%s' % incoming_port
    params.vm_base_cmd_add('incoming', incoming_val)
    dst_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_remote_guest(cmd=dst_qemu_cmd, ip=dst_host_ip,
                                       vm_alias='dst')
    dst_remote_qmp = RemoteQMPMonitor(id, params, dst_host_ip, qmp_port)

    test.main_step_log('5. check postcopy capability on')
    test.sub_step_log('set src host postcopy-ram on')
    utils_migration.set_migration_capabilities(remote_qmp=src_remote_qmp,
                                               capabilities='postcopy-ram',
                                               state='true')
    test.sub_step_log('set dst host postcopy-ram on')
    utils_migration.set_migration_capabilities(remote_qmp=dst_remote_qmp,
                                               capabilities='postcopy-ram',
                                               state='true')

    test.main_step_log('6. migrate guest to destination')
    cmd = '{"execute":"migrate", "arguments": { "uri": "tcp:%s:%s" }}' \
          % (dst_host_ip, incoming_port)
    src_remote_qmp.qmp_cmd_output(cmd=cmd)

    test.main_step_log('7. Cancel migration')
    status = utils_migration.query_status(remote_qmp=src_remote_qmp,
                                          status='active')
    if (status == False):
        test.test_error('Migration status is not active')
    cmd = '{"execute":"migrate_cancel"}'
    src_remote_qmp.qmp_cmd_output(cmd=cmd)
    output = utils_migration.query_status(remote_qmp=src_remote_qmp,
                                          status='cancelled')
    if (output == True):
        test.test_print('Migration is cancelled successfully')
    if (output == False):
        test.test_error('Migration status is not cancelled')

    ping_pid = src_host_session.host_cmd_output(cmd='pgrep ping')
    if not ping_pid:
        test.test_error('The process of host ping guest is not existing')
    cmd = 'kill -9 %s' % ping_pid
    src_host_session.host_cmd(cmd=cmd)

    fo = open(ping_file, 'r')
    for line in fo.readlines():
        line = line.strip()
        if re.findall(r'unknown host name', line) \
                or re.findall(r'unreachable', line) \
                or re.findall(r'timeout', line):
            test.test_error('There is error in ping file')
    test.test_print('There is no error in ping file')
    fo.close()
