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
    share_images_dir = params.get('share_images_dir')
    test = CreateTest(case_id='rhel7_10022_win', params=params)
    id = test.get_id()
    guest_name = test.guest_name

    test.main_step_log('1. Boot a guest.')
    src_host_session = HostSession(id, params)
    src_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_guest(cmd=src_qemu_cmd, vm_alias='src')

    test.sub_step_log('Wait 90s for guest boot up')
    time.sleep(90)
    test.sub_step_log('Check the status of src guest')
    src_remote_qmp = RemoteQMPMonitor(id, params, src_host_ip, qmp_port)

    test.main_step_log('2. Save VM state into a compressed file in host')
    src_remote_qmp.qmp_cmd_output('{"execute":"stop"}')
    src_remote_qmp.qmp_cmd_output('{"execute":"query-status"}')
    src_remote_qmp.qmp_cmd_output('{"execute":"migrate_set_speed", '
                                  '"arguments": { "value": 104857600 }}')

    statefile = '/%s/STATEFILE.gz' % share_images_dir
    src_host_session.host_cmd(cmd=('rm -rf %s' % statefile))
    src_remote_qmp.qmp_cmd_output('{"execute":"migrate",'
                                  '"arguments":{"uri": "exec:gzip -c > %s"}}'
                                  % statefile, recv_timeout=5)

    test.sub_step_log('Check the status of migration')
    info = query_migration(src_remote_qmp)
    if (info == True):
        test.test_print('Migration succeed')
    if (info == False):
        test.test_error('Migration timeout')

    src_remote_qmp.qmp_cmd_output('{"execute":"quit"}')
    time.sleep(3)
    src_chk_cmd = 'ps -aux | grep %s | grep -vE grep' % guest_name
    output = src_host_session.host_cmd_output(cmd=src_chk_cmd,
                                              echo_cmd=False,
                                              verbose=False)
    if output:
        src_pid = re.split(r"\s+", output)[1]
        src_host_session.host_cmd_output('kill -9 %s' % src_pid,
                                         echo_cmd=False)

    test.main_step_log('3. Load the file in dest host(src host).')
    params.vm_base_cmd_add('incoming', '"exec: gzip -c -d %s"' % statefile)
    dst_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_guest(cmd=dst_qemu_cmd, vm_alias='dst')

    test.sub_step_log('Check dst guest status')
    dst_remote_qmp = RemoteQMPMonitor(id, params, dst_host_ip, qmp_port)
    while True:
        output = dst_remote_qmp.qmp_cmd_output('{"execute":"query-status"}')
        if re.findall(r'"paused"', output):
            break
        time.sleep(3)

    dst_remote_qmp.qmp_cmd_output('{"execute":"cont"}')
    status = dst_remote_qmp.qmp_cmd_output('{"execute":"query-status"}')
    if '\"status\": \"running\"' not in status:
        dst_remote_qmp.test_error('Dst vm is not running')

    dst_remote_qmp.qmp_cmd_output('{"execute":"quit"}')

