import time
from utils_host import HostSession
from monitor import RemoteSerialMonitor
import re
import os
from vm import CreateTest
BASE_FILE = os.path.dirname(os.path.abspath(__file__))


def run_case(params):
    serial_port = int(params.get('vm_cmd_base')
                      ['serial'][0].split(',')[0].split(':')[2])

    test = CreateTest(case_id='unattended_installation', params=params)
    id = test.get_id()

    host_session = HostSession(id, params)

    if params.get('guest_arch') == 'x86_64':
        params.vm_base_cmd_add('machine', 'pc')
    elif params.get('guest_arch') == 'ppc64le':
        params.vm_base_cmd_add('machine', 'pseries')

    image_dir = BASE_FILE + '/images/'
    image_size = params.get('image_size')

    test.main_step_log('1. Create a system image to install os.')
    if params.get('image_format') == 'qcow2':
        image = image_dir + params.get('image_name') + '.qcow2'
        host_session.host_cmd_output('rm -rf %s' % image)
        host_session.host_cmd_output('qemu-img create -f qcow2 %s %s'
                                     % (image, image_size))
        params.vm_base_cmd_add('drive',
                               'id=drive_image1,if=none,snapshot=off,'
                               'aio=threads,cache=none,format=qcow2,'
                               'file=%s' % image)

    elif params.get('image_format') == 'raw':
        image = image_dir + params.get('image_name') + '.raw'
        host_session.host_cmd_output('qemu-img create -f raw %s %s'
                                     % (image, image_size))
        params.vm_base_cmd_add('drive',
                               'id=drive_image1,if=none,snapshot=off,'
                               'aio=threads,cache=none,format=raw,'
                               'file=%s' % image)
    elif params.get('image_format') == 'luks':
        pass

    if params.get('drive_format') == 'virtio_scsi':
        params.vm_base_cmd_add('device',
                               'scsi-hd,id=image1,drive=drive_image1')
    elif params.get('drive_format') == 'virtio_blk':
        params.vm_base_cmd_add('device',
                               'virtio-blk-pci,id=image1,drive=drive_image1')

    isos_dir = BASE_FILE + '/isos/'
    iso = isos_dir + params.get('iso_name')
    params.vm_base_cmd_add('drive',
                           'id=drive_cd1,if=none,snapshot=off,aio=threads,'
                           'cache=none,media=cdrom,file=%s' % iso)
    params.vm_base_cmd_add('device', 'scsi-cd,id=cd1,drive=drive_cd1,bootindex=2')

    ks_dir = BASE_FILE + '/ks/'
    ks = ks_dir + params.get('ks_name')
    ks_iso = BASE_FILE + '/isos/ks.iso'

    test.main_step_log('2. Make a %s form %s.' % (ks_iso, ks))
    host_session.host_cmd_output('mkisofs -o %s %s' % (ks_iso, ks))

    params.vm_base_cmd_add('drive',
                           'id=drive_unattended,if=none,snapshot=off,'
                           'aio=threads,cache=none,media=cdrom,'
                           'file=%s' % ks_iso)

    params.vm_base_cmd_add('device',
                           'scsi-cd,id=unattended,drive=drive_unattended,bootindex=3')

    params.vm_base_cmd_add('m', params.get('mem_size'))
    params.vm_base_cmd_add('smp', '%d,cores=%d,threads=1,sockets=%d'
                           % (int(params.get('vcpu')),
                              int(params.get('vcpu'))/2,
                              int(params.get('vcpu'))/2))

    test.main_step_log('3. cp vmlinuz and initrd.img form %s.' % isos_dir)
    host_session.host_cmd_output('mount %s /mnt/' % iso)
    host_session.host_cmd_output('cp /mnt/images/pxeboot/vmlinuz %s' % isos_dir)
    host_session.host_cmd_output('cp /mnt/images/pxeboot/initrd.img %s' % isos_dir)
    host_session.host_cmd_output('umount /mnt')

    test.main_step_log('4. Check the name of mounted ks.iso.')
    host_session.host_cmd_output('mount %s /mnt/' % ks_iso)
    ks_name = host_session.host_cmd_output('ls /mnt/')
    host_session.host_cmd_output('umount /mnt/')

    params.vm_base_cmd_add('kernel',
                           '"%s/vmlinuz"' % isos_dir)
    console_option = ''
    if params.get('guest_arch') == 'x86_64':
        console_option = 'ttyS0,115200'
    elif params.get('guest_arch') == 'ppc64le':
        console_option = 'hvc0,38400'
    params.vm_base_cmd_add('append',
                           '"ksdevice=link inst.repo=cdrom:/dev/sr0 '
                           'inst.ks=cdrom:/dev/sr1:/%s nicdelay=60 '
                           'biosdevname=0 net.ifnames=0 '
                           'console=tty0 console=%s"' % (ks_name, console_option))
    params.vm_base_cmd_add('initrd',
                           '"%s/initrd.img"' % isos_dir)

    test.main_step_log('5. Boot this guest and start to install os automaticlly.')
    qemu_cmd = params.create_qemu_cmd()
    host_session.boot_guest(cmd=qemu_cmd)
    guest_serial = RemoteSerialMonitor(case_id=id, params=params, ip='0', port=serial_port)

    end_timeout = time.time() + int(params.get('install_timeout'))
    install_done = False
    while time.time() < end_timeout:
        output = guest_serial.serial_output()
        test.test_print(output)
        if re.findall(r'Power down', output):
           install_done = True
           break

    if install_done == False:
        test.test_error('Install failed under %s sec' % params.get('install_timeout'))
    else:
        test.test_print('Install successfully.')
