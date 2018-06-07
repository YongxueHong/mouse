import os
import time
from monitor import RemoteQMPMonitor
import re
import threading
import json
import utils_misc

def do_migration(remote_qmp, migrate_port, dst_ip, chk_timeout_1=180,
                 chk_timeout_2=1200, downtime_val='20000',
                 speed_val='1073741824'):
    cmd = '{"execute":"migrate", "arguments": { "uri": "tcp:%s:%s" }}' \
              % (dst_ip, migrate_port)
    remote_qmp.qmp_cmd_output(cmd=cmd)
    remote_qmp.sub_step_log('Check the status of migration')
    ret = query_migration(remote_qmp=remote_qmp, chk_timeout=chk_timeout_1)
    if (ret == False):
        change_downtime(remote_qmp=remote_qmp, downtime_val=downtime_val)
        change_speed(remote_qmp=remote_qmp, speed_val=speed_val)
        ret = query_migration(remote_qmp=remote_qmp, chk_timeout=chk_timeout_2)
    return ret

def query_migration(remote_qmp, interval=5, chk_timeout=1200):
    cmd = '{"execute":"query-migrate"}'
    end_time = time.time() + chk_timeout
    while time.time() < end_time:
        output = remote_qmp.qmp_cmd_output(cmd=cmd)
        if re.findall(r'"status": "completed"', output):
            return True
        elif re.findall(r'"status": "failed"', output):
            remote_qmp.test_error('migration failed')
        time.sleep(interval)
    return False

def query_status(remote_qmp, status, interval=1, chk_timeout=300):
    cmd = '{"execute":"query-migrate"}'
    end_time = time.time() + chk_timeout
    while time.time() < end_time:
        output = remote_qmp.qmp_cmd_output(cmd=cmd)
        if re.findall(r'"status": "%s"' % status, output):
            return True
        elif re.findall(r'"status": "failed"', output):
            remote_qmp.test_error('migration failed')
        time.sleep(interval)
    return False

def change_downtime(remote_qmp, downtime_val):
    downtime_cmd = '{"execute":"migrate-set-parameters","arguments":' \
                   '{"downtime-limit": %s}}' % downtime_val
    remote_qmp.qmp_cmd_output(cmd=downtime_cmd)
    paras_chk_cmd = '{"execute":"query-migrate-parameters"}'
    output = remote_qmp.qmp_cmd_output(cmd=paras_chk_cmd,
                                           recv_timeout=2)
    if re.findall(r'"downtime-limit": %s' % downtime_val, output):
        remote_qmp.test_print('Change migration downtime successfully')
    else:
        remote_qmp.test_error('Failed to change migration downtime')

def change_speed(remote_qmp, speed_val):
    speed_cmd = '{"execute":"migrate-set-parameters","arguments":' \
                '{"max-bandwidth": %s}}' % speed_val
    remote_qmp.qmp_cmd_output(cmd=speed_cmd)
    paras_chk_cmd = '{"execute":"query-migrate-parameters"}'
    output = remote_qmp.qmp_cmd_output(cmd=paras_chk_cmd,
                                           recv_timeout=2)
    if re.findall(r'"max-bandwidth": %s' % speed_val, output):
        remote_qmp.test_print('Change migration speed successfully')
    else:
        remote_qmp.test_error('Failed to change migration speed')

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
                output = dst_remote_qmp.qmp_cmd_output(cmd=cmd)
                if re.findall(r'"status": "running"', output):
                    src_host_session.test_print('Migration from src to dst succeed')
                else:
                    src_host_session.test_error('Guest is not running on dst side')
            elif (ret == False):
                src_host_session.test_error('Migration from src to dst timeout')
            time.sleep(3)

        elif re.findall(r'"status": "running"', dst_output) \
                and re.findall(r'"status": "postmigrate"', src_output):
            src_host_session.sub_step_log('%d: Do migration from dst to src' % i)
            src_remote_qmp.qmp_cmd_output(cmd='{"execute":"quit"}',
                                          echo_cmd=False)

            src_host_session.check_guest_process(src_ip=src_ip)
            time.sleep(3)

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
                output = src_remote_qmp.qmp_cmd_output(cmd=cmd)
                if re.findall(r'"status": "running"', output):
                    src_host_session.test_print('Migration from dst to src succeed')
                else:
                    src_host_session.test_error('Guest is not running on src side')
            elif (ret == False):
                src_host_session.test_error('Migration from dst to src timeout')
            time.sleep(3)

        elif re.findall(r'"status": "running"', src_output) \
                and re.findall(r'"status": "postmigrate"', dst_output):
            src_host_session.sub_step_log('%d: Do migration from src to dst ' % i)
            dst_remote_qmp.qmp_cmd_output(cmd='{"execute":"quit"}',
                                          echo_cmd=False)

            src_host_session.check_guest_process(dst_ip=dst_ip)
            time.sleep(3)

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
                output = dst_remote_qmp.qmp_cmd_output(cmd=cmd)
                if re.findall(r'"status": "running"', output):
                    src_host_session.test_print('Migration from src to dst succeed')
                else:
                    src_host_session.test_error('Guest is not running on dst side')
            elif (ret == False):
                src_host_session.test_error('Migration from src to dst timeout')
            time.sleep(3)

    return src_remote_qmp, dst_remote_qmp

def set_migration_capabilities(remote_qmp, capabilities, state):
    set_capabilities = '{"execute":"migrate-set-capabilities","arguments":' \
                       '{"capabilities":[{"capability":"%s","state":%s}]}}' \
                       % (capabilities, state)
    check_capabilities = '{"execute":"query-migrate-capabilities"}'
    remote_qmp.qmp_cmd_output(cmd=set_capabilities)
    output = remote_qmp.qmp_cmd_output(cmd=check_capabilities)
    if re.findall(r'"state": %s, "capability": "%s"' % (state, capabilities), output):
        remote_qmp.test_print('Succeed to set migration capabilities: %s'
                              % capabilities)
    else:
        remote_qmp.test_error('Failed to set migration capabilities: %s'
                              % capabilities)

def switch_to_postcopy(remote_qmp, query_dirty_timeout=600, interval=5,
                       dirty_count_threshold=1):
    cmd = '{"execute":"query-migrate"}'
    end_time = time.time() + query_dirty_timeout
    flag = False
    while time.time() < end_time:
        output = remote_qmp.qmp_cmd_output(cmd=cmd)
        if re.findall(r'"status": "active"',output):
            output = json.loads(output)
            dirty_sync_count = int(output.get('return').get('ram')
                                   .get('dirty-sync-count'))
            json.dumps(output)
            if (dirty_sync_count > dirty_count_threshold):
                flag = True
                break
        elif re.findall(r'"status": "failed"', output):
            remote_qmp.test_error('migration failed')
        elif re.findall(r'"status": "completed"', output):
            remote_qmp.test_error('Migration is already completed')
        else:
            remote_qmp.test_error('Migration status is not active, failed or completed')
        time.sleep(interval)
    if flag == False:
        remote_qmp.test_error('dirty-sync-count is not lager than %d within %d'
                              % (dirty_count_threshold, query_dirty_timeout))
    cmd = '{"execute":"migrate-start-postcopy"}'
    remote_qmp.qmp_cmd_output(cmd=cmd)

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

def filebench_test(guest_session, run_time=60, recv_timeout=600):
    arch = guest_session.guest_cmd_output('arch')
    filebench_cmd = 'yum list installed | grep -w "filebench.%s"' % arch
    output = guest_session.guest_cmd_output(cmd=filebench_cmd)
    if not re.findall(r'filebench.%s' % arch, output):
        install_cmd = 'yum install -y filebench.`arch`'
        install_info = guest_session.guest_cmd_output(install_cmd)
        if re.findall('Complete', install_info):
            guest_session.test_print('Guest install filebench pkg successfully')
        else:
            guest_session.test_error('Guest failed to install filebench pkg')

    cmd = 'echo 0 > /proc/sys/kernel/randomize_va_space'
    guest_session.guest_cmd_output(cmd=cmd)
    cmd_filebench = "echo -e 'load varmail\nset $iosize=512\nrun %s' | filebench" % run_time
    output = guest_session.guest_cmd_output(cmd=cmd_filebench, timeout=recv_timeout)
    if re.findall(r'Running', output):
        guest_session.test_print('Succeed to execute filebench')
    elif not output or re.findall(r'Failed', output):
        guest_session.test_error('Failed to execute filebench')

def stress_test(guest_session, run_time=120):
    chk_cmd = 'yum list installed | grep stress.`arch`'
    output = guest_session.guest_cmd_output(cmd=chk_cmd)
    if not output:
        install_cmd = 'yum install -y stress.`arch`'
        install_info = guest_session.guest_cmd_output(cmd=install_cmd)
        if re.findall('Complete', install_info):
            guest_session.test_print('Guest install stress pkg successfully')
        else:
            guest_session.test_error('Guest failed to install stress pkg')
    stress_cmd = 'stress --cpu 4 --vm 4 --vm-bytes 256M --timeout %d > ' \
                 '/dev/null &' % run_time
    guest_session.guest_cmd_output(stress_cmd)
    if not utils_misc.wait_for_output(lambda: guest_session.
            guest_cmd_output('pgrep -x stress'), 30):
        guest_session.test_error('Stress is not running in guest')

def dirty_page_test(host_session, guest_session, guest_ip, script):
    BASE_DIR = os.path.dirname((os.path.abspath(__file__)))
    guest_passwd = guest_session._passwd
    host_session.test_print('scp %s to guest' % script)
    guest_session.guest_cmd_output('cd /home;rm -f %s' % script)
    host_session.host_cmd_scp_put(local_path='%s/c_scripts/%s' % (BASE_DIR, script),
                                  remote_path='/home/%s' % script, passwd=guest_passwd,
                                  remote_ip=guest_ip, timeout=300)
    chk_cmd = 'ls /home | grep -w "%s"' % script
    output = guest_session.guest_cmd_output(cmd=chk_cmd)
    if not output:
        guest_session.test_error('Failed to get %s' % script)
    arch = guest_session.guest_cmd_output('arch')
    gcc_cmd = 'yum list installed | grep -w "gcc.%s"' % arch
    output = guest_session.guest_cmd_output(cmd=gcc_cmd)
    if not re.findall(r'gcc.%s' % arch, output):
        install_cmd = 'yum install -y ^gcc.`arch`'
        install_info = guest_session.guest_cmd_output(install_cmd)
        if re.findall('Complete', install_info):
            guest_session.test_print('Guest install gcc pkg successfully')
        else:
            guest_session.test_error('Guest failed to install gcc pkg')
    compile_cmd = 'cd /home;gcc %s -o dirty_page' % script
    guest_session.guest_cmd_output(cmd=compile_cmd)
    output = guest_session.guest_cmd_output('ls /home | grep -w "dirty_page"')
    if not output:
        guest_session.test_error('Failed to compile %s' % script)
    dirty_cmd = 'cd /home;./dirty_page > /dev/null &'
    guest_session.guest_cmd_output(dirty_cmd)
    if not utils_misc.wait_for_output(lambda: guest_session.
            guest_cmd_output('pgrep -x dirty_page'), 30):
        guest_session.test_error('Dirty_page program is not running in guest')

def iozone_test(guest_session):
    cmd='yum list installed | grep ^gcc.`arch`'
    output = guest_session.guest_cmd_output(cmd=cmd)
    if not output:
        output=guest_session.guest_cmd_output('yum install -y gcc')
        if not re.findall(r'Complete!', output):
            guest_session.test_error('gcc install Error')
    output = guest_session.guest_cmd_output('cd /home/iozone3_471;cd src; '
                                            'cd current;ls |grep -w iozone')
    if re.findall(r'No such file or directory', output):
        cmd = 'cd /home;wget http://www.iozone.org/src/current/iozone3_471.tar'
        guest_session.guest_cmd_output(cmd=cmd)
        time.sleep(10)
        guest_session.guest_cmd_output('cd /home;tar -xvf iozone3_471.tar')
        output = guest_session.guest_cmd_output('arch')
        if re.findall(r'ppc64le', output):
            cmd = 'cd /home/iozone3_471/src/current/;make linux-powerpc64'
            guest_session.guest_cmd_output(cmd=cmd)
        elif re.findall(r'x86_64', output):
            cmd = 'cd /home/iozone3_471/src/current/;make linux-AMD64 '
            guest_session.guest_cmd_output(cmd=cmd)
        else:
            cmd = 'cd /home/iozone3_471/src/current/;make linux-S390X '
            guest_session.guest_cmd_output(cmd=cmd)
    cmd = 'cd /home/iozone3_471/src/current/;./iozone -a > /dev/null &'
    guest_session.guest_cmd_output(cmd)
    if not utils_misc.wait_for_output(lambda: guest_session.
            guest_cmd_output('pgrep -x iozone'), 30):
        guest_session.test_error('Iozone program is not running in guest')

def create_disk(host_session, disk_dir, disk_name, disk_format, disk_size):
    cmd = 'ls %s | grep %s.%s' % (disk_dir, disk_name, disk_format)
    output = host_session.host_cmd_output(cmd=cmd)
    if output:
        cmd = 'rm -f %s/%s.%s' % (disk_dir, disk_name, disk_format)
        output = host_session.host_cmd_output(cmd=cmd)
        if output:
            host_session.test_error('Failed to delete %s.%s disk'
                                    % (disk_name, disk_format))
    cmd = 'qemu-img create -f %s %s/%s.%s %d' \
          % (disk_format, disk_dir, disk_name, disk_format, disk_size)
    output = host_session.host_cmd_output(cmd=cmd)
    if re.findall('Failed', output) or \
            re.findall('Command not found', output):
        host_session.test_error('Failed to create %s.%s disk' %
                                (disk_name, disk_format))
    cmd = 'qemu-img info %s/%s.%s' % (disk_dir, disk_name, disk_format)
    output = host_session.host_cmd_output(cmd=cmd)
    if re.findall('file format: %s' % disk_format, output):
        host_session.test_print('The format of %s disk is %s'
                                % (disk_name, disk_format))
    else:
        host_session.test_error('The format of %s disk is not %s'
                                % (disk_name, disk_format))

def stressapptest(guest_session, val_M, val_s):
    cmd = 'yum list installed | grep git.`arch`'
    output = guest_session.guest_cmd_output(cmd=cmd)
    if not output:
        guest_session.guest_cmd_output(cmd='yum install -y git')
        if not re.findall(r'Complete!', output):
            guest_session.test_error('git install Error')
    cmd = 'yum list installed | grep gcc-c++.`arch`'
    output = guest_session.guest_cmd_output(cmd=cmd)
    if not output:
        guest_session.guest_cmd_output(cmd='yum install -y git')
        if not re.findall(r'Complete!', output):
            guest_session.test_error('gcc-c++ install Error')

    cmd = 'stressapptest --help'
    output = guest_session.guest_cmd_output(cmd=cmd)
    if re.findall(r'command not found', output):
        guest_session.guest_cmd_output(cmd='rm -rf /home/stressapptest')
        guest_session.guest_cmd_output(cmd='cd /home; git clone https://github.com/'
                                       'stressapptest/stressapptest.git')
        guest_session.guest_cmd_output('cd /home/stressapptest; '
                                       './configure; make; make install')
        output = guest_session.guest_cmd_output(cmd=cmd)
        if re.findall(r'command not found', output):
            guest_session.test_error('Failed to install stressapptest')
    cmd = 'stressapptest -M %s -s %s > /dev/null &' % (val_M, val_s)
    guest_session.guest_cmd_output(cmd)
    if not utils_misc.wait_for_output(lambda: guest_session.
            guest_cmd_output('pgrep -x stressapptest'), 30):
        guest_session.test_error('stressapptest process is not running in guest')

