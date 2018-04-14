import time
from utils_host import HostSession
from utils_guest import GuestSession
from monitor import RemoteSerialMonitor, RemoteQMPMonitor
import re
from vm import CreateTest
import threading
from utils_migration import do_migration

def run_case(params):
    src_host_ip = params.get('src_host_ip')
    dst_host_ip = params.get('dst_host_ip')
    qmp_port = int(params.get('qmp_port'))
    serial_port = int(params.get('serial_port'))
    share_images_dir = params.get('share_images_dir')
    incoming_port = params.get('incoming_port')

    test = CreateTest(case_id='rhel7_10031', params=params)
    id = test.get_id()
    src_host_session = HostSession(id, params)
    test.sub_step_log('Create a data disk')
    output = src_host_session.host_cmd_output('qemu-img create '
                                              '-f qcow2 %s/data-disk0.qcow2 10G'
                                              % share_images_dir)
    if re.findall(r'Failed', output):
        src_host_session.test_error('Create image failed!')
    params.vm_base_cmd_add('object', 'iothread,id=iothread0')
    params.vm_base_cmd_add('device',
                           'virtio-scsi-pci,id=virtio_scsi_pci1,bus=pci.0,'
                           'addr=a,iothread=iothread0')
    params.vm_base_cmd_add('drive',
                           'id=drive_data0,if=none,cache=none,format=qcow2,'
                           'snapshot=on,file=%s/data-disk0.qcow2'
                           % share_images_dir)
    params.vm_base_cmd_add('device',
                           'scsi-hd,id=data0,drive=drive_data0,'
                           'bus=virtio_scsi_pci1.0,channel=0,scsi-id=0,lun=0')
    src_qemu_cmd = params.create_qemu_cmd()

    test.main_step_log('1. Boot the guest on source host with data-plane '
                       'and \"werror=stop,rerror=stop\"')
    src_host_session.boot_guest(cmd=src_qemu_cmd, vm_alias='src')
    src_remote_qmp = RemoteQMPMonitor(id, params, src_host_ip, qmp_port)
    src_serial = RemoteSerialMonitor(id, params, src_host_ip, serial_port)
    src_guest_ip = src_serial.serial_login()
    src_guest_session = GuestSession(case_id=id, params=params, ip=src_guest_ip)
    test.sub_step_log('Check dmesg info ')
    cmd = 'dmesg'
    output = src_guest_session.guest_cmd_output(cmd)
    if re.findall(r'Call Trace:', output):
        src_guest_session.test_error('Guest hit call trace')

    test.main_step_log('2. Boot the guest on destination host '
                       'with \'werror=stop,rerror=stop\'')
    params.vm_base_cmd_add('incoming', 'tcp:0:%s' % incoming_port)
    dst_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_remote_guest(ip=dst_host_ip,
                                       cmd=dst_qemu_cmd, vm_alias='dst')
    dst_remote_qmp = RemoteQMPMonitor(id, params, dst_host_ip, qmp_port)

    test.main_step_log('3. Log in to the guest and launch processe '
                       'that access the disk which is using data-plane')
    sys_dev, output = src_guest_session.guest_system_dev()
    fio_dev = ''
    for dev in re.split("\s+", output):
        if not dev:
            continue
        if not re.findall(sys_dev, dev):
            fio_dev = dev
            break

    test.sub_step_log('run fio with data disk')
    src_guest_session.guest_cmd_output('rm -rf /home/fio')
    src_guest_session.guest_cmd_output('cd /home; '
                                       'git clone git://git.kernel.dk/fio.git')
    src_guest_session.guest_cmd_output('cd /home/fio; '
                                       './configure; make; make install')
    src_guest_session.guest_cmd_output('fio -v')
    cmd = 'fio --filename=%s --direct=1 ' \
          '--rw=randrw --bs=512 --runtime=600 ' \
          '--name=test --iodepth=1 --ioengine=libaio' % fio_dev
    thread = threading.Thread(target=src_guest_session.guest_cmd_output,
                              args=(cmd, 1200,))
    thread.name = 'fio'
    thread.daemon = True
    thread.start()
    time.sleep(10)
    output = src_guest_session.guest_cmd_output('pgrep -x fio')
    if not output:
        test.test_error('fio is not running inside guest')

    test.main_step_log('4. Migrate to the destination')
    check_info = do_migration(src_remote_qmp, incoming_port, dst_host_ip)
    if (check_info == False):
        test.test_error('Migration timeout')

    test.sub_step_log('Login dst guest')
    test.sub_step_log('Connecting to dst serial')
    dst_serial = RemoteSerialMonitor(id, params, dst_host_ip, serial_port)
    test.sub_step_log('check dmesg info')
    cmd = 'dmesg'
    output = dst_serial.serial_cmd_output(cmd=cmd)
    if re.findall(r'Call Trace:', output) or not output:
        test.test_error('Guest hit call trace')

    dst_serial.serial_cmd_output('reboot')
    dst_guest_ip = dst_serial.serial_login()
    dst_guest_session = GuestSession(case_id=id, params=params,
                                     ip=dst_guest_ip)

    test.sub_step_log('checking fio process')
    output = dst_guest_session.guest_cmd_output('pgrep -x fio')
    while output :
        output = dst_guest_session.guest_cmd_output('pgrep -x fio')
        time.sleep(3)

    dst_guest_session.guest_cmd_output('dmesg')
    if re.findall(r'Call Trace:', output):
        dst_guest_session.test_error('Guest hit call trace')

    test.main_step_log('Shut down guest and quit src qemu')
    output = dst_serial.serial_cmd_output('shutdown -h now')
    if re.findall(r'Call trace', output):
        dst_serial.test_error('Guest hit Call trace during shutdown')

    output = src_remote_qmp.qmp_cmd_output('{"execute":"quit"}')
    if output:
        src_remote_qmp.test_error('Failed to quit qemu on src end')