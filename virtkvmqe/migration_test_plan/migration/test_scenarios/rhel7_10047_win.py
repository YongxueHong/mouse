from utils_host import HostSession
from monitor import RemoteQMPMonitor
import re
import time
from vm import CreateTest
from utils_migration import ping_pong_migration

def run_case(params):
    src_host_ip = params.get('src_host_ip')
    dst_host_ip = params.get('dst_host_ip')
    qmp_port = int(params.get('qmp_port'))
    serial_port = int(params.get('serial_port'))
    incoming_port = params.get('incoming_port')
    test = CreateTest(case_id='rhel7_10047_win', params=params)
    id = test.get_id()
    guest_arch = params.get('guest_arch')
    src_host_session = HostSession(id, params)
    mem_size_base = params.get('mem_size')

    test.main_step_log('1. Boot guest with N vcpu and M (GB) memory on the src'
                       ' host. (N=host physical cpu number, '
                       'M=host physical memory number)')
    mem_cmd = 'free -g | grep Mem'
    mem_cmd_remote = "ssh root@%s %s" % (dst_host_ip, mem_cmd)
    if (guest_arch == 'ppc64le'):
        cpu_cmd = "lscpu | sed -n '3p'"
    elif(guest_arch == 'x86_64'):
        # Just a workaround it with cpu_src.strip(':')[-1]
        # and shell command "lscpu | sed -n '4p'"
        # since no any output with
        # host_cmd_output(lscpu | sed -n '4p' | awk '{print $2}').
        cpu_cmd = "lscpu | sed -n '4p'"
    cpu_cmd_remote = "ssh root@%s %s" % (dst_host_ip, cpu_cmd)

    mem_src = src_host_session.host_cmd_output(cmd=mem_cmd)
    mem_dst = src_host_session.host_cmd_output(cmd=mem_cmd_remote)
    cpu_src = src_host_session.host_cmd_output(cmd=cpu_cmd)
    cpu_dst = src_host_session.host_cmd_output(cmd=cpu_cmd_remote)

    cpu_src = cpu_src.split(':')[-1]
    cpu_dst = cpu_dst.split(':')[-1]

    mem_src = int(re.split(' +', mem_src)[3])
    mem_dst = int(re.split(' +', mem_dst)[3])
    cpu_src = int(cpu_src)
    cpu_dst = int(cpu_dst)

    mem_guest = str(min(mem_src, mem_dst))
    cpu_guest = str(min(cpu_src, cpu_dst))

    params.vm_base_cmd_update('m', mem_size_base, '%sG' % mem_guest)
    params.vm_base_cmd_update('smp', '4,maxcpus=4,cores=2,threads=1,sockets=2',
                              cpu_guest)
    src_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_guest(cmd=src_qemu_cmd, vm_alias='src')
    src_remote_qmp = RemoteQMPMonitor(id, params, src_host_ip, qmp_port)

    test.sub_step_log('1.1 Connecting to src serial  --- skip for windows guest')

    test.main_step_log('2. Boot guest with N vcpu and M (GB) memory '
                       'on the dst host')
    incoming_val = 'tcp:0:%s' % incoming_port
    params.vm_base_cmd_add('incoming', incoming_val)
    dst_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_remote_guest(cmd=dst_qemu_cmd,
                                       ip=dst_host_ip, vm_alias='dst')
    dst_remote_qmp = RemoteQMPMonitor(id, params, dst_host_ip, qmp_port)

    test.main_step_log('3. Do ping-pong live migration for 5 times')
    src_remote_qmp, dst_remote_qmp = ping_pong_migration(params, id, src_host_session,
                                                         src_remote_qmp, dst_remote_qmp, times=5)

    test.main_step_log('4. After migration, check if guest works well')
    test.sub_step_log('4.1 Check dst guest status')
    status = dst_remote_qmp.qmp_cmd_output('{"execute":"query-status"}')
    if '\"status\": \"running\"' not in status:
        dst_remote_qmp.test_error('Dst vm is not running')

    test.sub_step_log('4.2 Reboot guest')
    dst_remote_qmp.qmp_cmd_output('{"execute":"system_reset"}')

    output = src_remote_qmp.qmp_cmd_output('{"execute":"quit"}', recv_timeout=3)
    if output:
        src_remote_qmp.test_error('Failed to quit qemu on src end')

    time.sleep(30)
    status = dst_remote_qmp.qmp_cmd_output('{"execute":"query-status"}')
    if '\"status\": \"running\"' not in status:
        dst_remote_qmp.test_error('Dst vm is not running after reboot')

    output = dst_remote_qmp.qmp_cmd_output('{"execute":"quit"}')
    if output:
        dst_remote_qmp.test_error('Failed to quit qemu on dst end')

