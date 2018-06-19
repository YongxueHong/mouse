import time
from utils_host import HostSession
from monitor import RemoteQMPMonitor
import re
from vm import CreateTest
from utils_migration import do_migration, change_balloon_val

def run_case(params):
    src_host_ip = params.get('src_host_ip')
    dst_host_ip = params.get('dst_host_ip')
    qmp_port = int(params.get('qmp_port'))
    serial_port = int(params.get('serial_port'))
    incoming_port = params.get('incoming_port')
    test = CreateTest(case_id='rhel7_10078_win', params=params)
    id = test.get_id()
    guest_name = test.guest_name
    src_host_session = HostSession(id, params)
    balloon_val = '2147483648'
    chk_timeout = 180

    test.main_step_log('1. Boot guest on src host with memory balloon device.')
    params.vm_base_cmd_add('device',
                           'virtio-balloon-pci,id=balloon0,bus=pci.0,addr=0x9')
    src_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_guest(cmd=src_qemu_cmd, vm_alias='src')

    test.sub_step_log('1.1 Connecting to src serial --- skip for windows guest')

    test.main_step_log('2 Check if memory balloon device works.')
    test.sub_step_log('2.1 Check if balloon device exists')
    src_remote_qmp = RemoteQMPMonitor(id, params, src_host_ip, qmp_port)
    output = src_remote_qmp.qmp_cmd_output('{"execute":"query-balloon"}')
    original_val = eval(output).get('return').get('actual')
    if re.findall(r'No balloon', output):
        src_remote_qmp.test_error('No balloon device has been activated.')

    test.sub_step_log('2.2 Change the value of balloon to %s bytes'
                      % balloon_val)
    change_balloon_val(new_value=balloon_val, remote_qmp=src_remote_qmp)

    test.sub_step_log('2.3 Restore balloon to original value')
    change_balloon_val(new_value=original_val, remote_qmp=src_remote_qmp)

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
                                       ip=dst_host_ip, vm_alias='dst')
    dst_remote_qmp = RemoteQMPMonitor(id, params, dst_host_ip, qmp_port)
    output = dst_remote_qmp.qmp_cmd_output('{"execute":"query-balloon"}',
                                           recv_timeout=5)
    if re.findall(r'No balloon', output):
        test.test_print("Destination guest don't have balloon device")

    test.main_step_log('5. Start live migration, should finish successfully')
    flag = do_migration(remote_qmp=src_remote_qmp,
                        migrate_port=incoming_port, dst_ip=dst_host_ip)
    if (flag == False):
        test.test_error('Migration timeout')

    test.main_step_log('6. Check guest on des, guest should work well.')
    status = dst_remote_qmp.qmp_cmd_output('{"execute":"query-status"}')
    if '\"status\": \"running\"' not in status:
        dst_remote_qmp.test_error('Dst vm is not running')

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
    change_balloon_val(new_value=original_val, remote_qmp=dst_remote_qmp)

    test.main_step_log('9. Quit qemu on src host. Then boot guest with '
                       '\'-incoming\' on src host')
    output = src_remote_qmp.qmp_cmd_output('{"execute":"quit"}')
    if output:
        test.test_error('Failed to quit qemu on src host')
    src_host_session.check_guest_process(src_ip=src_host_ip)
    params.vm_base_cmd_add('device', 'virtio-balloon-pci,id=balloon0,'
                                     'bus=pci.0,addr=0x9')
    src_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_guest(cmd=src_qemu_cmd, vm_alias='src')
    src_remote_qmp = RemoteQMPMonitor(id, params, src_host_ip, qmp_port)
    output = src_remote_qmp.qmp_cmd_output('{"execute":"query-balloon"}')
    if re.findall(r'No balloon', output):
        src_remote_qmp.test_error('src host do not has balloon device')

    test.main_step_log('10. Do migration from dst to src')
    flag = do_migration(remote_qmp=dst_remote_qmp,
                        migrate_port=incoming_port, dst_ip=src_host_ip)
    if (flag == False):
        test.test_error('Migration timeout')

    test.main_step_log('11&12. Check guest on src, reboot, '
                       'and shutdown.')

    test.sub_step_log('11.1 Check src guest status')
    status = src_remote_qmp.qmp_cmd_output('{"execute":"query-status"}')
    if '\"status\": \"running\"' not in status:
        src_remote_qmp.test_error('Src vm is not running')

    test.sub_step_log('11.2 Reboot src guest')
    src_remote_qmp.qmp_cmd_output('{"execute":"system_reset"}')

    test.sub_step_log('11.3 quit qemu on dst end and shutdown vm on src end')
    output = dst_remote_qmp.qmp_cmd_output('{"execute":"quit"}', recv_timeout=3)
    if output:
        dst_remote_qmp.test_error('Failed to quit qemu on dst end')

    time.sleep(30)
    status = src_remote_qmp.qmp_cmd_output('{"execute":"query-status"}')
    if '\"status\": \"running\"' not in status:
        src_remote_qmp.test_error('Src vm is not running after reboot')

    output = src_remote_qmp.qmp_cmd_output('{"execute":"quit"}')
    if output:
        src_remote_qmp.test_error('Failed to quit qemu on src end')


