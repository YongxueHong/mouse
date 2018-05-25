from utils_host import HostSession
from utils_guest import GuestSession
from monitor import RemoteSerialMonitor, RemoteQMPMonitor
import re
from vm import CreateTest
import utils_migration
import utils_stable_abi_ppc

def run_case(params):
    src_host_ip = params.get('src_host_ip')
    dst_host_ip = params.get('dst_host_ip')
    qmp_port = int(params.get('qmp_port'))
    serial_port = int(params.get('serial_port'))
    share_images_dir = params.get('share_images_dir')
    sys_image_name = params.get('sys_image_name')
    matrix = params.get('matrix')
    disk1_name = params.get('disk1_name').split('.')[0]
    disk1_format = params.get('disk1_name').split('.')[1]
    disk2_name = params.get('disk2_name').split('.')[0]
    disk2_format = params.get('disk2_name').split('.')[1]
    disk3_name = params.get('disk3_name').split('.')[0]
    disk3_format = params.get('disk3_name').split('.')[1]
    disk4_name = params.get('disk4_name').split('.')[0]
    disk4_format = params.get('disk4_name').split('.')[1]
    disk5_name = params.get('disk5_name').split('.')[0]
    disk5_format = params.get('disk5_name').split('.')[1]
    iso = params.get('cdrom1_name')

    test = CreateTest(case_id='rhel7_110037', params=params)
    id = test.get_id()
    src_host_session = HostSession(id, params)
    test.test_print('=======Create test environment=======')
    test.sub_step_log('~~~~1. Create 5 data disks~~~~')
    utils_migration.create_disk(host_session=src_host_session,
                                disk_dir=share_images_dir, disk_name=disk1_name,
                                disk_format=disk1_format, disk_size=2048)
    utils_migration.create_disk(host_session=src_host_session,
                                disk_dir=share_images_dir,
                                disk_name=disk2_name,
                                disk_format=disk2_format, disk_size=2048)
    utils_migration.create_disk(host_session=src_host_session,
                                disk_dir=share_images_dir,
                                disk_name=disk3_name,
                                disk_format=disk3_format, disk_size=2048)
    utils_migration.create_disk(host_session=src_host_session,
                                disk_dir=share_images_dir,
                                disk_name=disk4_name,
                                disk_format=disk4_format, disk_size=2048)
    utils_migration.create_disk(host_session=src_host_session,
                                disk_dir=share_images_dir,
                                disk_name=disk5_name,
                                disk_format=disk5_format, disk_size=2048)

    test.sub_step_log('~~~~2. Create 1 iso~~~~')
    utils_stable_abi_ppc.create_iso(host_session=src_host_session, disk_dir=share_images_dir, iso=iso)

    test.sub_step_log('~~~~3. Configure host hugepage~~~~')
    utils_stable_abi_ppc.configure_host_hugepage(host_session=src_host_session,
                                                 matrix=matrix, dst_ip=dst_host_ip,
                                                 mount_point='/mnt/kvm_hugepage')

    test.main_step_log('1. Guest must be installed on Source Host  host and '
                       'copy it to Destination Host host. guest must have '
                       'following devices')
    test.main_step_log('2.install guest on Source Host  (old host)')
    test.main_step_log('3.Copy image from Source Host  host to Destination Host  host')
    dst_del_img = 'ssh root@%s rm -rf /tmp/%s' % (dst_host_ip, sys_image_name)
    src_host_session.host_cmd(cmd=dst_del_img)
    cmd = 'scp %s/%s root@%s:/tmp/%s' % (share_images_dir, sys_image_name,
                                         dst_host_ip, sys_image_name)
    src_host_session.host_cmd(cmd=cmd)
    md5_cmd_src = "md5sum %s/%s | awk '{print $1}'" % (share_images_dir, sys_image_name)
    md5_src_images = src_host_session.host_cmd_output(cmd=md5_cmd_src)
    md5_cmd_dst = "ssh root@%s md5sum /tmp/%s | awk '{print $1}'" % (dst_host_ip, sys_image_name)
    md5_dst_images =src_host_session.host_cmd_output(cmd=md5_cmd_dst)

    if not (md5_src_images == md5_dst_images):
        test.test_error('Failed to scp system image to dst host')

    test.main_step_log('4.Boot guest on Destination Host  host and check '
                       'devices function one by one with machine '
                       'type \"-M pseries-rhel7.5.0 \"')
    params.vm_base_cmd_update('chardev', 'socket,id=serial_id_serial0,host=%s,port=%s,server,nowait'
                              % (src_host_ip, serial_port),
                              'socket,id=serial_id_serial0,host=%s,port=%s,server,nowait'
                              % (dst_host_ip, serial_port))
    if (matrix == 'P8_P9'):
        cmd = 'ssh root@%s uname -r' % dst_host_ip
        output = src_host_session.host_cmd_output(cmd=cmd)
        if re.findall(r'el7a', output):
            params.vm_base_cmd_update('machine', 'pseries',
                                  'pseries-rhel7.5.0,max-cpu-compat=power8')
        else:
            params.vm_base_cmd_update('machine', 'pseries', 'pseries-rhel7.5.0')
    else:
        params.vm_base_cmd_update('machine', 'pseries', 'pseries-rhel7.5.0')
    dst_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_remote_guest(cmd=dst_qemu_cmd, ip=dst_host_ip,
                                       vm_alias='dst')
    dst_remote_qmp = RemoteQMPMonitor(id, params, ip=dst_host_ip, port=qmp_port)
    dst_serial = RemoteSerialMonitor(id, params, ip=dst_host_ip,
                                     port=serial_port)
    dst_guest_ip = dst_serial.serial_login()
    dst_guest_session = GuestSession(case_id=id, params=params,
                                     ip=dst_guest_ip)

    test.sub_step_log('a.Check networking')
    dst_guest_session.guest_ping_test('www.redhat.com', 10)
    test.sub_step_log('b.Check block by the following methods')
    utils_migration.filebench_test(dst_guest_session)
    test.sub_step_log('c.Check VNC console and check keyboard by input keys')
    dst_remote_qmp.qmp_cmd_output('{"execute":"system_reset"}')
    dst_serial.serial_login()
