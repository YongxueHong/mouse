import time
from utils_host import HostSession
from utils_guest import GuestSession
from monitor import RemoteSerialMonitor, RemoteQMPMonitor
import re
import os
from vm import CreateTest
BASE_FILE = os.path.dirname(os.path.abspath(__file__))
MIGRATION_FILE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def run_case(params):
    serial_port = int(params.get('serial_port'))
    qmp_port = int(params.get('qmp_port'))
    nfs_server_list = params.get('nfs_server')
    src_host_ip = params.get('src_host_ip')
    guest_arch = params.get('guest_arch')
    guest_name = params.get('vm_cmd_base')['name'][0]

    test = CreateTest(case_id='rhel7_10070', params=params)
    id = test.get_id()
    host_session = HostSession(id, params)

    test.main_step_log('1. start VM in src host, install a guest')
    nfs_server_ip_list = []
    for server in nfs_server_list:
        nfs_server_ip_list.append(server.split(':')[0])
    test.test_print('NFS server ip:%s' % nfs_server_ip_list)

    rtt_info = {}
    rtt_val = []
    test.sub_step_log('1.1 Chose a nfs server.')
    for ip in nfs_server_ip_list:
        ping_cmd = 'ping %s -c 5' % ip
        output = host_session.host_cmd_output(ping_cmd)
        rtt_line = output.splitlines()[-1]
        if float(rtt_line.split('/')[-3]) < float(params.get('rtt_tolerance')):
            rtt_info[ip] = rtt_line.split('/')[-3]
            rtt_val.append(float(rtt_line.split('/')[-3]))
    if not rtt_val:
        test.test_error('No available nfs server.')
    test.test_print('rtt info : %s' % rtt_info)
    min_rtt_val = min(rtt_val)
    mount_info = ''
    for ip, rtt in rtt_info.items():
        if float(rtt) == min_rtt_val:
            for nfs_server in nfs_server_list:
                if ip in nfs_server:
                    mount_info = nfs_server

    test.test_print('Mount point info : %s' % mount_info)
    tmp_install_dir = os.path.join(params.get('share_images_dir'), 'install')
    if not os.path.exists(tmp_install_dir):
        os.makedirs(tmp_install_dir)

    image_size = params.get('image_size')
    test.sub_step_log('1.2 Create a system image to install os.')
    params.vm_base_cmd_update('device',
                              'scsi-hd,id=image1,drive=drive_image1,'
                              'bus=virtio_scsi_pci0.0,channel=0,scsi-id=0,'
                              'lun=0,bootindex=0',
                              'scsi-hd,id=image1,drive=drive_image1,'
                              'bus=virtio_scsi_pci0.0,channel=0,'
                              'scsi-id=0,lun=0')
    params.vm_base_cmd_del('drive',
                           'id=drive_image1,if=none,snapshot=off,'
                           'aio=threads,cache=none,format=qcow2,'
                           'file=%s/%s'
                           % (params.get('share_images_dir'),
                              params.get('image1_name')))
    if params.get('image_format') == 'qcow2':
        image = os.path.join(tmp_install_dir,
                             (params.get('image_name') + '.qcow2'))
        host_session.host_cmd_output('rm -rf %s' % image)
        host_session.host_cmd_output('qemu-img create -f qcow2 %s %s'
                                     % (image, image_size))
        params.vm_base_cmd_add('drive',
                               'id=drive_image1,if=none,snapshot=off,'
                               'aio=threads,cache=none,format=qcow2,'
                               'file=%s' % image)

    elif params.get('image_format') == 'raw':
        image = tmp_install_dir + params.get('image_name') + '.raw'
        host_session.host_cmd_output('qemu-img create -f raw %s %s'
                                     % (image, image_size))
        params.vm_base_cmd_add('drive',
                               'id=drive_image1,if=none,snapshot=off,'
                               'aio=threads,cache=none,format=raw,'
                               'file=%s' % image)

    mnt_dir = os.path.join(tmp_install_dir, 'mnt')
    if not os.path.exists(mnt_dir):
        os.makedirs(mnt_dir)
    test.sub_step_log('1.3 Mount iso from nfs server.')
    host_session.host_cmd_output('mount -t nfs %s %s' % (mount_info, mnt_dir))

    test.sub_step_log('1.4 Find the corresponding iso')
    iso_pattern = params.get('iso_name') + '*' + 'Server' + '*' \
               + params.get('guest_arch') + '*' + 'dvd1.iso'
    iso_name = host_session.host_cmd_output('find %s -name %s'
                                            % (mnt_dir, iso_pattern))
    if not iso_name:
        test.test_error('No found the corresponding %s iso.'
                        % params.get('iso_name'))
    test.test_print('Found the corresponding iso: %s' % iso_name)

    isos_dir = os.path.join(tmp_install_dir, 'isos')
    if not os.path.exists(isos_dir):
        os.makedirs(isos_dir)
    test.sub_step_log('1.5 cp the corresponding iso to %s' % isos_dir)
    host_session.host_cmd_output('cp -f %s %s' % (iso_name, isos_dir))

    iso_name = host_session.host_cmd_output('find %s -name %s'
                                            % (isos_dir, iso_pattern))

    host_session.host_cmd_output('umount %s' % mnt_dir)

    params.vm_base_cmd_add('drive',
                           'id=drive_cd1,if=none,snapshot=off,aio=threads,'
                           'cache=none,media=cdrom,file=%s' % iso_name)
    params.vm_base_cmd_add('device',
                           'scsi-cd,id=cd1,drive=drive_cd1,bootindex=2')

    test.sub_step_log('1.6 Find the corresponding ks')
    ks_pattern = params.get('iso_name').split('.')[0] + '*'
    ks = host_session.host_cmd_output('find %s -name %s'
                                      % (MIGRATION_FILE, ks_pattern))

    ks_iso = os.path.join(tmp_install_dir, 'ks.iso')

    test.sub_step_log('1.7 Make a %s form %s.' % (ks_iso, ks))
    host_session.host_cmd_output('mkisofs -o %s %s' % (ks_iso, ks))

    params.vm_base_cmd_add('drive',
                           'id=drive_unattended,if=none,snapshot=off,'
                           'aio=threads,cache=none,media=cdrom,'
                           'file=%s' % ks_iso)

    params.vm_base_cmd_add('device',
                           'scsi-cd,'
                           'id=unattended,drive=drive_unattended,bootindex=3')

    test.sub_step_log('1.8 cp vmlinuz and initrd.img form %s.' % iso_name)
    host_session.host_cmd_output('mount %s %s' % (iso_name, mnt_dir))
    if (guest_arch == 'x86_64'):
        host_session.host_cmd_output('cp -f /%s/images/pxeboot/vmlinuz %s'
                                     % (mnt_dir, isos_dir))
        host_session.host_cmd_output('cp -f /%s/images/pxeboot/initrd.img %s'
                                     % (mnt_dir, isos_dir))
    elif (guest_arch == 'ppc64le'):
        host_session.host_cmd_output('cp -f /%s/ppc/ppc64/vmlinuz %s'
                                     % (mnt_dir, isos_dir))
        host_session.host_cmd_output('cp -f /%s/ppc/ppc64/initrd.img %s'
                                     % (mnt_dir, isos_dir))
    host_session.host_cmd_output('umount %s' % mnt_dir)

    test.sub_step_log('1.9 Check the name of mounted ks.iso.')
    host_session.host_cmd_output('mount %s %s' % (ks_iso, mnt_dir))
    ks_name = host_session.host_cmd_output('ls %s' % mnt_dir)
    host_session.host_cmd_output('umount %s' % mnt_dir)

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
                           'console=tty0 console=%s"'
                           % (ks_name, console_option))
    params.vm_base_cmd_add('initrd',
                           '"%s/initrd.img"' % isos_dir)

    test.sub_step_log('1.10 Boot this guest and start to install os automaticlly.')
    src_qemu_cmd = params.create_qemu_cmd()
    host_session.boot_guest(cmd=src_qemu_cmd, vm_alias='src')
    src_remote_qmp = RemoteQMPMonitor(id, params, src_host_ip, qmp_port)
    src_serial = RemoteSerialMonitor(case_id=id, params=params,
                                           ip=src_host_ip, port=serial_port)

    install_timeout = time.time() + int(params.get('install_timeout'))
    install_done = False
    started_install = False

    while time.time() < install_timeout:
        output = src_serial.serial_output()
        test.test_print(output)
        if re.findall(r'Installing', output):
            started_install = True
            break

    if started_install == False:
        test.test_error('No started to install under %s sec.'
                        % params.get('install_timeout'))

    statefile = '/%s/STATEFILE.gz' % params.get('share_images_dir')
    if started_install == True:
        test.main_step_log('2.do offline migrate during guest installation')
        host_session.host_cmd(cmd=('rm -rf %s' % statefile))
        src_remote_qmp.qmp_cmd_output('{"execute":"migrate",'
                                      '"arguments":{"uri": "exec:gzip -c > %s"}}'
                                      % statefile, recv_timeout=5)
        test.sub_step_log('Check the status of migration')
        cmd = '{"execute":"query-migrate"}'
        migrate_timeout = 1800
        end_timeout = time.time() + migrate_timeout
        flag_done = False
        while time.time() < end_timeout:
            output = src_remote_qmp.qmp_cmd_output(cmd)
            if re.findall(r'"remaining": 0', output):
                flag_done = True
                break
            if re.findall(r'fail', output):
                test.test_error('Migrate failed!')
            time.sleep(2)
        if flag_done == False:
            test.test_error('Failed to migrate under %s sec.' % migrate_timeout)

    test.main_step_log('3. After the guest\'s status changes to paused, '
                       'quit command line and resume it by boot up '
                       'with the same command line'
                       ':-incoming \"exec: gzip -c -d STATEFILE.gz\"')
    chk_timeout = 300
    end_timeout = time.time() + chk_timeout
    flag_timeout = True
    while time.time() < end_timeout:
        cmd = '{ "execute": "query-status" }'
        output = src_remote_qmp.qmp_cmd_output(cmd)
        if re.findall(r'postmigrate', output):
            cmd = '{ "execute": "quit" }'
            guest_chk = "ps -aux | grep %s | grep -vE grep" % guest_name
            output = host_session.host_cmd_output(cmd=guest_chk,
                                                  echo_cmd=False, verbose=False)
            if output:
                guest_pid = re.split(r"\s+", output)[1]
                host_session.host_cmd_output('kill -9 %s' % guest_pid,
                                             echo_cmd=False)
            src_remote_qmp.qmp_cmd_output(cmd)
            flag_timeout = False
            break
        time.sleep(2)

    if flag_timeout == True:
        test.test_error('The guest status is not paused under %s sec.'
                        % chk_timeout)

    params.vm_base_cmd_add('incoming', '"exec: gzip -c -d %s"' % statefile)
    dst_qemu_cmd = params.create_qemu_cmd()
    host_session.boot_guest(cmd=dst_qemu_cmd, vm_alias='dst')
    dst_remote_qmp = RemoteQMPMonitor(id, params, src_host_ip, qmp_port)
    dst_remote_qmp.qmp_cmd_output('{ "execute": "cont" }')
    dst_serial = RemoteSerialMonitor(id, params, src_host_ip, serial_port)

    while time.time() < install_timeout:
        output = dst_serial.serial_output()
        test.test_print(output)
        if re.findall(r'Power down.', output):
           install_done = True
           host_session.host_cmd_output('rm -rf %s/initrd.img' % isos_dir)
           host_session.host_cmd_output('rm -rf %s/vmlinuz' % isos_dir)
           host_session.host_cmd_output('rm -rf %s' % ks_iso)
           break

    if install_done == False:
        host_session.host_cmd_output('rm -rf %s/initrd.img' % isos_dir)
        host_session.host_cmd_output('rm -rf %s/vmlinuz' % isos_dir)
        host_session.host_cmd_output('rm -rf %s' % ks_iso)
        test.test_error('Install failed under %s sec'
                        % params.get('install_timeout'))
    else:
        test.test_print('Install successfully.')

    params.vm_base_cmd_del('drive',
                           'id=drive_cd1,if=none,snapshot=off,aio=threads,'
                           'cache=none,media=cdrom,file=%s' % iso_name)

    params.vm_base_cmd_del('device',
                           'scsi-cd,id=cd1,drive=drive_cd1,bootindex=2')

    params.vm_base_cmd_del('drive',
                           'id=drive_unattended,if=none,snapshot=off,'
                           'aio=threads,cache=none,media=cdrom,'
                           'file=%s' % ks_iso)

    params.vm_base_cmd_del('device',
                           'scsi-cd,'
                           'id=unattended,drive=drive_unattended,bootindex=3')

    params.vm_base_cmd_del('kernel',
                           '"%s/vmlinuz"' % isos_dir)

    params.vm_base_cmd_del('append',
                           '"ksdevice=link inst.repo=cdrom:/dev/sr0 '
                           'inst.ks=cdrom:/dev/sr1:/%s nicdelay=60 '
                           'biosdevname=0 net.ifnames=0 '
                           'console=tty0 console=%s"'
                           % (ks_name, console_option))

    params.vm_base_cmd_del('initrd',
                           '"%s/initrd.img"' % isos_dir)

    params.vm_base_cmd_del('incoming', '"exec: gzip -c -d %s"' % statefile)

    dst_qemu_cmd = params.create_qemu_cmd()
    test.sub_step_log('Boot guest again.')
    host_session.boot_guest(cmd=dst_qemu_cmd, vm_alias='dst')
    dst_serial = RemoteSerialMonitor(id, params, src_host_ip, serial_port)

    dst_guest_ip = dst_serial.serial_login()
    dst_guest_session = GuestSession(case_id=id, params=params,
                                     ip=dst_guest_ip)
    test.sub_step_log('3.1 guest keyboard and mouse work normally.')

    test.sub_step_log('3.2 ping available, copy file succeed, network is fine. ')
    external_host_ip = 'www.redhat.com'
    cmd_ping = 'ping %s -c 10' % external_host_ip
    output = dst_guest_session.guest_cmd_output(cmd=cmd_ping)
    if re.findall(r'100% packet loss', output):
        dst_guest_session.test_error('Ping failed')

    test.sub_step_log('3.3 Guest can reboot and shutdown successfully.')
    dst_serial.serial_cmd(cmd='reboot')
    dst_serial.serial_login()
    output = dst_serial.serial_cmd_output('shutdown -h now')
    if re.findall(r'Call trace', output):
        dst_serial.test_error('Guest hit Call trace during shutdown')
