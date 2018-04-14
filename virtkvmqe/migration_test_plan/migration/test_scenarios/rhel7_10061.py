import time
from utils_host import HostSession
from utils_guest import GuestSession
from monitor import RemoteSerialMonitor, RemoteQMPMonitor
import re
from vm import CreateTest
from utils_migration import do_migration, query_migration
import threading

def run_case(params):
    src_host_ip = params.get('src_host_ip')
    dst_host_ip = params.get('dst_host_ip')
    qmp_port = int(params.get('qmp_port'))
    serial_port = int(params.get('serial_port'))
    incoming_port = params.get('incoming_port')
    test = CreateTest(case_id='rhel7_10061', params=params)
    id = test.get_id()
    guest_name = test.guest_name
    src_host_session = HostSession(id, params)
    downtime = '20000'
    speed = '1073741824'
    chk_time_1 = 20
    chk_time_2 = 1200

    test.main_step_log('1. Start VM in the src host, guest running stress')
    src_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_guest(cmd=src_qemu_cmd, vm_alias='src')
    src_remote_qmp = RemoteQMPMonitor(id, params, src_host_ip, qmp_port)

    test.sub_step_log('1.1 Connecting to src serial')
    src_serial = RemoteSerialMonitor(id, params, src_host_ip, serial_port)
    src_guest_ip = src_serial.serial_login()
    src_guest_session = GuestSession(case_id=id, params=params, ip=src_guest_ip)

    test.sub_step_log('1.2 Running stress in src guest')
    chk_cmd = 'yum list installed | grep stress.`arch`'
    output = src_guest_session.guest_cmd_output(cmd=chk_cmd)
    if not output:
        install_cmd = 'yum install -y stress.`arch`'
        install_info = src_guest_session.guest_cmd_output(cmd=install_cmd)
        if re.findall('Complete', install_info):
            test.test_print('Guest install stress pkg successfully')
        else:
            test.test_error('Guest failed to install stress pkg')

    stress_cmd = 'stress --cpu 4 --vm 4 --vm-bytes 256M'
    thread = threading.Thread(target=src_guest_session.guest_cmd_output,
                              args=(stress_cmd, 1200))
    thread.name = 'stress'
    thread.daemon = True
    thread.start()
    time.sleep(10)
    output = src_guest_session.guest_cmd_output('pgrep -x stress')
    if not output:
        test.test_error('Stress is not running in guest')

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
    cmd = '{"execute":"query-migrate"}'
    while True:
        output = src_remote_qmp.qmp_cmd_output(cmd=cmd)
        if re.findall('"status": "active"', output):
            break

    test.main_step_log('4. During migration in progress, cancel migration')
    cmd = '{"execute":"migrate_cancel"}'
    src_remote_qmp.qmp_cmd_output(cmd=cmd, recv_timeout=5)
    output = src_remote_qmp.qmp_cmd_output('{"execute":"query-migrate"}')
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
    flag = do_migration(remote_qmp=src_remote_qmp,
                        migrate_port=incoming_port, dst_ip=dst_host_ip,
                        chk_timeout=chk_time_1)
    if (flag == False):
        test.sub_step_log('6.1 Enlarge the value of downtime and speed')
        downtime_cmd = '{"execute":"migrate-set-parameters","arguments":' \
                       '{"downtime-limit": %s}}' % downtime
        src_remote_qmp.qmp_cmd_output(cmd=downtime_cmd)
        speed_cmd = '{"execute":"migrate-set-parameters","arguments":' \
                    '{"max-bandwidth": %s}}' % speed
        src_remote_qmp.qmp_cmd_output(cmd=speed_cmd)
        paras_chk_cmd = '{"execute":"query-migrate-parameters"}'
        output = src_remote_qmp.qmp_cmd_output(cmd=paras_chk_cmd)
        if re.findall(r'"downtime-limit": %s' % downtime, output) \
                and re.findall(r'"max-bandwidth": %s' % speed, output):
            test.test_print('Change downtime and speed successfully')
        else:
            test.test_error('Failed to change downtime and speed')
        test.sub_step_log('6.2 Check migration status again')
        output = query_migration(remote_qmp=src_remote_qmp,
                                 chk_timeout=chk_time_2)
        if (output == False):
            test.test_error('Migration timeout after change downtime & speed')

    test.main_step_log('7. After migration succeed, '
                       'checking  the status of guest on the dst host')
    test.sub_step_log('7.1 Guest keyboard and mouse work normally.')
    test.sub_step_log('7.2 Reboot guest')
    dst_serial = RemoteSerialMonitor(id, params, dst_host_ip, serial_port)
    cmd = 'dmesg'
    output = dst_serial.serial_cmd_output(cmd=cmd)
    if re.findall(r'Call Trace:', output):
       test.test_error('Guest hit call trace')
    dst_serial.serial_cmd(cmd='reboot')
    dst_guest_ip = dst_serial.serial_login()

    test.sub_step_log('7.3 Ping external host/copy file between guest and host')
    external_host_ip = 'www.redhat.com'
    cmd_ping = 'ping %s -c 10' % external_host_ip
    dst_guest_session = GuestSession(case_id=id, params=params, ip=dst_guest_ip)
    output = dst_guest_session.guest_cmd_output(cmd=cmd_ping)
    if re.findall(r'100% packet loss', output):
        dst_guest_session.test_error('Ping failed')

    test.sub_step_log('7.4 DD a file inside guest')
    cmd_dd = 'dd if=/dev/zero of=file1 bs=100M count=10 oflag=direct'
    output = dst_guest_session.guest_cmd_output(cmd=cmd_dd, timeout=600)
    if not output or re.findall('error', output):
        test.test_error('Failed to dd a file in guest')

    test.sub_step_log('7.5 Shutdown guest successfully')
    output = dst_serial.serial_cmd_output('shutdown -h now')
    if re.findall(r'Call trace', output):
        dst_serial.test_error('Guest hit Call trace during shutdown')

    output = src_remote_qmp.qmp_cmd_output('{"execute":"quit"}', recv_timeout=3)
    if output:
        src_remote_qmp.test_error('Failed to quit qemu on src end')