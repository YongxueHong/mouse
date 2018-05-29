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
    incoming_port = params.get('incoming_port')
    test = CreateTest(case_id='rhel7_10056_win', params=params)
    id = test.get_id()
    src_host_session = HostSession(id, params)
    speed = '1073741824'
    active_timeout = 300
    stress_time = 120

    test.main_step_log('1. Start VM with high load, with each method is ok')
    src_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_guest(cmd=src_qemu_cmd, vm_alias='src')
    src_remote_qmp = RemoteQMPMonitor(id, params, src_host_ip, qmp_port)

    test.sub_step_log('Wait 90s for guest boot up')
    time.sleep(90)

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
    cmd = '{"execute":"migrate", "arguments": {"uri": "tcp:%s:%s"}}' % \
          (dst_host_ip, incoming_port)
    src_remote_qmp.qmp_cmd_output(cmd)

    test.main_step_log('3.Enlarge migration speed')
    flag_active = utils_migration.query_status(remote_qmp=src_remote_qmp,
                                               status='active')
    if (flag_active == False):
        src_remote_qmp.test_error('Migration could not be active within %d'
                                  % active_timeout)
    utils_migration.change_speed(remote_qmp=src_remote_qmp, speed_val=speed)

    test.sub_step_log('3.2 Check migration status again')
    flag_1 = utils_migration.query_migration(remote_qmp=src_remote_qmp)
    if (flag_1 == False):
        test.test_error('Migration timeout after changing speed')

    test.main_step_log('4. After migration, check dst guest status and reboot guest')
    test.sub_step_log('4.1 Check dst guest status')
    status = dst_remote_qmp.qmp_cmd_output('{"execute":"query-status"}')
    if '\"status\": \"running\"' not in status:
        dst_remote_qmp.test_error('Dst vm is not running')

    test.sub_step_log('4.2. Reboot guest')
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
