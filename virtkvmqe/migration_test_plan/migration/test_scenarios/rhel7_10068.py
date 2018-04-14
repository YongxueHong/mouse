from utils_host import HostSession
from utils_guest import GuestSession
from monitor import RemoteSerialMonitor, RemoteQMPMonitor
import re
from vm import CreateTest
from utils_migration import query_migration

def run_case(params):
    src_host_ip = params.get('src_host_ip')
    dst_host_ip = params.get('dst_host_ip')
    qmp_port = int(params.get('qmp_port'))
    serial_port = int(params.get('serial_port'))
    incoming_port = params.get('incoming_port')
    test = CreateTest(case_id='rhel7_10068', params=params)
    id = test.get_id()

    test.main_step_log('1.Start VM in src host')
    params.vm_base_cmd_add('S', 'None')
    params.vm_base_cmd_add('monitor','tcp:0:5555,server,nowait')

    src_host_session = HostSession(id, params)
    src_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_guest(cmd=src_qemu_cmd, vm_alias='src')

    test.sub_step_log('Check the status of src guest')
    src_remote_qmp = RemoteQMPMonitor(id, params, src_host_ip, qmp_port)

    test.main_step_log('2. Start listening mode in dst host ')
    params.vm_base_cmd_del('S','None')
    params.vm_base_cmd_del('monitor','tcp:0:5555,server,nowait')
    incoming_val = 'tcp:0:%s' % (incoming_port)
    params.vm_base_cmd_add('incoming', incoming_val)
    dst_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_remote_guest(cmd=dst_qemu_cmd, ip=dst_host_ip, 
                                       vm_alias='dst')
    dst_remote_qmp = RemoteQMPMonitor(id, params, dst_host_ip, qmp_port)

    test.main_step_log('3. Start live migration with '
                       'running below script on src host')
    cmd='echo c | nc localhost 5555; sleep 0.6; ' \
        'echo migrate tcp:%s:%s | nc localhost 5555' % \
        (dst_host_ip, incoming_port)
    src_host_session.host_cmd(cmd=cmd)
    
    test.main_step_log('4.Check guest on des, guest should work well')
    migration_flag = query_migration(src_remote_qmp)
    if (migration_flag == False):
        src_remote_qmp.test_error('migration timeout')
    output = dst_remote_qmp.qmp_cmd_output('{"execute":"query-status"}')
    if not re.findall(r'"status": "running"', output):
            dst_remote_qmp.test_error('migration status error')

    test.main_step_log('5.Reboot guest, guest should work well.')
    dst_serial = RemoteSerialMonitor(case_id=id, params=params, ip=dst_host_ip,
                                     port=serial_port)
    cmd = 'dmesg'
    output = dst_serial.serial_cmd_output(cmd)
    if re.findall(r'Call Trace:', output):
        test.test_error('Guest hit call trace')
    dst_serial.serial_cmd(cmd='reboot')
    dst_guest_ip=dst_serial.serial_login()
    external_host_ip = dst_host_ip
    dst_guest_session = GuestSession(case_id=id, params=params,
                                     ip=dst_guest_ip)
    cmd_ping = 'ping %s -c 10' % external_host_ip
    output = dst_guest_session.guest_cmd_output(cmd=cmd_ping)
    if re.findall(r'100% packet loss', output):
        dst_guest_session.test_error('Ping failed')
    test.sub_step_log('check dmesg info')
    cmd = 'dmesg'
    output = dst_guest_session.guest_cmd_output(cmd=cmd)
    if re.findall(r'Call Trace:', output) or not output:
        dst_guest_session.test_error('Guest hit call trace')

    test.sub_step_log('quit qemu on src end and shutdown vm on dst end')
    output = src_remote_qmp.qmp_cmd_output('{"execute":"quit"}',
                                           recv_timeout=3)
    if output:
        src_remote_qmp.test_error('Failed to quit qemu on src host')

    output = dst_serial.serial_cmd_output('shutdown -h now')
    if re.findall(r'Call trace', output):
        dst_serial.test_error('Guest hit Call trace during shutdown')
