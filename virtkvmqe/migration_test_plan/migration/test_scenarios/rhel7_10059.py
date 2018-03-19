import os, sys
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.extend([BASE_DIR])
import time
from utils_host import HostSession
from utils_guest import GuestSession
from monitor import RemoteSerialMonitor, RemoteQMPMonitor
import re
from vm import CreateTest
from utils_migration import ping_pong_migration
import threading
import Queue

def scp_thread(session, queue, src_file, dst_file, src_ip=None, dst_ip=None, timeout=300):
    session.host_cmd_scp(src_file, dst_file, src_ip, dst_ip, timeout)

def run_case(params):
    SRC_HOST_IP = params.get('src_host_ip')
    DST_HOST_IP = params.get('dst_host_ip')
    qmp_port = int(params.get('vm_cmd_base')['qmp'][0].split(',')[0].split(':')[2])
    serail_port = int(params.get('vm_cmd_base')['serial'][0].split(',')[0].split(':')[2])
    share_images_dir = params.get('share_images_dir')
    incoming_port = params.get('incoming_port')

    queue = Queue.Queue()

    test = CreateTest(case_id='rhel7_10059', params=params)
    id = test.get_id()
    src_host_session = HostSession(id, params)

    test.main_step_log('1. Start source vm')
    src_qemu_cmd = params.create_qemu_cmd()

    src_host_session.boot_guest(src_qemu_cmd, vm_alias='src')

    src_remote_qmp = RemoteQMPMonitor(id, params, SRC_HOST_IP, qmp_port)

    test.sub_step_log('Connecting to src serial')
    src_serial = RemoteSerialMonitor(id, params, SRC_HOST_IP, serail_port)
    SRC_GUEST_IP = src_serial.serial_login()
    DST_GUEST_IP = SRC_GUEST_IP

    src_guest_session = GuestSession(case_id=id, params=params, ip=SRC_GUEST_IP)
    test.sub_step_log('Check dmesg info ')
    cmd = 'dmesg'
    output = src_guest_session.guest_cmd_output(cmd)
    if re.findall(r'Call Trace:', output):
        src_guest_session.test_error('Guest hit call trace')

    test.main_step_log('2. Create a file in host')

    src_host_session.host_cmd(cmd='rm -rf /home/file_host')
    src_host_session.host_cmd(cmd='rm -rf /home/file_host2')

    cmd = 'dd if=/dev/urandom of=/home/file_host bs=1M count=5000 oflag=direct'

    src_host_session.host_cmd_output(cmd, timeout=600)

    test.main_step_log('3. Start des vm in migration-listen mode: "-incoming tcp:0:****"')

    params.vm_base_cmd_add('incoming', 'tcp:0:%s' %incoming_port)
    dst_qemu_cmd = params.create_qemu_cmd()

    src_host_session.boot_remote_guest(ip=DST_HOST_IP, cmd=dst_qemu_cmd, vm_alias='dst')

    dst_remote_qmp = RemoteQMPMonitor(id, params, DST_HOST_IP, qmp_port)

    test.main_step_log('4. Transfer file from host to guest')

    src_guest_session.guest_cmd_output(cmd='rm -rf /home/file_guest')
    thread = threading.Thread(target=scp_thread,
                              args=(src_host_session, queue, '/home/file_host', '/home/file_guest', None, SRC_GUEST_IP, 600))

    thread.name = 'scp_thread'
    thread.daemon = True
    thread.start()

    test.main_step_log('5. Start migration')
    cmd = '{"execute":"migrate", "arguments": { "uri": "tcp:%s:%s" }}' %(DST_HOST_IP, incoming_port)
    src_remote_qmp.qmp_cmd_output(cmd=cmd)

    test.sub_step_log('Check the status of migration')
    cmd = '{"execute":"query-migrate"}'
    while True:
        output = src_remote_qmp.qmp_cmd_output(cmd=cmd)
        if re.findall(r'"remaining": 0', output):
            break
        if re.findall(r'"status": "failed"', output):
            src_remote_qmp.test_error('migration failed')
        time.sleep(3)

    test.sub_step_log('Login dst guest')

    dst_guest_session = GuestSession(case_id=id, params=params, ip=DST_GUEST_IP)
    dst_guest_session.guest_cmd_output(cmd='dmesg')

    test.main_step_log('6. Ping-pong migrate until file transfer finished')
    src_remote_qmp, dst_remote_qmp = ping_pong_migration(params=params, test=test, cmd=src_qemu_cmd, id=id, src_host_session=src_host_session,
                        src_remote_qmp=src_remote_qmp, dst_remote_qmp=dst_remote_qmp,
                        src_ip=SRC_HOST_IP, src_port=qmp_port,
                        dst_ip=DST_HOST_IP, dst_port=qmp_port, migrate_port=incoming_port, even_times=4, query_cmd='pgrep -x scp')

    test.sub_step_log('Login dst guest after ping-pong migration')

    dst_guest_session = GuestSession(case_id=id, params=params, ip=DST_GUEST_IP)
    dst_guest_session.guest_cmd_output(cmd='dmesg')

    file_src_host_md5 = src_host_session.host_cmd_output(cmd='md5sum /home/file_host')
    file_guest_md5 = dst_guest_session.guest_cmd_output(cmd='md5sum /home/file_guest')

    if file_src_host_md5.split(' ')[0] != file_guest_md5.split(' ')[0]:
        test.test_error('Value of md5sum error!')

    test.main_step_log('7. Transfer file from guest to host')
    thread = threading.Thread(target=src_host_session.host_cmd_scp,
                              args=('/home/file_guest', '/home/file_host2',
                                    DST_GUEST_IP, None, 600))
    thread.name = 'scp_thread2'
    thread.daemon = True
    thread.start()

    test.main_step_log('8. Ping-Pong migration until file transfer finished.')
    src_remote_qmp, dst_remote_qmp = ping_pong_migration(params=params, test=test, cmd=src_qemu_cmd, id=id, src_host_session=src_host_session,
                        src_remote_qmp=src_remote_qmp, dst_remote_qmp=dst_remote_qmp,
                        src_ip=SRC_HOST_IP, src_port=qmp_port,
                        dst_ip=DST_HOST_IP, dst_port=qmp_port, migrate_port=4000, even_times=4, query_cmd='pgrep -x scp')

    test.main_step_log('9. Check md5sum after file transfer')

    file_src_host_md5 = src_host_session.host_cmd_output(cmd='md5sum /home/file_host')

    file_src_host2_md5 = src_host_session.host_cmd_output(cmd='md5sum /home/file_host2')

    if file_src_host_md5.split(' ')[0] != file_src_host2_md5.split(' ')[0] \
            and file_src_host_md5.split(' ')[0] != file_guest_md5.split(' ')[0] \
            and file_src_host2_md5.split(' ')[0] != file_guest_md5.split(' ')[0] :
        test.test_error('Value of md5sum error!')

    test.sub_step_log('Login dst guest after ping-pong migration')

    dst_guest_session = GuestSession(case_id=id, params=params, ip=DST_GUEST_IP)
    dst_guest_session.guest_cmd_output(cmd='dmesg')
