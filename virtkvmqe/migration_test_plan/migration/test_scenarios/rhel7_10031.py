import time
from utils_host import HostSession
from utils_guest import GuestSession
from monitor import RemoteSerialMonitor, RemoteQMPMonitor
import re
from vm import CreateTest
import threading


def run_case(params):
    SRC_HOST_IP = params.get('src_host_ip')
    DST_HOST_IP = params.get('dst_host_ip')

    qmp_port = int(params.get('vm_cmd_base')
                   ['qmp'][0].split(',')[0].split(':')[2])
    serail_port = int(params.get('vm_cmd_base')
                      ['serial'][0].split(',')[0].split(':')[2])
    share_images_dir = params.get('share_images_dir')
    incoming_port = params.get('incoming_port')

    test = CreateTest(case_id='rhel7_10031', params=params)
    id = test.get_id()
    src_host_session = HostSession(id, params)

    test.sub_step_log('Create a data disk')

    output = src_host_session.host_cmd_output('qemu-img create '
                                              '-f qcow2 %sdata-disk0.qcow2 10G'
                                              % share_images_dir)
    if re.findall(r'Failed', output):
        src_host_session.test_error('Create image failed!')

    params.vm_base_cmd_add('object', 'iothread,id=iothread0')
    params.vm_base_cmd_add('device',
                           'virtio-scsi-pci,id=virtio_scsi_pci1,bus=pci.0,'
                           'addr=a,iothread=iothread0')
    params.vm_base_cmd_add('drive',
                           'id=drive_data0,if=none,cache=none,format=qcow2,'
                           'snapshot=on,file=%s/data-disk0.qcow2' % share_images_dir)
    params.vm_base_cmd_add('device',
                           'scsi-hd,id=data0,drive=drive_data0,'
                           'bus=virtio_scsi_pci1.0,channel=0,scsi-id=0,lun=0')

    src_qemu_cmd = params.create_qemu_cmd()

    test.main_step_log('1. Boot the guest on source host with data-plane '
                       'and \"werror=stop,rerror=stop\"')

    src_host_session.boot_guest(cmd=src_qemu_cmd, vm_alias='src')

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

    test.main_step_log('2. Boot the guest on destination host '
                       'with \'werror=stop,rerror=stop\'')

    params.vm_base_cmd_add('incoming', 'tcp:0:%s' %incoming_port)
    dst_qemu_cmd = params.create_qemu_cmd()

    src_host_session.boot_remote_guest(ip=DST_HOST_IP,
                                       cmd=dst_qemu_cmd, vm_alias='dst')

    dst_remote_qmp = RemoteQMPMonitor(id, params, DST_HOST_IP, qmp_port)

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

    time.sleep(1)
    src_guest_session.guest_cmd_output('pgrep -x fio')

    test.main_step_log('4. Migrate to the destination')
    cmd = '{"execute":"migrate", "arguments": { "uri": "tcp:%s:%s" }}' \
          % (DST_HOST_IP, incoming_port)
    src_remote_qmp.qmp_cmd_output(cmd)

    test.sub_step_log('Check the status of migration')
    cmd = '{"execute":"query-migrate"}'
    while True:
        output = src_remote_qmp.qmp_cmd_output(cmd)
        if re.findall(r'"remaining": 0', output):
            break
        if re.findall(r'"status": "failed"', output):
            src_remote_qmp.test_error('migration failed')
        time.sleep(5)

    test.sub_step_log('Login dst guest')
    test.sub_step_log('Connecting to dst serial')
    dst_serial = RemoteSerialMonitor(id, params, DST_HOST_IP, serail_port)

    dst_guest_session = GuestSession(case_id=id, params=params,
                                     ip=DST_GUEST_IP)
    dst_guest_session.guest_cmd_output('dmesg')
    if re.findall(r'Call Trace:', output):
        src_guest_session.test_error('Guest hit call trace')

    test.sub_step_log('checking fio process')
    output = dst_guest_session.guest_cmd_output('pgrep -x fio')
    while output :
        output = dst_guest_session.guest_cmd_output('pgrep -x fio')
        time.sleep(3)

    dst_guest_session.guest_cmd_output('dmesg')
    if re.findall(r'Call Trace:', output):
        src_guest_session.test_error('Guest hit call trace')
