import time
from utils_host import HostSession
from monitor import RemoteQMPMonitor
import re
from vm import CreateTest
from utils_migration import query_migration

def run_case(params):
    src_host_ip = params.get('src_host_ip')
    dst_host_ip = src_host_ip
    qmp_port = int(params.get('qmp_port'))
    serial_port = int(params.get('serial_port'))
    vnc_port = int(params.get('vnc_port'))
    share_images_dir = params.get('share_images_dir')
    test = CreateTest(case_id='rhel7_10075', params=params)
    id = test.get_id()
    src_host_session = HostSession(id, params)
    query_timeout = 1200

    test.main_step_log('1. Boot a guest on source host.')
    src_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_guest(cmd=src_qemu_cmd, vm_alias='src')
    src_remote_qmp = RemoteQMPMonitor(id, params, src_host_ip, qmp_port)

    test.sub_step_log('1.1 Connecting to src serial --- ignore for windows guest')

    test.main_step_log('2. start listening port in the same host')
    vnc_port_new = int(vnc_port + 1)
    params.vm_base_cmd_update('vnc', ':%d' % vnc_port, ':%d' % vnc_port_new)
    qmp_port_new = int(qmp_port + 1)
    params.vm_base_cmd_update('qmp', 'tcp:0:%d,server,nowait' % qmp_port,
                              'tcp:0:%d,server,nowait' % qmp_port_new)
    serial_port_new = int(serial_port + 1)
    params.vm_base_cmd_update('serial', 'tcp:0:%d,server,nowait' % serial_port,
                              'tcp:0:%d,server,nowait' % serial_port_new)
    output = src_host_session.host_cmd_output('rm -f %s/unix' % share_images_dir)
    if output:
        test.test_error('Failed to delete the existed unix socket')
    incoming_val = 'unix:%s/unix' % share_images_dir
    params.vm_base_cmd_add('incoming', incoming_val)

    dst_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_guest(cmd=dst_qemu_cmd, vm_alias='dst')
    dst_remote_qmp = RemoteQMPMonitor(id, params, dst_host_ip, qmp_port_new)

    test.main_step_log('3. do live migration')
    test.sub_step_log('3.1 Check whether the socket exists')
    output = src_host_session.host_cmd_output('ls %s | grep unix'
                                              % share_images_dir)
    if re.findall(r'unix', output):
        test.test_print('unix socket exists')
    else:
        test.test_error('Unix socket does not exist')

    test.sub_step_log('3.2 Begin to do migration')
    cmd = '{"execute":"migrate","arguments":{"uri":"unix:%s/unix"}}' \
          % share_images_dir
    src_remote_qmp.qmp_cmd_output(cmd=cmd, recv_timeout=6)

    test.sub_step_log('Check the status of migration')
    flag = query_migration(remote_qmp=src_remote_qmp,
                           chk_timeout=query_timeout)
    if (flag == False):
        test.test_error('Migration timeout in %d' % query_timeout)
        
    test.main_step_log('4. After migration, check if guest works well.')
    test.sub_step_log('4.1 Check dst guest status')
    status = dst_remote_qmp.qmp_cmd_output('{"execute":"query-status"}')
    if '\"status\": \"running\"' not in status:
        dst_remote_qmp.test_error('Dst vm is not running')

    test.sub_step_log('4.2. Reboot guest')
    dst_remote_qmp.qmp_cmd_output('{"execute":"system_reset"}')

    time.sleep(30)
    status = dst_remote_qmp.qmp_cmd_output('{"execute":"query-status"}')
    if '\"status\": \"running\"' not in status:
        dst_remote_qmp.test_error('Dst vm is not running after reboot')

    output = dst_remote_qmp.qmp_cmd_output('{"execute":"quit"}')
    if output:
        dst_remote_qmp.test_error('Failed to quit qemu on dst end')

    output = src_remote_qmp.qmp_cmd_output('{"execute":"quit"}', recv_timeout=3)
    if output:
        src_remote_qmp.test_error('Failed to quit qemu on src end')