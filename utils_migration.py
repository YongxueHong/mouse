import time
from monitor import RemoteQMPMonitor
import re

def do_migration(test, src_remote_qmp, dst_remote_qmp, migrate_port, src_ip=None,
                        dst_ip=None):
    if dst_ip:
        cmd = '{"execute":"migrate", "arguments": { "uri": "tcp:%s:%d" }}' \
              % (dst_ip, migrate_port)
        src_remote_qmp.qmp_cmd_output(cmd=cmd)
    else:
        cmd = '{"execute":"migrate", "arguments": { "uri": "tcp:%s:%d" }}' \
              % (src_ip, migrate_port)
        dst_remote_qmp.qmp_cmd_output(cmd=cmd)
    test.sub_step_log('Check the status of migration')
    cmd = '{"execute":"query-migrate"}'
    while 1:
        if dst_ip:
            output = src_remote_qmp.qmp_cmd_output(cmd=cmd)
        else:
            output = dst_remote_qmp.qmp_cmd_output(cmd=cmd)
        if re.findall(r'"remaining": 0', output):
            break
        if re.findall(r'"status": "failed"', output):
            if dst_ip:
                src_remote_qmp.test_error('migration failed')
            else:
                dst_remote_qmp.test_error('migration failed')
        time.sleep(2)

def ping_pong_migration(params, test, cmd, id, src_host_session,
                        src_remote_qmp, dst_remote_qmp, src_ip, src_port,
                        dst_ip, dst_port, migrate_port, even_times=30,
                        query_cmd=None):
    output = ''
    if (even_times % 2) != 0:
        test.test_error('Please set the value of times to even')

    for i in range(1, even_times+1):
        if query_cmd:
            if (even_times % 2) == 0 \
                    and not src_host_session.host_cmd_output(cmd=query_cmd):
                break

        src_output = src_remote_qmp.qmp_cmd_output(cmd='{"execute":"query-status"}')
        dst_output = dst_remote_qmp.qmp_cmd_output(cmd='{"execute":"query-status"}')

        if re.findall(r'"status": "running"', src_output) \
                and re.findall(r'"status": "inmigrate"', dst_output):
            test.test_print('========>>>>>>>> %d : Do migration from src to dst'
                            ' ========>>>>>>>> \n' % i)
            test.sub_step_log('start dst with -incoming ')
            opt_value = 'tcp:0:%d' % migrate_port
            if not params.get('vm_cmd_base')['incoming']:
                params.vm_base_cmd_add('incoming', opt_value)
            dst_qemu_cmd = params.create_qemu_cmd()
            src_host_session.boot_remote_guest(ip=dst_ip, cmd=dst_qemu_cmd, vm_alias='dst')
            dst_remote_qmp = RemoteQMPMonitor(id, params, dst_ip, dst_port)
            do_migration(test, src_remote_qmp, dst_remote_qmp, src_ip=None,
                        dst_ip=dst_ip, migrate_port=migrate_port)

        elif re.findall(r'"status": "running"', dst_output) \
                and re.findall(r'"status": "postmigrate"', src_output):
            test.test_print('========>>>>>>>> %d : Do migration from dst to src'
                            ' ========>>>>>>>> \n' % i)
            src_remote_qmp.qmp_cmd_output(cmd='{"execute":"quit"}')
            test.sub_step_log('start src with -incoming ')
            opt_value = 'tcp:0:%d' % migrate_port
            if not params.get('vm_cmd_base')['incoming']:
                params.vm_base_cmd_add('incoming', opt_value)
            src_qemu_cmd = params.create_qemu_cmd()

            src_host_session.boot_guest(cmd=src_qemu_cmd, vm_alias='src')
            src_remote_qmp = RemoteQMPMonitor(id, params, src_ip, src_port)
            do_migration(test, src_remote_qmp, dst_remote_qmp, src_ip=src_ip,
                        dst_ip=None, migrate_port=migrate_port)

        elif re.findall(r'"status": "running"', src_output) \
                and re.findall(r'"status": "postmigrate"', dst_output):
            test.test_print('========>>>>>>>> %d : Do migration from src to dst'
                            ' ========>>>>>>>> \n' % i)
            dst_remote_qmp.qmp_cmd_output(cmd='{"execute":"quit"}')
            test.sub_step_log('start dst with -incoming ')
            opt_value = 'tcp:0:%d' % migrate_port
            if not params.get('vm_cmd_base')['incoming']:
                params.vm_base_cmd_add('incoming', opt_value)
            dst_qemu_cmd = params.create_qemu_cmd()

            src_host_session.boot_remote_guest(ip=dst_ip, cmd=dst_qemu_cmd, vm_alias='dst')
            dst_remote_qmp = RemoteQMPMonitor(id, params, dst_ip, dst_port)
            do_migration(test, src_remote_qmp, dst_remote_qmp, src_ip=None,
                        dst_ip=dst_ip, migrate_port=migrate_port)

    return src_remote_qmp, dst_remote_qmp

def change_balloon_val(test, new_value, remote_qmp):
    test.test_print('Change the value of balloon to %d bytes' % new_value)
    cmd = '{"execute": "balloon","arguments":{"value":%d}}' % new_value
    remote_qmp.qmp_cmd_output(cmd=cmd, recv_timeout=5)

    test.test_print('Check if the balloon value becomes to %d bytes'
                      % new_value)
    cmd = '{"execute":"query-balloon"}'
    timeout = 300
    end_time = time.time() + timeout
    flag_done = False
    while time.time() < end_time:
        output = remote_qmp.qmp_cmd_output(cmd=cmd, recv_timeout=2)
        if re.findall(r'"actual": %d' % new_value, output):
            flag_done = True
            break
        time.sleep(3)
    if flag_done == False:
        test.test_error('Error: The value of balloon is not changed to %d '
                        'bytes in %s sec' % (new_value, timeout))
