import time
from monitor import RemoteQMPMonitor
import re

def do_migration(remote_qmp, migrate_port, dst_ip, chk_timeout=1200):
    cmd = '{"execute":"migrate", "arguments": { "uri": "tcp:%s:%s" }}' \
              % (dst_ip, migrate_port)
    remote_qmp.qmp_cmd_output(cmd=cmd)
    remote_qmp.sub_step_log('Check the status of migration')
    return query_migration(remote_qmp=remote_qmp, chk_timeout=chk_timeout)

def query_migration(remote_qmp, interval=5, chk_timeout=1200, recv_timeout=5):
    cmd = '{"execute":"query-migrate"}'
    end_time = time.time() + chk_timeout
    while time.time() < end_time:
        output = remote_qmp.qmp_cmd_output(cmd=cmd, recv_timeout=recv_timeout)
        if re.findall(r'"remaining": 0', output):
            return True
        elif re.findall(r'"status": "failed"', output):
            remote_qmp.test_error('migration failed')
        time.sleep(interval)
    return False

def ping_pong_migration(params, id, src_host_session, src_remote_qmp,
                        dst_remote_qmp, times=10, query_thread=None):
    src_ip = params.get('src_host_ip')
    dst_ip = params.get('dst_host_ip')
    migrate_port = params.get('incoming_port')
    qmp_port = int(params.get('qmp_port'))

    if query_thread:
        if (times % 2) != 0:
            src_host_session.test_error('Please set the value of times to even')

    for i in range(1, times+1):
        if query_thread:
            if (i % 2) != 0:
                src_host_session.sub_step_log('Check the thread: %s '
                                              % query_thread)
                if not src_host_session.host_cmd_output(cmd=query_thread):
                    break
        cmd = '{"execute":"query-status"}'
        src_output = src_remote_qmp.qmp_cmd_output(cmd=cmd,
                                                   echo_cmd=False,
                                                   verbose=False)
        dst_output = dst_remote_qmp.qmp_cmd_output(cmd=cmd,
                                                   echo_cmd=False,
                                                   verbose=False)

        if re.findall(r'"status": "running"', src_output) \
                and re.findall(r'"status": "inmigrate"', dst_output):
            src_host_session.sub_step_log('%d: Do migration from src to dst' % i)
            ret = do_migration(remote_qmp=src_remote_qmp, dst_ip=dst_ip,
                                migrate_port=migrate_port)
            if (ret == True):
                cmd = '{"execute":"query-status"}'
                output = dst_remote_qmp.qmp_cmd_output(cmd=cmd, recv_timeout=5)
                if re.findall(r'"status": "running"', output):
                    src_host_session.test_print('Migration from src to dst succeed')
                else:
                    src_host_session.test_error('Guest is not running on dst side')
            elif (ret == False):
                src_host_session.test_error('Migration from src to dst timeout')

        elif re.findall(r'"status": "running"', dst_output) \
                and re.findall(r'"status": "postmigrate"', src_output):
            src_host_session.sub_step_log('%d: Do migration from dst to src' % i)
            src_remote_qmp.qmp_cmd_output(cmd='{"execute":"quit"}',
                                          echo_cmd=False)

            src_host_session.check_guest_process(src_ip=src_ip)

            src_host_session.sub_step_log('start src with -incoming')
            opt_value = 'tcp:0:%s' % migrate_port
            if not params.get('vm_cmd_base')['incoming']:
                params.vm_base_cmd_add('incoming', opt_value)
            src_qemu_cmd = params.create_qemu_cmd()
            src_host_session.boot_guest(cmd=src_qemu_cmd, vm_alias='src')
            time.sleep(5)
            src_remote_qmp = RemoteQMPMonitor(id, params, src_ip, qmp_port)
            ret = do_migration(remote_qmp=dst_remote_qmp, dst_ip=src_ip,
                                migrate_port=migrate_port)
            if (ret == True):
                cmd = '{"execute":"query-status"}'
                output = src_remote_qmp.qmp_cmd_output(cmd=cmd, recv_timeout=5)
                if re.findall(r'"status": "running"', output):
                    src_host_session.test_print('Migration from dst to src succeed')
                else:
                    src_host_session.test_error('Guest is not running on src side')
            elif (ret == False):
                src_host_session.test_error('Migration from dst to src timeout')

        elif re.findall(r'"status": "running"', src_output) \
                and re.findall(r'"status": "postmigrate"', dst_output):
            src_host_session.sub_step_log('%d: Do migration from src to dst ' % i)
            dst_remote_qmp.qmp_cmd_output(cmd='{"execute":"quit"}',
                                          echo_cmd=False)

            src_host_session.check_guest_process(dst_ip=dst_ip)

            src_host_session.sub_step_log('start dst with -incoming ')
            opt_value = 'tcp:0:%s' % migrate_port
            if not params.get('vm_cmd_base')['incoming']:
                params.vm_base_cmd_add('incoming', opt_value)
            dst_qemu_cmd = params.create_qemu_cmd()
            src_host_session.boot_remote_guest(ip=dst_ip, cmd=dst_qemu_cmd,
                                               vm_alias='dst')
            time.sleep(5)
            dst_remote_qmp = RemoteQMPMonitor(id, params, dst_ip, qmp_port)

            ret = do_migration(remote_qmp=src_remote_qmp, dst_ip=dst_ip,
                                migrate_port=migrate_port)
            if (ret == True):
                cmd = '{"execute":"query-status"}'
                output = dst_remote_qmp.qmp_cmd_output(cmd=cmd, recv_timeout=5)
                if re.findall(r'"status": "running"', output):
                    src_host_session.test_print('Migration from src to dst succeed')
                else:
                    src_host_session.test_error('Guest is not running on dst side')
            elif (ret == False):
                src_host_session.test_error('Migration from src to dst timeout')

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
    ret_done = False
    while time.time() < end_time:
        output = remote_qmp.qmp_cmd_output(cmd=cmd, recv_timeout=qmp_timeout)
        if re.findall(r'"actual": %s' % new_value, output):
            ret_done = True
            break
    if ret_done == False:
        remote_qmp.sub_step_log('Error: The value of balloon is not changed'
                                ' to %s bytes in %s sec'
                                % (new_value, query_timeout))
