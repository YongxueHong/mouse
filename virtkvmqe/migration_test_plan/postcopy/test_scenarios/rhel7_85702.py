from utils_host import HostSession
from utils_guest import GuestSession
from monitor import RemoteSerialMonitor, RemoteQMPMonitor
import re
from vm import CreateTest
import utils_migration

def run_case(params):
    src_host_ip = params.get('src_host_ip')
    dst_host_ip = params.get('dst_host_ip')
    qmp_port = int(params.get('qmp_port'))
    serial_port = int(params.get('serial_port'))
    incoming_port = params.get('incoming_port')
    test = CreateTest(case_id='rhel7_85702', params=params)
    id = test.get_id()
    src_host_session = HostSession(id, params)
    script = 'migration_dirtypage_2.c'

    test.main_step_log('1.Boot a vm in src host with qemu cli:')
    src_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_guest(cmd=src_qemu_cmd, vm_alias='src')
    src_remote_qmp = RemoteQMPMonitor(id, params, src_host_ip, qmp_port)
    src_serial = RemoteSerialMonitor(id, params, src_host_ip, serial_port)
    src_guest_ip = src_serial.serial_login()
    src_guest_session = GuestSession(case_id=id, params=params,
                                     ip=src_guest_ip)

    test.main_step_log('2.Boot a vm in dst host')
    incoming_val = 'tcp:0:%s' % incoming_port
    params.vm_base_cmd_add('incoming', incoming_val)
    dst_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_remote_guest(cmd=dst_qemu_cmd, ip=dst_host_ip,
                                       vm_alias='dst')
    dst_remote_qmp = RemoteQMPMonitor(id, params, dst_host_ip, qmp_port)

    test.main_step_log('3.In the guest, execute the below program '
                       'to generate dirty pages')
    utils_migration.dirty_page_test(host_session=src_host_session,
                                    guest_session=src_guest_session,
                                    guest_ip=src_guest_ip, script=script)

    test.main_step_log('4. Set migration configuration in HMP and do migration')
    test.sub_step_log('set src host xbzrle and postcopy-ram on')
    utils_migration.set_migration_capabilities(remote_qmp=src_remote_qmp,
                                               capabilities='xbzrle',
                                               state='true')
    utils_migration.set_migration_capabilities(remote_qmp=src_remote_qmp,
                                               capabilities='postcopy-ram',
                                               state='true')
    test.sub_step_log('set dst host xbzrle and postcopy-ram on')
    utils_migration.set_migration_capabilities(remote_qmp=dst_remote_qmp,
                                               capabilities='xbzrle',
                                               state='true')
    utils_migration.set_migration_capabilities(remote_qmp=dst_remote_qmp,
                                               capabilities='postcopy-ram',
                                               state='true')
    test.sub_step_log('start to do migration')
    cmd = '{"execute":"migrate", "arguments": { "uri": "tcp:%s:%s" }}' \
          % (dst_host_ip, incoming_port)
    src_remote_qmp.qmp_cmd_output(cmd=cmd)

    test.main_step_log('5. Check migration status, after producing dirty pages'
                       ' switch to post-copy.')
    utils_migration.switch_to_postcopy(remote_qmp=src_remote_qmp)
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

