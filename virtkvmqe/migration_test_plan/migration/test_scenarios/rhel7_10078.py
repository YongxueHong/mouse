import os, sys
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.extend([BASE_DIR])
import time
from utils_host import HostSession
from utils_guest import GuestSession
from monitor import RemoteSerialMonitor, RemoteQMPMonitor
import re
from vm import CreateTest

def run_case(params):
    SRC_HOST_IP = params.get('src_host_ip')
    DST_HOST_IP = params.get('dst_host_ip')
    qmp_port = int(params.get('vm_cmd_base')['qmp'][0].split(',')[0].split(':')[2])
    serail_port = int(params.get('vm_cmd_base')['serial'][0].split(',')[0].split(':')[2])
    incoming_port = int(params.get('incoming_port'))

    test = CreateTest(case_id='rhel7_10078', params=params)
    id = test.get_id()
    src_host_session = HostSession(id, params)

    test.main_step_log('1. Boot guest on src host with memory balloon device.')
    params.vm_base_cmd_add('device', 'virtio-balloon-pci,id=balloon0,bus=pci.0,addr=0x9')

    src_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_guest(cmd=src_qemu_cmd, vm_alias='src')
    src_remote_qmp = RemoteQMPMonitor(id, params, SRC_HOST_IP, qmp_port)

    test.sub_step_log('1.1 Check guest disk')
    output = src_remote_qmp.qmp_cmd_output('{"execute":"query-block"}', recv_timeout=10)
    if not re.findall(r'drive_image1', output):
        src_remote_qmp.test_error('No found system disk')

    test.sub_step_log('1.2 Connecting to src serial')
    src_serial = RemoteSerialMonitor(id, params, SRC_HOST_IP, serail_port)

    SRC_GUEST_IP = src_serial.serial_login()

    src_guest_session = GuestSession(case_id=id, params=params, ip=SRC_GUEST_IP)
    test.sub_step_log('1.3 Check dmesg info ')
    cmd = 'dmesg'
    output = src_guest_session.guest_cmd_output(cmd)
    if re.findall(r'Call Trace:', output):
        src_guest_session.test_error('Guest hit call trace')

    test.main_step_log('2 Check if memory balloon device works.')
    test.sub_step_log('2.1 Check if balloon device exists')
    output = src_remote_qmp.qmp_cmd_output('{"execute":"query-balloon"}', recv_timeout=10)
    if re.findall(r'No balloon', output):
        src_remote_qmp.test_error('No balloon device has been activated.')

    test.sub_step_log('2.2 Change the value of balloon ~ to 1024MB')
    cmd = '{"execute": "balloon","arguments":{"value":1073741824}}'
    src_remote_qmp.qmp_cmd_output(cmd=cmd, recv_timeout=10)

    test.sub_step_log('Check if the balloon value becomes to 1024MB')
    cmd = '{"execute":"query-balloon"}'
    timeout = 300
    end_time = time.time() + timeout
    flag_done = False
    while time.time() < end_time:
        output = src_remote_qmp.qmp_cmd_output(cmd=cmd, recv_timeout=2)
        if re.findall(r'"actual": 1073741824', output):
            flag_done = True
            break
        time.sleep(3)

    if flag_done == False:
        test.test_error('Error: The value of balloon is failed to  changed to 1024MB in %s sec' % timeout)

    test.main_step_log('3. Hot unplug this memory balloon from guest.')
    cmd = '{"execute":"device_del","arguments":{"id":"balloon0"}}'
    src_remote_qmp.qmp_cmd_output(cmd=cmd, recv_timeout=5)

    test.sub_step_log('Check if the balloon is hot unplug successfully')
    cmd = '{"execute":"query-balloon"}'
    output = src_remote_qmp.qmp_cmd_output(cmd=cmd, recv_timeout=2)
    if re.findall(r'No balloon', output):
        print "Balloon device is hot unplug successfully"

    test.main_step_log('4. Boot guest with \'-incoming\' and without memory balloon device on des host.')
    params.vm_base_cmd_del('device', 'virtio-balloon-pci,id=balloon0,bus=pci.0,addr=0x9')
    incoming_val = 'tcp:0:%d' % incoming_port
    params.vm_base_cmd_add('incoming', incoming_val)

    dst_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_remote_guest(cmd=dst_qemu_cmd, ip=DST_HOST_IP, vm_alias='dst')

    dst_remote_qmp = RemoteQMPMonitor(id, params, DST_HOST_IP, qmp_port)
    output = dst_remote_qmp.qmp_cmd_output('{"execute":"query-balloon"}', recv_timeout=5)
    if re.findall(r'No balloon', output):
        print "Destination guest don't have balloon device"

    test.main_step_log('5. Start live migration, should finish successfully')
    cmd = '{"execute":"migrate", "arguments": {"uri": "tcp:%s:%d"}}' % (DST_HOST_IP, incoming_port)
    src_remote_qmp.qmp_cmd_output(cmd=cmd)

    test.sub_step_log('Check the status of migration')
    cmd = '{"execute":"query-migrate"}'
    while True:
        output = src_remote_qmp.qmp_cmd_output(cmd=cmd)
        if re.findall('"remaining": 0',output):
            break
        time.sleep(2)

    test.main_step_log('6. Check guest on des, guest should work well.')
    dst_serial = RemoteSerialMonitor(id, params, DST_HOST_IP, serail_port)

    test.sub_step_log('Reboot dst guest and get ip of destination guest')
    dst_serial.serial_cmd(cmd='reboot')
    DEST_GUEST_IP = dst_serial.serial_login()
    print 'The ip of destination guest is %s' % DEST_GUEST_IP

    test.main_step_log('7. Hot plug a memory balloon device to destination guest.')
    cmd = '{"execute":"device_add","arguments":{"driver":"virtio-balloon-pci","bus":"pci.0","addr":"0x9","id":"balloon0"}}'
    dst_remote_qmp.qmp_cmd_output(cmd=cmd, recv_timeout=2)
    output = dst_remote_qmp.qmp_cmd_output('{"execute":"query-balloon"}', recv_timeout=3)
    if re.findall(r'No balloon', output):
        dst_remote_qmp.test_error('Failed to hotplug balloon device')

    test.main_step_log('8. Repeat step2')
    cmd = '{"execute": "balloon","arguments":{"value":1073741824}}'
    dst_remote_qmp.qmp_cmd_output(cmd=cmd, recv_timeout=10)

    test.sub_step_log('Check if the balloon value becomes to 1024MB')
    cmd = '{"execute":"query-balloon"}'
    timeout = 300
    end_time = time.time() + timeout
    flag_done = False
    while time.time() < end_time:
        output = dst_remote_qmp.qmp_cmd_output(cmd=cmd, recv_timeout=2)
        if re.findall(r'"actual": 1073741824', output):
            flag_done = True
            break
        time.sleep(2)

    if flag_done == False:
        test.test_error('Error: The value of balloon is failed to  changed to 1024MB in %s sec' % timeout)

    test.main_step_log('9. Quit qemu on src host. Then boot guest with \'-incoming\'on src host, and with memory balloon device')
    src_remote_qmp.qmp_cmd_output('{"execute":"quit"}', recv_timeout=6)
    params.vm_base_cmd_add('device', 'virtio-balloon-pci,id=balloon0,bus=pci.0,addr=0x9')

    src_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_guest(cmd=src_qemu_cmd, vm_alias='src')

    test.main_step_log('10. Start live migration, should finish successfully.')
    cmd = '{"execute":"migrate", "arguments": {"uri": "tcp:%s:%d"}}' % (SRC_HOST_IP, incoming_port)
    dst_remote_qmp.qmp_cmd_output(cmd=cmd)

    test.sub_step_log('Check the status of migration')
    cmd = '{"execute":"query-migrate"}'
    while True:
        output = dst_remote_qmp.qmp_cmd_output(cmd=cmd)
        if re.findall('"remaining": 0',output):
            break
        time.sleep(2)

    test.main_step_log('11&12. Check guest on src, reboot, ping external host,and shutdown.')
    test.sub_step_log('11.1 Reboot src guest')
    src_serial = RemoteSerialMonitor(id, params, SRC_HOST_IP, serail_port)
    src_serial.serial_cmd(cmd='reboot')
    SRC_GUEST_IP = src_serial.serial_login()

    test.sub_step_log('11.2 Ping external host and shutdown guest')
    src_guest_session = GuestSession(case_id=id, params=params, ip=SRC_GUEST_IP)
    external_host_ip = SRC_HOST_IP
    cmd_ping = 'ping %s -c 10' % external_host_ip
    output = src_guest_session.guest_cmd_output(cmd=cmd_ping)
    if re.findall(r'100% packet loss', output):
        src_guest_session.test_error('Ping failed')

