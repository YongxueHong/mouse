import os, sys
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
    #src_qemu_cmd = params.create_qemu_cmd()
    qmp_port = int(params.get('vm_cmd_base')['qmp'][0].split(',')[0].split(':')[2])
    serail_port = int(params.get('vm_cmd_base')['serial'][0].split(',')[0].split(':')[2])

    test = CreateTest(case_id='rhel7_10055', params=params)
    id = test.get_id()
    src_host_session = HostSession(id, params)
    src_qemu_cmd = params.create_qemu_cmd()



    test.main_step_log('1. Boot the guest on source host with ')
    #src_host_session.boot_guest_v2(cmd=cmd_x86_src, vm_alias='src')
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

    test.main_step_log('2. Boot the guest on destination host ')

    params.vm_base_cmd_add('incoming', 'tcp:0:4000')
    dst_qemu_cmd = params.create_qemu_cmd()
    #src_host_session.boot_remote_guest(ip='10.66.10.208', cmd=cmd_x86_dst, vm_alias='dst')
    src_host_session.boot_remote_guest(ip=DST_HOST_IP, cmd=dst_qemu_cmd, vm_alias='dst')

    dst_remote_qmp = RemoteQMPMonitor(id, params, DST_HOST_IP, qmp_port)

    test.main_step_log('3. Log in to the src guest and and  Do I/O operations load(iozone) in the guest')


    test.sub_step_log('run iozone -a')

    output = src_guest_session.guest_cmd_output('gcc -v')
    if re.findall(r'command not found', output):
        src_guest_session.guest_cmd_output('yum install -y gcc')

    output = src_guest_session.guest_cmd_output('cd /home/iozone_471;cd src; cd current;./iozone -a')
    if re.findall(r'No such file or directory', output):
        src_guest_session.guest_cmd_output('cd /home; wget http://www.iozone.org/src/current/iozone3_471.tar')
        time.sleep(10)
        src_guest_session.guest_cmd_output('cd /home;tar -xvf iozone3_471.tar')
        src_guest_session.guest_cmd_output('cd /home/iozone3_471/src/current/;make linux-powerpc64')
        output = src_guest_session.guest_cmd_output('cd /home/iozone3_471/src/current/;./iozone -a')
        if re.findall(r'command not found', output) or not output:
            src_guest_session.test_error('Install fio failed')

    cmd = 'cd /home/iozone3_471/src/current/;./iozone -a'
    thread = threading.Thread(target=src_guest_session.guest_cmd_output, args=(cmd, 1200,))
    thread.name = 'fio'
    thread.daemon = True
    thread.start()

    time.sleep(1)
    src_guest_session.guest_cmd_output('pgrep -x iozone')

    test.main_step_log('4. Migrate to the destination')
    cmd = '{"execute":"migrate", "arguments": { "uri": "tcp:%s:4000" }}' %(DST_HOST_IP)
    src_remote_qmp.qmp_cmd_output(cmd)

    test.main_step_log('5.Stop guest during migration')
    cmd = '{"execute":"stop"}'
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
    cmd = '{"execute":"query-status"}'
    while True:
        output = dst_remote_qmp.qmp_cmd_output(cmd=cmd)
        if re.findall(r'"status": "paused"', output):
            break
        time.sleep(5)

    test.sub_step_log('Login dst guest')
    test.sub_step_log('Connecting to dst serial')
    test.sub_step_log('check dmesg info')
    dst_remote_qmp.qmp_cmd_output('{"execute":"cont"}')
    dst_remote_qmp.qmp_cmd_output('{"execute":"query-status"}')

    dst_serial = RemoteSerialMonitor(case_id=id, params=params, ip=SRC_HOST_IP, port=serail_port)

    guest_session = GuestSession(case_id=id, params=params, ip=SRC_GUEST_IP)

    cmd = 'dmesg'
    output = guest_session.guest_cmd_output(cmd=cmd)
    if re.findall(r'Call Trace:', output) or not output:
        guest_session.test_error('Guest hit call trace')
    
    


