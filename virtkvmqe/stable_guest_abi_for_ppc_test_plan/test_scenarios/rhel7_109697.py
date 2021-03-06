from utils_host import HostSession
from utils_guest import GuestSession
from monitor import RemoteSerialMonitor, RemoteQMPMonitor
import time
import re
from vm import CreateTest
import utils_migration
import utils_stable_abi_ppc

def run_case(params):
    src_host_ip = params.get('src_host_ip')
    dst_host_ip = params.get('dst_host_ip')
    qmp_port = int(params.get('qmp_port'))
    serial_port = int(params.get('serial_port'))
    incoming_port = params.get('incoming_port')
    share_images_dir = params.get('share_images_dir')
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

    test = CreateTest(case_id='rhel7_109697', params=params)
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
    utils_stable_abi_ppc.create_iso(host_session=src_host_session,
                                    disk_dir=share_images_dir, iso=iso)

    test.sub_step_log('~~~~3. Configure host hugepage~~~~')
    utils_stable_abi_ppc.configure_host_hugepage(host_session=src_host_session,
                                                 matrix=matrix, dst_ip=dst_host_ip,
                                                 mount_point='/mnt/kvm_hugepage')

    test.sub_step_log('~~~~4. Check matrix~~~~')
    flag = utils_stable_abi_ppc.check_matrix(host_session=src_host_session,
                                             dst_ip=dst_host_ip, matrix=matrix)

    test.main_step_log('1. start guest on Source Host  host must have '
                       'following devices')
    if (flag == 'p9_to_p8'):
        params.vm_base_cmd_update('machine', 'pseries',
                                  'pseries-rhel7.3.0,max-cpu-compat=power8')
    else:
        params.vm_base_cmd_update('machine', 'pseries', 'pseries-rhel7.3.0')
    src_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_guest(cmd=src_qemu_cmd, vm_alias='src')

    test.sub_step_log('1.1 Connecting to src serial')
    src_remote_qmp = RemoteQMPMonitor(id, params, ip=src_host_ip, port=qmp_port)
    src_serial = RemoteSerialMonitor(id, params, ip=src_host_ip, port=serial_port)
    src_guest_ip = src_serial.serial_login()

    test.sub_step_log('2 Start guest on Destination Host  host with same '
                      'qemu cli as step1 but appending')
    if (flag == 'p8_to_p9'):
        params.vm_base_cmd_update('machine', 'pseries-rhel7.3.0',
                                  'pseries-rhel7.3.0,max-cpu-compat=power8')
    elif (flag == 'p9_to_p8'):
        params.vm_base_cmd_update('machine',
                                  'pseries-rhel7.3.0,max-cpu-compat=power8',
                                  'pseries-rhel7.3.0')
    incoming_val = 'tcp:0:%s' % incoming_port
    params.vm_base_cmd_add('incoming', incoming_val)
    params.vm_base_cmd_update('chardev', 'socket,id=serial_id_serial0,host=%s,'
                                         'port=%s,server,nowait' % (src_host_ip,
                                                                    serial_port),
                              'socket,id=serial_id_serial0,host=%s,port=%s,'
                              'server,nowait' % (dst_host_ip, serial_port))
    dst_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_remote_guest(cmd=dst_qemu_cmd, ip=dst_host_ip,
                                       vm_alias='dst')
    dst_remote_qmp = RemoteQMPMonitor(id, params, ip=dst_host_ip, port=qmp_port)

    test.main_step_log('3.In guest, execute the program to generate dirty pages')
    src_guest_session = GuestSession(case_id=id, params=params,
                                     ip=src_guest_ip)
    utils_migration.dirty_page_test(host_session=src_host_session,
                                    guest_session=src_guest_session,
                                    guest_ip=src_guest_ip,
                                    script='migration_dirtypage_2.c')

    test.main_step_log('4.Enable postcopy on both sides and do migration')
    utils_migration.set_migration_capabilities(remote_qmp=src_remote_qmp,
                                               capabilities='postcopy-ram',
                                               state='true')
    utils_migration.set_migration_capabilities(remote_qmp=dst_remote_qmp,
                                               capabilities='postcopy-ram',
                                               state='true')
    cmd = '{"execute":"migrate", "arguments": { "uri": "tcp:%s:%s" }}'\
          % (dst_host_ip, incoming_port)
    src_remote_qmp.qmp_cmd_output(cmd=cmd)

    test.main_step_log('5.check the migration status, after generating dirty '
                       'pages, change to postcopy mode')
    utils_migration.switch_to_postcopy(remote_qmp=src_remote_qmp)
    chk_info = utils_migration.query_migration(remote_qmp=src_remote_qmp)
    if chk_info == False:
        test.test_error('Migration timeout')

    test.main_step_log('6.Check devices function one by one')
    dst_serial = RemoteSerialMonitor(id, params, ip=dst_host_ip, port=serial_port)
    output = dst_serial.serial_cmd_output('dmesg')
    if re.findall(r'Call Trace:', output):
        test.test_error('Guest hit call trace after migration')
    dst_remote_qmp.qmp_cmd_output('{"execute":"system_reset"}')
    dst_guest_ip = dst_serial.serial_login()
    dst_guest_session = GuestSession(case_id=id, params=params,
                                     ip=dst_guest_ip)
    test.sub_step_log('a.Check networking')
    dst_guest_session.guest_ping_test('www.redhat.com', 10)
    test.sub_step_log('b.Check block by the following methods')
    utils_migration.filebench_test(dst_guest_session)
    test.sub_step_log('c.Check VNC console and check keyboard by input keys')
    time.sleep(3)

    test.main_step_log('7.Migrate the guest back to src host and please '
                       'refer to step 4 and step 5')
    src_remote_qmp.qmp_cmd_output('{"execute":"quit"}')
    time.sleep(3)
    src_host_session.check_guest_process(src_ip=src_host_ip)

    if (flag == 'p8_to_p9'):
        params.vm_base_cmd_update('machine',
                                  'pseries-rhel7.3.0,max-cpu-compat=power8',
                                  'pseries-rhel7.3.0')
    elif (flag == 'p9_to_p8'):
        params.vm_base_cmd_update('machine', 'pseries-rhel7.3.0',
                                  'pseries-rhel7.3.0,max-cpu-compat=power8')
    params.vm_base_cmd_update('chardev', 'socket,id=serial_id_serial0,host=%s,'
                                         'port=%s,server,nowait' % (dst_host_ip,
                                                                    serial_port),
                              'socket,id=serial_id_serial0,host=%s,port=%s,'
                              'server,nowait' % (src_host_ip, serial_port))
    src_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_guest(cmd=src_qemu_cmd, vm_alias='src')
    src_remote_qmp = RemoteQMPMonitor(id, params, ip=src_host_ip, port=qmp_port)

    utils_migration.dirty_page_test(host_session=src_host_session,
                                    guest_session=dst_guest_session,
                                    guest_ip=dst_guest_ip,
                                    script='migration_dirtypage_2.c')

    utils_migration.set_migration_capabilities(remote_qmp=dst_remote_qmp,
                                               capabilities='postcopy-ram',
                                               state='true')
    utils_migration.set_migration_capabilities(remote_qmp=src_remote_qmp,
                                               capabilities='postcopy-ram',
                                               state='true')
    cmd = '{"execute":"migrate", "arguments": { "uri": "tcp:%s:%s" }}'\
          % (src_host_ip, incoming_port)
    dst_remote_qmp.qmp_cmd_output(cmd=cmd)
    utils_migration.switch_to_postcopy(remote_qmp=dst_remote_qmp)
    chk_info = utils_migration.query_migration(remote_qmp=dst_remote_qmp)
    if chk_info == False:
        test.test_error('Migration timeout')

    test.main_step_log('8.Repeat step6')
    src_serial = RemoteSerialMonitor(id, params, src_host_ip, serial_port)
    output = src_serial.serial_cmd_output('dmesg')
    if re.findall(r'Call Trace:', output):
        test.test_error('Guest hit call trace after migration')
    src_remote_qmp.qmp_cmd_output('{"execute":"system_reset"}')
    src_guest_ip = src_serial.serial_login()
    src_guest_session = GuestSession(case_id=id, params=params,
                                     ip=src_guest_ip)
    test.sub_step_log('a.Check networking')
    src_guest_session.guest_ping_test('www.redhat.com', 10)
    test.sub_step_log('b.Check block by the following methods')
    utils_migration.filebench_test(src_guest_session)
    test.sub_step_log('c.Check VNC console and check keyboard by input keys')

