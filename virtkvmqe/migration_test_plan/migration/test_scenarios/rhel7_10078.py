import time
from utils_host import HostSession
from utils_guest import GuestSession
from monitor import RemoteSerialMonitor, RemoteQMPMonitor
import re
from vm import CreateTest
from utils_migration import do_migration, change_balloon_val

def run_case(params):
    SRC_HOST_IP = params.get('src_host_ip')
    DST_HOST_IP = params.get('dst_host_ip')
    qmp_port = int(params.get('qmp_port'))
    serial_port = int(params.get('serial_port'))
    incoming_port = params.get('incoming_port')
    test = CreateTest(case_id='rhel7_10078', params=params)
    id = test.get_id()
    src_host_session = HostSession(id, params)
    balloon_val = '1073741824'

    test.main_step_log('1. Boot guest on src host with memory balloon device.')
    params.vm_base_cmd_add('device',
                           'virtio-balloon-pci,id=balloon0,bus=pci.0,addr=0x9')
    src_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_guest(cmd=src_qemu_cmd, vm_alias='src')
    src_remote_qmp = RemoteQMPMonitor(id, params, SRC_HOST_IP, qmp_port)

    test.sub_step_log('1.1 Connecting to src serial')
    src_serial = RemoteSerialMonitor(id, params, SRC_HOST_IP, serial_port)
    SRC_GUEST_IP = src_serial.serial_login()

    test.main_step_log('2 Check if memory balloon device works.')
    test.sub_step_log('2.1 Check if balloon device exists')
    output = src_remote_qmp.qmp_cmd_output('{"execute":"query-balloon"}',
                                           recv_timeout=5)
    if re.findall(r'No balloon', output):
        src_remote_qmp.test_error('No balloon device has been activated.')

    test.sub_step_log('2.2 Change the value of balloon to %s bytes'
                      % balloon_val)
    change_balloon_val(new_value=balloon_val, remote_qmp=src_remote_qmp)

    test.main_step_log('3. Hot unplug this memory balloon from guest.')
    cmd = '{"execute":"device_del","arguments":{"id":"balloon0"}}'
    src_remote_qmp.qmp_cmd_output(cmd=cmd, recv_timeout=5)

    test.sub_step_log('Check if the balloon is hot unplug successfully')
    cmd = '{"execute":"query-balloon"}'
    output = src_remote_qmp.qmp_cmd_output(cmd=cmd, recv_timeout=5)
    if re.findall(r'No balloon', output):
        test.test_print("Balloon device is hot unplug successfully")

    test.main_step_log('4. Boot guest with \'-incoming\' and '
                       'without memory balloon device on des host.')
    params.vm_base_cmd_del('device', 'virtio-balloon-pci,id=balloon0,'
                                     'bus=pci.0,addr=0x9')
    incoming_val = 'tcp:0:%s' % incoming_port
    params.vm_base_cmd_add('incoming', incoming_val)
    dst_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_remote_guest(cmd=dst_qemu_cmd,
                                       ip=DST_HOST_IP, vm_alias='dst')
    dst_remote_qmp = RemoteQMPMonitor(id, params, DST_HOST_IP, qmp_port)
    output = dst_remote_qmp.qmp_cmd_output('{"execute":"query-balloon"}',
                                           recv_timeout=5)
    if re.findall(r'No balloon', output):
        test.test_print("Destination guest don't have balloon device")

    test.main_step_log('5. Start live migration, should finish successfully')
    flag = do_migration(remote_qmp=src_remote_qmp,
                        migrate_port=incoming_port, dst_ip=DST_HOST_IP)
    if (flag == False):
        test.test_error('Migration timeout')

    test.main_step_log('6. Check guest on des, guest should work well.')
    dst_serial = RemoteSerialMonitor(id, params, DST_HOST_IP, serial_port)
    test.sub_step_log('Reboot dst guest and get ip of destination guest')
    dst_serial.serial_cmd(cmd='reboot')
    DEST_GUEST_IP = dst_serial.serial_login()
    test.test_print('The ip of destination guest is %s' % DEST_GUEST_IP)

    test.main_step_log('7. Hot plug a memory balloon device to '
                       'destination guest.')
    cmd = '{"execute":"device_add","arguments":{"driver":"virtio-balloon-pci",' \
          '"bus":"pci.0","addr":"0x9","id":"balloon0"}}'
    dst_remote_qmp.qmp_cmd_output(cmd=cmd, recv_timeout=5)
    output = dst_remote_qmp.qmp_cmd_output('{"execute":"query-balloon"}',
                                           recv_timeout=5)
    if re.findall(r'No balloon', output):
        dst_remote_qmp.test_error('Failed to hotplug balloon device')

    test.main_step_log('8. Repeat step2')
    change_balloon_val(new_value=balloon_val, remote_qmp=dst_remote_qmp)

    test.main_step_log('9. Quit qemu on src host. Then boot guest with '
                       '\'-incoming\'on src host, and with '
                       'memory balloon device')
    output = src_remote_qmp.qmp_cmd_output('{"execute":"quit"}')
    if output:
        test.test_error('Failed to quit qemu on src host')
    time.sleep(10)
    params.vm_base_cmd_add('device', 'virtio-balloon-pci,id=balloon0,'
                                     'bus=pci.0,addr=0x9')
    src_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_guest(cmd=src_qemu_cmd, vm_alias='src')
    src_remote_qmp = RemoteQMPMonitor(id, params, SRC_HOST_IP, qmp_port)
    output = eval(src_remote_qmp.qmp_cmd_output('{"execute":"query-balloon"}'))
    balloon_val_1 = output.get('return').get('actual')

    test.main_step_log('10. Set the dst balloon value same with src balloon, '
                       'then do migration')
    change_balloon_val(new_value=balloon_val_1, remote_qmp=dst_remote_qmp)
    flag = do_migration(remote_qmp=dst_remote_qmp,
                        migrate_port=incoming_port, dst_ip=SRC_HOST_IP)
    if (flag == False):
        test.test_error('Migration timeout')

    test.main_step_log('11&12. Check guest on src, reboot, '
                       'ping external host,and shutdown.')
    test.sub_step_log('11.1 Reboot src guest')
    src_serial = RemoteSerialMonitor(id, params, SRC_HOST_IP, serial_port)
    src_serial.serial_cmd(cmd='reboot')
    SRC_GUEST_IP = src_serial.serial_login()

    test.sub_step_log('11.2 Ping external host and shutdown guest')
    src_guest_session = GuestSession(case_id=id, params=params,
                                     ip=SRC_GUEST_IP)
    external_host_ip = 'www.redhat.com'
    cmd_ping = 'ping %s -c 10' % external_host_ip
    output = src_guest_session.guest_cmd_output(cmd=cmd_ping)
    if re.findall(r'100% packet loss', output):
        src_guest_session.test_error('Ping failed')

    test.sub_step_log('11.3 quit qemu on dst end and shutdown vm on src end')
    output = src_serial.serial_cmd_output('shutdown -h now')
    if re.findall(r'Call trace', output):
        src_serial.test_error('Guest hit Call trace during shutdown')

    output = dst_remote_qmp.qmp_cmd_output('{"execute":"quit"}',
                                           recv_timeout=3)
    if output:
        dst_remote_qmp.test_error('Failed to quit qemu on dst host')

