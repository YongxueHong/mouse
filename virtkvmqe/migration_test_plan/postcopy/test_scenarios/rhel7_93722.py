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
    incoming_port = params.get('incoming_port')
    test = CreateTest(case_id='rhel7_93722', params=params)
    id = test.get_id()
    src_host_session = HostSession(id, params)
    size = '2147483648'

    test.main_step_log('1.configure hugepage(both src and dst)')
    output = src_host_session.host_cmd_output(cmd='lscpu')
    if re.findall(r'POWER8', output):
        matrix = 'P8_P8'
    elif re.findall(r'POWER9', output):
        matrix = 'P9_P9'
    utils_stable_abi_ppc.configure_host_hugepage(host_session=src_host_session,
                                                 matrix=matrix, dst_ip=dst_host_ip,
                                                 mount_point='/mnt/kvm_hugepage')

    test.main_step_log('2.Boot a guest with hugepage memdev and numa on src host')
    params.vm_base_cmd_add('object', 'memory-backend-file,id=ram-node0,prealloc=yes,'
                                     'mem-path=/dev/hugepages,size=%s' % size)
    params.vm_base_cmd_add('numa', 'node,nodeid=0,cpus=0-1,memdev=ram-node0')
    params.vm_base_cmd_add('object', 'memory-backend-file,id=ram-node1,prealloc=yes,'
                                     'mem-path=/dev/hugepages,size=%s' % size)
    params.vm_base_cmd_add('numa', 'node,nodeid=1,cpus=2-3,memdev=ram-node1')
    src_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_guest(cmd=src_qemu_cmd, vm_alias='src')
    src_remote_qmp = RemoteQMPMonitor(id, params, src_host_ip, qmp_port)
    src_serial = RemoteSerialMonitor(id, params, src_host_ip, serial_port)
    src_serial.serial_login()

    test.main_step_log('3. Boot a guest on dst host')
    incoming_val = 'tcp:0:%s' % incoming_port
    params.vm_base_cmd_add('incoming', incoming_val)
    dst_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_remote_guest(cmd=dst_qemu_cmd, ip=dst_host_ip,
                                       vm_alias='dst')
    dst_remote_qmp = RemoteQMPMonitor(id, params, dst_host_ip, qmp_port)

    test.main_step_log('4.On src host and dst host, '
                       'enable postcopy and do migration')
    test.sub_step_log('set src host postcopy-ram on')
    utils_migration.set_migration_capabilities(remote_qmp=src_remote_qmp,
                                               capabilities='postcopy-ram',
                                               state='true')
    test.sub_step_log('set dst host postcopy-ram on')
    utils_migration.set_migration_capabilities(remote_qmp=dst_remote_qmp,
                                               capabilities='postcopy-ram',
                                               state='true')
    test.sub_step_log('start to do migration')
    cmd = '{"execute":"migrate", "arguments": { "uri": "tcp:%s:%s" }}' \
          % (dst_host_ip, incoming_port)
    src_remote_qmp.qmp_cmd_output(cmd=cmd)
    utils_migration.switch_to_postcopy(remote_qmp=src_remote_qmp,
                                       dirty_count_threshold=0)
    chk_info = utils_migration.query_migration(remote_qmp=src_remote_qmp)
    if chk_info == False:
        test.test_error('Migration timeout')

    test.sub_step_log('Check guest status after migration finished')
    dst_serial = RemoteSerialMonitor(id, params, dst_host_ip, serial_port)
    output = dst_serial.serial_cmd_output('dmesg')
    if re.findall(r'Call Trace:', output):
        test.test_error('Guest hit call trace after migration')
    dst_serial.serial_cmd(cmd='reboot')
    dst_guest_ip = dst_serial.serial_login()
    dst_guest_session = GuestSession(case_id=id, params=params,
                                     ip=dst_guest_ip)
    dst_guest_session.guest_ping_test(dst_ip='www.redhat.com', count=10)

