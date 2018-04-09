from utils_host import HostSession
from utils_guest import GuestSession
from monitor import RemoteSerialMonitor, RemoteQMPMonitor
import re
from vm import CreateTest
from utils_migration import do_migration

def run_case(params):
    src_host_ip = params.get('src_host_ip')
    dst_host_ip = params.get('dst_host_ip')
    qmp_port = int(params.get('qmp_port'))
    serial_port = int(params.get('serial_port'))
    incoming_port = params.get('incoming_port')
    test = CreateTest(case_id='rhel7_10026', params=params)
    id = test.get_id()
    src_host_session = HostSession(id, params)
    downtime = '20000'
    speed = '1073741824'

    test.main_step_log('1. Start vm on src host')
    src_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_guest(cmd=src_qemu_cmd, vm_alias='src')
    src_remote_qmp = RemoteQMPMonitor(id, params, src_host_ip, qmp_port)
    src_serial = RemoteSerialMonitor(id, params, src_host_ip, serial_port)
    src_guest_ip = src_serial.serial_login()

    test.main_step_log('2. Start listening mode on dst host')
    incoming_val = 'tcp:0:%s' % incoming_port
    params.vm_base_cmd_add('incoming', incoming_val)
    dst_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_remote_guest(cmd=dst_qemu_cmd, ip=dst_host_ip,
                                       vm_alias='dst')
    dst_remote_qmp = RemoteQMPMonitor(id, params, dst_host_ip, qmp_port)
    dst_serial = RemoteSerialMonitor(id, params, dst_host_ip, serial_port)

    test.main_step_log('3. keep reboot vm with system_reset, let guest '
                       'in bios stage, before kernel loading')
    test.sub_step_log('3.1 Enlarge the value of downtime and speed to ensure '
                      'to do migration during vm reboot')
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
        test.test_print('Set downtime and speed successfully')
    else:
        test.test_error('Failed to set downtime and speed')

    test.sub_step_log('3.2 system_reset guest')
    src_remote_qmp.qmp_cmd_output('{"execute":"system_reset"}')
    while 1:
        serial_output = src_serial.serial_output()
        test.test_print(serial_output)
        if re.findall(r'SLOF', serial_output):
            test.test_print('Catch keyword')
            break
        if re.findall(r'login', serial_output):
            test.test_error('Failed to catch migration point')

    test.main_step_log('4. implement migrate during vm reboot')
    check_info = do_migration(remote_qmp=src_remote_qmp,
                               migrate_port=incoming_port,
                               dst_ip=dst_host_ip)
    if (check_info == True):
         test.test_print('Migration succeed')
    elif (check_info == False):
         test.test_error('Migration timeout')

    test.main_step_log('5. After migration, check if guest works well')
    output =  dst_serial.serial_output()
    if not output:
        dst_remote_qmp.qmp_cmd_output('{"execute":"system_reset"}')
    dst_guest_ip = dst_serial.serial_login()
    test.sub_step_log('5.1 Guest mouse and keyboard')
    test.sub_step_log('5.2. Ping external host / copy file '
                      'between guest and host')
    external_host_ip = 'www.redhat.com'
    cmd_ping = 'ping %s -c 10' % external_host_ip
    dst_guest_session = GuestSession(case_id=id, params=params, ip=dst_guest_ip)
    output = dst_guest_session.guest_cmd_output(cmd=cmd_ping)
    if re.findall(r'100% packet loss', output):
        dst_guest_session.test_error('Ping failed')

    test.sub_step_log('5.3 dd a file inside guest')
    cmd_dd = 'dd if=/dev/zero of=file1 bs=100M count=10 oflag=direct'
    output = dst_serial.serial_cmd_output(cmd=cmd_dd, timeout=600)
    if not output or re.findall('error', output):
        dst_serial.test_error('Failed to dd a file inside guest')

    test.sub_step_log('5.4. Reboot and then shutdown guest')
    dst_serial.serial_cmd(cmd='reboot')
    dst_serial.serial_login()

    output = dst_serial.serial_cmd_output('shutdown -h now')
    if re.findall(r'Call trace', output):
        dst_serial.test_error('Guest hit Call trace during shutdown')

    output = src_remote_qmp.qmp_cmd_output('{"execute":"quit"}')
    if output:
        src_remote_qmp.test_error('Failed to quit qemu on src end')