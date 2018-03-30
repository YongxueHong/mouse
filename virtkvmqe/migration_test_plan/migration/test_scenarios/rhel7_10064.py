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
    serial_port = int(params.get('vm_cmd_base')
                      ['serial'][0].split(',')[0].split(':')[2])
    incoming_port = int(params.get('incoming_port'))

    test = CreateTest(case_id='rhel7_10064', params=params)
    id = test.get_id()
    src_host_session = HostSession(id, params)
    src_qemu_cmd = params.create_qemu_cmd()

    test.main_step_log('1. Start VM in src host')
    src_host_session.boot_guest(cmd=src_qemu_cmd, vm_alias='src')
    src_remote_qmp = RemoteQMPMonitor(id, params, SRC_HOST_IP, qmp_port)

    test.sub_step_log('Connecting to src serial')
    src_serial = RemoteSerialMonitor(id, params, SRC_HOST_IP, serial_port)
    SRC_GUEST_IP = src_serial.serial_login()

    src_guest_session = GuestSession(case_id=id, params=params,
                                     ip=SRC_GUEST_IP)
    test.sub_step_log('Check dmesg info ')
    cmd = 'dmesg'
    output = src_guest_session.guest_cmd_output(cmd)
    if re.findall(r'Call Trace:', output):
        src_guest_session.test_error('Guest hit call trace')

    test.main_step_log('2. Start listening mode in dst host ')
    incoming_val = 'tcp:0:%d' % (incoming_port)
    params.vm_base_cmd_add('incoming', incoming_val)
    dst_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_remote_guest(cmd=dst_qemu_cmd,ip=DST_HOST_IP,
                                       vm_alias='dst')
    dst_remote_qmp = RemoteQMPMonitor(id, params, DST_HOST_IP, qmp_port)

    test.main_step_log('3. Do I/O operations load(iozone) in the guest')
    test.sub_step_log('run iozone -a')
    cmd = 'yum list installed | grep ^gcc.`arch`'
    output = src_guest_session.guest_cmd_output(cmd=cmd)
    if not output:
        output = src_guest_session.guest_cmd_output('yum install -y gcc')
        if not re.findall(r'Complete!', output):
            src_guest_session.test_error('gcc install Error')
    output = src_guest_session.guest_cmd_output('cd /home/iozone3_471/src'
                                                '/current;ls |grep -w iozone')
    if not re.findall(r'No such file or directory', output):
        cmd = 'cd /home;wget http://www.iozone.org/src/current/iozone3_471.tar'
        src_guest_session.guest_cmd_output(cmd=cmd)
        time.sleep(10)
        src_guest_session.guest_cmd_output('cd /home;tar -xvf iozone3_471.tar')
        output = src_guest_session.guest_cmd_output('arch')
        if re.findall(r'ppc64le', output):
            cmd = 'cd /home/iozone3_471/src/current/;make linux-powerpc64'
            src_guest_session.guest_cmd_output(cmd=cmd)
        elif re.findall(r'x86_64', output):
            cmd = 'cd /home/iozone3_471/src/current/;make linux-AMD64 '
            src_guest_session.guest_cmd_output(cmd=cmd)
        else:
            cmd = 'cd /home/iozone3_471/src/current/;make linux-S390X '
            src_guest_session.guest_cmd_output(cmd=cmd)
    cmd = 'cd /home/iozone3_471/src/current/;./iozone -a'
    thread = threading.Thread(target=src_guest_session.guest_cmd_output,
                              args=(cmd,1200,))
    thread.name = 'iozone'
    thread.daemon = True
    thread.start()
    time.sleep(5)
    pid = src_guest_session.guest_cmd_output('pgrep -x iozone')
    if not pid:
        src_guest_session.test_error('iozone excute Error')

    test.main_step_log('4. Stop guest on src guest before migration')
    cmd = '{"execute":"stop"}'
    src_remote_qmp.qmp_cmd_output(cmd)
    while True:
        output = src_remote_qmp.qmp_cmd_output('{"execute":"query-status"}')
        if re.findall(r'"status": "paused"', output):
            break
        time.sleep(5)

    test.main_step_log('5. Start migration from src  to dst host')
    cmd = '{"execute":"migrate", "arguments": {"uri": "tcp:%s:%d"}}' % \
          (DST_HOST_IP, incoming_port)
    src_remote_qmp.qmp_cmd_output(cmd)

    test.sub_step_log('Check the status of migration')
    cmd = '{"execute":"query-migrate"}'
    timeout = 1200
    timeover = time.time() + timeout
    migration_flag = False
    while time.time() < timeover:
        output = src_remote_qmp.qmp_cmd_output(cmd)
        if re.findall(r'"remaining": 0', output):
            migration_flag = True
            break
        if re.findall(r'"status": "failed"', output):
            src_remote_qmp.test_error('migration failed')
    if migration_flag != True:
        src_remote_qmp.test_error('migration timeout')
   
    test.main_step_log('6.After migration finished ,check guests status.')
    cmd = '{"execute":"query-status"}'
    while True:
        output = dst_remote_qmp.qmp_cmd_output(cmd=cmd)
        if re.findall(r'"status": "paused"', output):
           break
        time.sleep(3)
    dst_remote_qmp.qmp_cmd_output('{"execute":"cont"}')
    output=dst_remote_qmp.qmp_cmd_output('{"execute":"query-status"}')
    if not re.findall(r'"status": "running"', output):
        dst_remote_qmp.test.error('migration status Error')

    test.sub_step_log('Connecting to dst serial')
    dst_serial = RemoteSerialMonitor(case_id=id, params=params, ip=DST_HOST_IP,
                                     port=serial_port)
    test.main_step_log('7. Check if guest works well.')
    test.sub_step_log('7.1 Guest mouse and keyboard.')
    test.sub_step_log('7.2Check dmesg info ')
    cmd = 'dmesg'
    output = src_guest_session.guest_cmd_output(cmd)
    if re.findall(r'Call Trace:', output):
        src_guest_session.test_error('Guest hit call trace')
    test.sub_step_log('8. Reboot and then shutdown guest.')
    dst_serial.serial_cmd(cmd='reboot')
    DST_GUEST_IP=dst_serial.serial_login()
    guest_session = GuestSession(case_id=id, params=params, ip=DST_GUEST_IP)
    test.sub_step_log(' Can access guest from external host')
    external_host_ip = DST_HOST_IP
    cmd_ping = 'ping %s -c 10' % external_host_ip
    output = guest_session.guest_cmd_output(cmd=cmd_ping)
    if re.findall(r'100% packet loss', output):
        guest_session.test_error('Ping failed')
    guest_session.guest_cmd_output('dmesg')
    if re.findall(r'Call Trace:', output):
        src_guest_session.test_error('Guest hit call trace')

    test.sub_step_log('quit qemu on src end and shutdown vm on dst end')
    output = src_remote_qmp.qmp_cmd_output('{"execute":"quit"}',
                                           recv_timeout=3)
    if output:
        src_remote_qmp.test_error('Failed to quit qemu on src host')

    output = dst_serial.serial_cmd_output('shutdown -h now')
    if re.findall(r'Call trace', output):
        dst_serial.test_error('Guest hit Call trace during shutdown')



























