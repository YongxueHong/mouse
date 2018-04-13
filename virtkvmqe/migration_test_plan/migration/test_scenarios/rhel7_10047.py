from utils_host import HostSession
from utils_guest import GuestSession
from monitor import RemoteSerialMonitor, RemoteQMPMonitor
import re
from vm import CreateTest
from utils_migration import ping_pong_migration

def run_case(params):
    src_host_ip = params.get('src_host_ip')
    dst_host_ip = params.get('dst_host_ip')
    qmp_port = int(params.get('qmp_port'))
    serial_port = int(params.get('serial_port'))
    incoming_port = params.get('incoming_port')
    test = CreateTest(case_id='rhel7_10047', params=params)
    id = test.get_id()
    guest_name = test.guest_name
    src_host_session = HostSession(id, params)
    mem_size_base = params.get('mem_size')

    test.main_step_log('1. Boot guest with N vcpu and M (GB) memory on the src'
                       ' host. (N=host physical cpu number, '
                       'M=host physical memory number)')
    mem_cmd = "free -h | grep Mem | awk '{print $2}' |sed 's/G//g'"
    mem_cmd_remote = "ssh root@%s %s" % (dst_host_ip, mem_cmd)
    cpu_cmd = "lscpu | sed -n '3p' | awk '{print $2}'"
    cpu_cmd_remote = "ssh root@%s %s" % (dst_host_ip, cpu_cmd)
    mem_src = int(src_host_session.host_cmd_output(cmd=mem_cmd))
    mem_dst = int(src_host_session.host_cmd_output(cmd=mem_cmd_remote))
    cpu_src = int(src_host_session.host_cmd_output(cmd=cpu_cmd))
    cpu_dst = int(src_host_session.host_cmd_output(cmd=cpu_cmd_remote))
    mem_guest = str(min(mem_src, mem_dst))
    cpu_guest = str(min(cpu_src, cpu_dst))

    params.vm_base_cmd_update('m', mem_size_base, '%sG' % mem_guest)
    params.vm_base_cmd_update('smp', '4,maxcpus=4,cores=2,threads=1,sockets=2',
                              cpu_guest)
    src_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_guest(cmd=src_qemu_cmd, vm_alias='src')
    src_remote_qmp = RemoteQMPMonitor(id, params, src_host_ip, qmp_port)

    test.sub_step_log('1.1 Connecting to src serial')
    src_serial = RemoteSerialMonitor(id, params, src_host_ip, serial_port)
    src_guest_ip = src_serial.serial_login()

    test.main_step_log('2. Boot guest with N vcpu and M (GB) memory '
                       'on the dst host')
    incoming_val = 'tcp:0:%s' % incoming_port
    params.vm_base_cmd_add('incoming', incoming_val)
    dst_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_remote_guest(cmd=dst_qemu_cmd,
                                       ip=dst_host_ip, vm_alias='dst')
    dst_remote_qmp = RemoteQMPMonitor(id, params, dst_host_ip, qmp_port)

    test.main_step_log('3. Do ping-pong live migration for 5 times')
    ping_pong_migration(params, id, src_host_session, src_remote_qmp,
                        dst_remote_qmp, times=5)

    test.main_step_log('4. After migration, check if guest works well')
    test.sub_step_log('4.1 Guest mouse and keyboard')
    test.sub_step_log('4.2 Reboot guest')
    dst_serial = RemoteSerialMonitor(id, params, dst_host_ip, serial_port)
    cmd = 'dmesg'
    output = dst_serial.serial_cmd_output(cmd=cmd)
    if re.findall(r'Call Trace:', output):
        test.test_error('Guest hit call trace')
    dst_serial.serial_cmd(cmd='reboot')
    dst_guest_ip = dst_serial.serial_login()

    test.sub_step_log('4.3 Ping external host/copy file between guest and host')
    dst_guest_session = GuestSession(case_id=id, params=params, ip=dst_guest_ip)
    external_host_ip = 'www.redhat.com'
    cmd_ping = 'ping %s -c 10' % external_host_ip
    output = dst_guest_session.guest_cmd_output(cmd=cmd_ping)
    if re.findall(r'100% packet loss', output):
        dst_serial.test_error('Ping failed')

    test.sub_step_log('4.4 DD a file inside guest')
    cmd_dd = 'dd if=/dev/zero of=file1 bs=100M count=10 oflag=direct'
    output = dst_guest_session.guest_cmd_output(cmd=cmd_dd, timeout=600)
    if not output or re.findall('error', output):
        dst_serial.test_error('Failed to dd a file in guest')

    test.sub_step_log('4.5 Shutdown guest')
    output = dst_serial.serial_cmd_output('shutdown -h now')
    if re.findall(r'Call trace', output):
        dst_serial.test_error('Guest hit Call trace during shutdown')

    src_remote_qmp = RemoteQMPMonitor(id, params, src_host_ip, qmp_port)
    output = src_remote_qmp.qmp_cmd_output('{"execute":"quit"}')
    if output:
        test.test_error('Failed to quit qemu on src end')
