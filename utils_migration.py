import time
from monitor import RemoteQMPMonitor
import re

def do_migration(remote_qmp, migrate_port, dst_ip, chk_timeout=1200):
    cmd = '{"execute":"migrate", "arguments": { "uri": "tcp:%s:%s" }}' \
              % (dst_ip, migrate_port)
    remote_qmp.qmp_cmd_output(cmd=cmd)
    remote_qmp.sub_step_log('Check the status of migration')
    return query_migration(remote_qmp=remote_qmp, chk_timeout=chk_timeout)

def query_migration(remote_qmp, chk_timeout=1200):
    cmd = '{"execute":"query-migrate"}'
    end_time = time.time() + chk_timeout
    while time.time() < end_time:
        output = remote_qmp.qmp_cmd_output(cmd=cmd)
        if re.findall(r'"remaining": 0', output):
            return True
        elif re.findall(r'"status": "failed"', output):
            remote_qmp.test_error('migration failed')
    return False

def ping_pong_migration(params, test, id, src_host_session, src_remote_qmp,
                        dst_remote_qmp, src_ip, dst_ip, migrate_port,
                        qmp_port, guest_name, even_times=10):
    for i in range(1, even_times+1):
        cmd = '{"execute":"query-status"}'
        src_output = src_remote_qmp.qmp_cmd_output(cmd=cmd)
        dst_output = dst_remote_qmp.qmp_cmd_output(cmd=cmd)

        if re.findall(r'"status": "running"', src_output) \
                and re.findall(r'"status": "inmigrate"', dst_output):
            test.test_print('========>>>>>>>> %d :Do migration from src to dst'
                            ' ========>>>>>>>> \n' % i)
            flag = do_migration(remote_qmp=src_remote_qmp, dst_ip=dst_ip,
                                migrate_port=migrate_port)
            if (flag == True):
                cmd = '{"execute":"query-status"}'
                output = dst_remote_qmp.qmp_cmd_output(cmd=cmd, recv_timeout=5)
                if re.findall(r'"status": "running"', output):
                    test.test_print('Migration from src to dst succeed')
                else:
                    test.test_error('Guest is not running on dst side')
            elif (flag == False):
                test.test_error('Migration from src to dst timeout')

        elif re.findall(r'"status": "running"', dst_output) \
                and re.findall(r'"status": "postmigrate"', src_output):
            test.test_print('========>>>>>>>> %d :Do migration from dst to src'
                            ' ========>>>>>>>> \n' % i)
            src_remote_qmp.qmp_cmd_output(cmd='{"execute":"quit"}')
            src_chk_cmd = "ps -aux | grep %s | grep -vE 'grep|ssh'" \
                          % guest_name
            output = src_host_session.host_cmd_output(cmd=src_chk_cmd)
            if output:
                src_pid = re.split(r"\s+", output)[1]
                src_host_session.host_cmd_output('kill -9 %s' % src_pid)

            test.sub_step_log('start src with -incoming')
            opt_value = 'tcp:0:%s' % migrate_port
            if not params.get('vm_cmd_base')['incoming']:
                params.vm_base_cmd_add('incoming', opt_value)
            src_qemu_cmd = params.create_qemu_cmd()

            src_host_session.boot_guest(cmd=src_qemu_cmd, vm_alias='src')
            src_remote_qmp = RemoteQMPMonitor(id, params, src_ip, qmp_port)
            flag = do_migration(remote_qmp=dst_remote_qmp, dst_ip=src_ip,
                                migrate_port=migrate_port)
            if (flag == True):
                cmd = '{"execute":"query-status"}'
                output = src_remote_qmp.qmp_cmd_output(cmd=cmd, recv_timeout=5)
                if re.findall(r'"status": "running"', output):
                    test.test_print('Migration from dst to src succeed')
                else:
                    test.test_error('Guest is not running on src side')
            elif (flag == False):
                test.test_error('Migration from dst to src timeout')

        elif re.findall(r'"status": "running"', src_output) \
                and re.findall(r'"status": "postmigrate"', dst_output):
            test.test_print('========>>>>>>>> %d :Do migration from src to dst'
                            ' ========>>>>>>>> \n' % i)
            dst_remote_qmp.qmp_cmd_output(cmd='{"execute":"quit"}')
            dst_chk_cmd = 'ssh root@%s ps -aux | grep %s | grep -v grep' \
                          % (dst_ip, guest_name)
            output = src_host_session.host_cmd_output(cmd=dst_chk_cmd)
            if output:
                dst_pid = re.split(r"\s+", output)[1]
                src_host_session.host_cmd_output('ssh root@%s kill -9 %s'
                                                 % (dst_ip, dst_pid))

            test.sub_step_log('start dst with -incoming ')
            opt_value = 'tcp:0:%s' % migrate_port
            if not params.get('vm_cmd_base')['incoming']:
                params.vm_base_cmd_add('incoming', opt_value)
            dst_qemu_cmd = params.create_qemu_cmd()

            src_host_session.boot_remote_guest(ip=dst_ip, cmd=dst_qemu_cmd,
                                               vm_alias='dst')
            dst_remote_qmp = RemoteQMPMonitor(id, params, dst_ip, qmp_port)

            flag = do_migration(remote_qmp=src_remote_qmp, dst_ip=dst_ip,
                                migrate_port=migrate_port)
            if (flag == True):
                cmd = '{"execute":"query-status"}'
                output = dst_remote_qmp.qmp_cmd_output(cmd=cmd, recv_timeout=5)
                if re.findall(r'"status": "running"', output):
                    test.test_print('Migration from src to dst succeed')
                else:
                    test.test_error('Guest is not running on dst side')
            elif (flag == False):
                test.test_error('Migration from src to dst timeout')

    return src_remote_qmp, dst_remote_qmp

def change_balloon_val(new_value, remote_qmp, query_timeout=300,
                       qmp_timeout=5):
    remote_qmp.sub_step_log('Change the value of balloon to %s bytes'
                            % new_value)
    cmd = '{"execute": "balloon","arguments":{"value":%s}}' % new_value
    remote_qmp.qmp_cmd_output(cmd=cmd, recv_timeout=qmp_timeout)

    remote_qmp.sub_step_log('Check if the balloon value becomes to %s bytes'
                      % new_value)
    cmd = '{"execute":"query-balloon"}'
    end_time = time.time() + query_timeout
    flag_done = False
    while time.time() < end_time:
        output = remote_qmp.qmp_cmd_output(cmd=cmd, recv_timeout=qmp_timeout)
        if re.findall(r'"actual": %s' % new_value, output):
            flag_done = True
            break
    if flag_done == False:
        remote_qmp.sub_step_log('Error: The value of balloon is not changed'
                                ' to %s bytes in %s sec'
                                % (new_value, query_timeout))
