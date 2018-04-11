from utils_host import HostSession
from utils_guest import GuestSession
from monitor import RemoteSerialMonitor, RemoteQMPMonitor
from vm import CreateTest
import re
import time
import threading


def run_case(params):
    SRC_HOST_IP = params.get('src_host_ip')
    DST_HOST_IP = params.get('dst_host_ip')
    qmp_port = int(params.get('vm_cmd_base')
                   ['qmp'][0].split(',')[0].split(':')[2])
    serial_port = int(params.get('vm_cmd_base')
                      ['serial'][0].split(',')[0].split(':')[2])
    incoming_port = int(params.get('incoming_port'))

    test = CreateTest(case_id='rhel7_10055', params=params)
    id = test.get_id()
    guest_passwd = params.get('guest_passwd')
    src_host_session = HostSession(id, params)
    src_qemu_cmd = params.create_qemu_cmd()

    test.main_step_log('Scenario 1:src: vhost des'
                       'fileCopy: from src host to guest ')
    test.main_step_log('1. Start VM in src host ')
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
        src_guest_session.test_error('Guest hit call trallce')

    test.main_step_log('2. Start listening mode without vhost in des host ')
    params.vm_base_cmd_del('netdev','tap,id=tap0,vhost=on')
    params.vm_base_cmd_add('netdev','tap,id=tap0')
    incoming_val = 'tcp:0:%d' % (incoming_port)
    params.vm_base_cmd_add('incoming', incoming_val)
    dst_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_remote_guest(cmd=dst_qemu_cmd, ip=DST_HOST_IP,
                                       vm_alias='dst')
    dst_remote_qmp = RemoteQMPMonitor(id, params, DST_HOST_IP, qmp_port)

    test.main_step_log('3.Copy a large file(eg 2G) from host to guest in '
                       'src host, make sure the file keeps transferring '
                       'when migration finish. ')
    src_host_session.host_cmd(cmd='rm -rf /home/file_host')
    cmd = 'dd if=/dev/urandom of=/home/file_host bs=1M count=2000 oflag=direct'
    src_host_session.host_cmd_output(cmd, timeout=600)
    src_guest_session.guest_cmd_output(cmd='rm -rf /home/file_guest')
    thread = threading.Thread(target=src_host_session.host_cmd_scp_put,
                              args=('/home/file_host',
                                    '/home/file_guest',
                                    params.get('guest_passwd'),
                                    SRC_GUEST_IP, 600))
    thread.name = 'scp_thread_put'
    thread.daemon = True
    thread.start()
    time.sleep(10)
    chk_cmd = 'ls /home | grep -w file_guest'
    output = src_guest_session.guest_cmd_output(cmd=chk_cmd)
    if not output:
        test.test_error('Failed to get file')

    test.main_step_log('4. Migrate to the destination')
    cmd = '{"execute":"migrate", "arguments": {"uri": "tcp:%s:%d"}}' % \
          (DST_HOST_IP, incoming_port)
    src_remote_qmp.qmp_cmd_output(cmd)

    test.main_step_log('5.After migration finishes,until transferring finished'
                        'reboot guest,Check file in host and guest.'
                        'value of md5sum is the same.')
    cmd = '{"execute":"query-migrate"}'
    timeout = 2400
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
    test.sub_step_log('check status of transferring the file')
    while True:
        pid = src_host_session.host_cmd_output('pgrep -x scp')
        if not pid:
            break
    output=src_guest_session.guest_cmd_output(cmd='dmesg')
    if re.findall(r'Call Trace:', output) or not output:
        src_guest_session.test_error('Guest hit call trace')

    test.sub_step_log('reboot guest')
    dst_serial = RemoteSerialMonitor(case_id=id, params=params, ip=DST_HOST_IP,
                                     port=serial_port)
    dst_serial.serial_cmd(cmd='reboot')
    DEST_GUEST_IP = dst_serial.serial_login()
    dst_guest_session = GuestSession(case_id=id,params=params,ip=DEST_GUEST_IP)
    cmd = 'dmesg'
    output = dst_guest_session.guest_cmd_output(cmd=cmd)
    if re.findall(r'Call Trace:', output) or not output:
        dst_guest_session.test_error('Guest hit call trace')

    test.sub_step_log('network of guest should be woking')
    external_host_ip = DST_HOST_IP
    cmd_ping = 'ping %s -c 10' % external_host_ip
    output = dst_guest_session.guest_cmd_output(cmd=cmd_ping)
    if re.findall(r'100% packet loss', output):
        dst_guest_session.test_error('Ping failed')

    test.sub_step_log('Check file in host and guest')
    file_src_host_md5 = src_host_session.host_cmd_output(
        cmd='md5sum /home/file_host')
    file_guest_md5 = dst_guest_session.guest_cmd_output(
        cmd='md5sum /home/file_guest')
    if file_src_host_md5.split(' ')[0] != file_guest_md5.split(' ')[0]:
        test.test_error('Value of md5sum error!')

    test.sub_step_log('quit qemu on src end and shutdown vm on dst end')
    output = src_remote_qmp.qmp_cmd_output('{"execute":"quit"}',
                                           recv_timeout=3)
    if output:
        src_remote_qmp.test_error('Failed to quit qemu on src host')

    output = dst_serial.serial_cmd_output('shutdown -h now')
    if re.findall(r'Call trace', output):
        dst_serial.test_error('Guest hit Call trace during shutdown')

    output = dst_remote_qmp.qmp_cmd_output('{"execute":"quit"}',
                                           recv_timeout=3)
    if output:
        dst_remote_qmp.test_error('Failed to quit qemu on dst host')

    time.sleep(20)
    test.main_step_log('Scenario 2.src: des: vhost,'
                       'fileCopy: from src host to guest')
    src_host_session = HostSession(id, params)

    test.main_step_log('1. Start VM in src host ')
    incoming_val = 'tcp:0:%d' % (incoming_port)
    params.vm_base_cmd_del('incoming', incoming_val)
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
        src_guest_session.test_error('Guest hit call trallce')

    test.main_step_log('2. Start listening mode without vhost in des host ')
    params.vm_base_cmd_del('netdev', 'tap,id=tap0')
    params.vm_base_cmd_add('netdev', 'tap,id=tap0,vhost=on')
    incoming_val = 'tcp:0:%d' % (incoming_port)
    params.vm_base_cmd_add('incoming', incoming_val)
    dst_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_remote_guest(cmd=dst_qemu_cmd, ip=DST_HOST_IP,
                                       vm_alias='dst')
    dst_remote_qmp = RemoteQMPMonitor(id, params, DST_HOST_IP, qmp_port)

    test.main_step_log('3.Copy a large file(eg 2G) from host to guest in '
                       'src host, make sure the file keeps transferring '
                       'when migration finish. ')
    src_host_session.host_cmd(cmd='rm -rf /home/file_host')
    cmd = 'dd if=/dev/urandom of=/home/file_host bs=1M count=2000 oflag=direct'
    src_host_session.host_cmd_output(cmd, timeout=600)
    src_guest_session.guest_cmd_output(cmd='rm -rf /home/file_guest')
    thread = threading.Thread(target=src_host_session.host_cmd_scp_put,
                              args=('/home/file_host',
                                    '/home/file_guest',
                                    params.get('guest_passwd'),
                                    SRC_GUEST_IP, 600))
    thread.name = 'scp_thread_put'
    thread.daemon = True
    thread.start()
    time.sleep(3)
    chk_cmd = 'ls /home | grep -w file_guest'
    output = src_guest_session.guest_cmd_output(cmd=chk_cmd)
    if not output:
        test.test_error('Failed to get file')

    test.main_step_log('4. Migrate to the destination')
    cmd = '{"execute":"migrate", "arguments": {"uri": "tcp:%s:%d"}}' % \
          (DST_HOST_IP, incoming_port)
    src_remote_qmp.qmp_cmd_output(cmd)

    test.main_step_log('5.After migration finishes,until transferring finished'
                       'reboot guest,Check file in host and guest.'
                       'value of md5sum is the same.')
    cmd = '{"execute":"query-migrate"}'
    timeout = 2400
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
    test.sub_step_log('check status of transferring the file')
    while True:
        pid = src_host_session.host_cmd_output('pgrep -x scp')
        if not pid:
            break
    output = src_guest_session.guest_cmd_output(cmd='dmesg')
    if re.findall(r'Call Trace:', output) or not output:
        src_guest_session.test_error('Guest hit call trace')

    test.sub_step_log('reboot guest')
    dst_serial = RemoteSerialMonitor(case_id=id, params=params, ip=DST_HOST_IP,
                                     port=serial_port)
    dst_serial.serial_cmd(cmd='reboot')
    DEST_GUEST_IP = dst_serial.serial_login()
    dst_guest_session = GuestSession(case_id=id, params=params,
                                     ip=DEST_GUEST_IP)
    cmd = 'dmesg'
    output = dst_guest_session.guest_cmd_output(cmd=cmd)
    if re.findall(r'Call Trace:', output) or not output:
        dst_guest_session.test_error('Guest hit call trace')

    test.sub_step_log('network of guest should be woking')
    external_host_ip = DST_HOST_IP
    cmd_ping = 'ping %s -c 10' % external_host_ip
    output = dst_guest_session.guest_cmd_output(cmd=cmd_ping)
    if re.findall(r'100% packet loss', output):
        dst_guest_session.test_error('Ping failed')

    test.sub_step_log('Check file in host and guest')
    file_src_host_md5 = src_host_session.host_cmd_output(
        cmd='md5sum /home/file_host')
    file_guest_md5 = dst_guest_session.guest_cmd_output(
        cmd='md5sum /home/file_guest')
    if file_src_host_md5.split(' ')[0] != file_guest_md5.split(' ')[0]:
        test.test_error('Value of md5sum error!')

    test.sub_step_log('6.quit qemu on src end and shutdown vm on dst end')
    output = src_remote_qmp.qmp_cmd_output('{"execute":"quit"}',
                                           recv_timeout=3)
    if output:
        src_remote_qmp.test_error('Failed to quit qemu on src host')

    output = dst_serial.serial_cmd_output('shutdown -h now')
    if re.findall(r'Call trace', output):
        dst_serial.test_error('Guest hit Call trace during shutdown')
    output = dst_remote_qmp.qmp_cmd_output('{"execute":"quit"}',
                                           recv_timeout=3)
    if output:
        dst_remote_qmp.test_error('Failed to quit qemu on dst host')

    time.sleep(20)
    test.main_step_log('Scenario 3.src:vhost des:,'
                       'fileCopy: from src guest to host')
    src_host_session = HostSession(id, params)

    test.main_step_log('1. Start VM in src host ')
    incoming_val = 'tcp:0:%d' % (incoming_port)
    params.vm_base_cmd_del('incoming', incoming_val)
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
        src_guest_session.test_error('Guest hit call trallce')

    test.main_step_log('2. Start listening mode without vhost in des host ')
    params.vm_base_cmd_del('netdev','tap,id=tap0,vhost=on')
    params.vm_base_cmd_add('netdev','tap,id=tap0')
    incoming_val = 'tcp:0:%d' % (incoming_port)
    params.vm_base_cmd_add('incoming', incoming_val)
    dst_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_remote_guest(cmd=dst_qemu_cmd, ip=DST_HOST_IP,
                                       vm_alias='dst')
    dst_remote_qmp = RemoteQMPMonitor(id, params, DST_HOST_IP, qmp_port)

    test.main_step_log('3.Copy a large file(eg 2G) from guest to host in '
                       'src host, make sure the file keeps transferring '
                       'when migration finish. ')
    src_guest_session.guest_cmd_output(cmd='rm -rf /home/file_guest')
    cmd = 'dd if=/dev/urandom of=/home/file_guest ' \
          'bs=1M count=2000 oflag=direct'
    src_guest_session.guest_cmd_output(cmd, timeout=600)
    src_host_session.host_cmd_output(cmd='rm -rf /home/file_host')
    thread = threading.Thread(target=src_host_session.host_cmd_scp_get,
                              args=('/home/file_host',
                                    '/home/file_guest',
                                    params.get('guest_passwd'),
                                    SRC_GUEST_IP, 600))
    thread.name = 'scp_thread_get'
    thread.daemon = True
    thread.start()
    time.sleep(10)
    chk_cmd = 'ls /home | grep -w file_host'
    output = src_host_session.host_cmd_output(cmd=chk_cmd)
    if not output:
        test.test_error('Failed to get file')

    test.main_step_log('4. Migrate to the destination')
    cmd = '{"execute":"migrate", "arguments": {"uri": "tcp:%s:%d"}}' % \
          (DST_HOST_IP, incoming_port)
    src_remote_qmp.qmp_cmd_output(cmd)

    test.main_step_log('5.After migration finishes,until transferring finished'
                        'reboot guest,Check file in host and guest.'
                        'value of md5sum is the same.')
    cmd = '{"execute":"query-migrate"}'
    timeout = 2400
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
    test.sub_step_log('check status of transferring the file')
    while True:
        pid = src_host_session.host_cmd_output('pgrep -x scp')
        if not pid:
            break
    output=src_guest_session.guest_cmd_output(cmd='dmesg')
    if re.findall(r'Call Trace:', output) or not output:
        src_guest_session.test_error('Guest hit call trace')

    test.sub_step_log('reboot guest')
    dst_serial = RemoteSerialMonitor(case_id=id, params=params, ip=DST_HOST_IP,
                                     port=serial_port)
    dst_serial.serial_cmd(cmd='reboot')
    DEST_GUEST_IP = dst_serial.serial_login()
    dst_guest_session = GuestSession(case_id=id,params=params,ip=DEST_GUEST_IP)
    cmd = 'dmesg'
    output = dst_guest_session.guest_cmd_output(cmd=cmd)
    if re.findall(r'Call Trace:', output) or not output:
        dst_guest_session.test_error('Guest hit call trace')

    test.sub_step_log('network of guest should be woking')
    external_host_ip = DST_HOST_IP
    cmd_ping = 'ping %s -c 10' % external_host_ip
    output = dst_guest_session.guest_cmd_output(cmd=cmd_ping)
    if re.findall(r'100% packet loss', output):
        dst_guest_session.test_error('Ping failed')

    test.sub_step_log('Check file in host and guest')
    file_src_host_md5 = src_host_session.host_cmd_output(
        cmd='md5sum /home/file_host')
    file_guest_md5 = dst_guest_session.guest_cmd_output(
        cmd='md5sum /home/file_guest')
    if file_src_host_md5.split(' ')[0] != file_guest_md5.split(' ')[0]:
        test.test_error('Value of md5sum error!')

    test.sub_step_log('quit qemu on src end and shutdown vm on dst end')
    output = src_remote_qmp.qmp_cmd_output('{"execute":"quit"}',
                                           recv_timeout=3)
    if output:
        src_remote_qmp.test_error('Failed to quit qemu on src host')

    output = dst_serial.serial_cmd_output('shutdown -h now')
    if re.findall(r'Call trace', output):
        dst_serial.test_error('Guest hit Call trace during shutdown')
    
    output = dst_remote_qmp.qmp_cmd_output('{"execute":"quit"}',
                                           recv_timeout=3)
    if output:
        dst_remote_qmp.test_error('Failed to quit qemu on dst host')

    test.main_step_log('Scenario 4.src: des:vhost ,'
                       'fileCopy: from src guest to host')
    src_host_session = HostSession(id, params)

    test.main_step_log('1. Start VM in src host ')
    incoming_val = 'tcp:0:%d' % (incoming_port)
    params.vm_base_cmd_del('incoming', incoming_val)
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
        src_guest_session.test_error('Guest hit call trallce')

    test.main_step_log('2. Start listening mode without vhost in des host ')
    params.vm_base_cmd_del('netdev', 'tap,id=tap0')
    params.vm_base_cmd_add('netdev', 'tap,id=tap0,vhost=on')
    incoming_val = 'tcp:0:%d' % (incoming_port)
    params.vm_base_cmd_add('incoming', incoming_val)
    dst_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_remote_guest(cmd=dst_qemu_cmd, ip=DST_HOST_IP,
                                       vm_alias='dst')
    dst_remote_qmp = RemoteQMPMonitor(id, params, DST_HOST_IP, qmp_port)

    test.main_step_log('3.Copy a large file(eg 2G) from guest to host in '
                       'src host, make sure the file keeps transferring '
                       'when migration finish. ')
    src_guest_session.guest_cmd_output(cmd='rm -rf /home/file_guest')
    cmd = 'dd if=/dev/urandom of=/home/file_guest ' \
          'bs=1M count=2000 oflag=direct'
    src_guest_session.guest_cmd_output(cmd, timeout=600)
    src_host_session.host_cmd_output(cmd='rm -rf /home/file_host')
    thread = threading.Thread(target=src_host_session.host_cmd_scp_get,
                              args=('/home/file_host',
                                    '/home/file_guest',
                                    params.get('guest_passwd'),
                                    SRC_GUEST_IP, 600))
    thread.name = 'scp_thread_get'
    thread.daemon = True
    thread.start()
    time.sleep(10)
    chk_cmd = 'ls /home | grep -w file_host'
    output = src_host_session.host_cmd_output(cmd=chk_cmd)
    if not output:
        test.test_error('Failed to get file')

    test.main_step_log('4. Migrate to the destination')
    cmd = '{"execute":"migrate", "arguments": {"uri": "tcp:%s:%d"}}' % \
          (DST_HOST_IP, incoming_port)
    src_remote_qmp.qmp_cmd_output(cmd)

    test.main_step_log('5.After migration finishes,until transferring finished'
                       'reboot guest,Check file in host and guest.'
                       'value of md5sum is the same.')
    cmd = '{"execute":"query-migrate"}'
    timeout = 2400
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
    test.sub_step_log('check status of transferring the file')
    while True:
        pid = src_host_session.host_cmd_output('pgrep -x scp')
        if not pid:
            break
    output = src_guest_session.guest_cmd_output(cmd='dmesg')
    if re.findall(r'Call Trace:', output) or not output:
        src_guest_session.test_error('Guest hit call trace')

    test.sub_step_log('reboot guest')
    dst_serial = RemoteSerialMonitor(case_id=id, params=params, ip=DST_HOST_IP,
                                     port=serial_port)
    dst_serial.serial_cmd(cmd='reboot')
    DEST_GUEST_IP = dst_serial.serial_login()
    dst_guest_session = GuestSession(case_id=id, params=params,
                                     ip=DEST_GUEST_IP)
    cmd = 'dmesg'
    output = dst_guest_session.guest_cmd_output(cmd=cmd)
    if re.findall(r'Call Trace:', output) or not output:
        dst_guest_session.test_error('Guest hit call trace')

    test.sub_step_log('network of guest should be woking')
    external_host_ip = DST_HOST_IP
    cmd_ping = 'ping %s -c 10' % external_host_ip
    output = dst_guest_session.guest_cmd_output(cmd=cmd_ping)
    if re.findall(r'100% packet loss', output):
        dst_guest_session.test_error('Ping failed')

    test.sub_step_log('Check file in host and guest')
    file_src_host_md5 = src_host_session.host_cmd_output(
        cmd='md5sum /home/file_host')
    file_guest_md5 = dst_guest_session.guest_cmd_output(
        cmd='md5sum /home/file_guest')
    if file_src_host_md5.split(' ')[0] != file_guest_md5.split(' ')[0]:
        test.test_error('Value of md5sum error!')

    test.sub_step_log('quit qemu on src end and shutdown vm on dst end')
    output = src_remote_qmp.qmp_cmd_output('{"execute":"quit"}',
                                           recv_timeout=3)
    if output:
        src_remote_qmp.test_error('Failed to quit qemu on src host')

    output = dst_serial.serial_cmd_output('shutdown -h now')
    if re.findall(r'Call trace', output):
        dst_serial.test_error('Guest hit Call trace during shutdown')

