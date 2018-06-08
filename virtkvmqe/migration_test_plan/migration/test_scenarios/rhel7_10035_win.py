from __future__ import division
import time
from utils_host import HostSession
from monitor import RemoteQMPMonitor
import re
from vm import CreateTest
import utils_migration

def run_case(params):
    src_host_ip = params.get('src_host_ip')
    dst_host_ip = params.get('dst_host_ip')
    qmp_port = int(params.get('qmp_port'))
    serial_port = int(params.get('serial_port'))
    incoming_port = params.get('incoming_port')
    test = CreateTest(case_id='rhel7_10035', params=params)
    id = test.get_id()
    src_host_session = HostSession(id, params)
    downtime = 10000
    speed_m = 20
    speed = speed_m * 1024 * 1024
    gap_speed = 5
    gap_downtime = 5000

    test.main_step_log('1.Boot up a guest on source host')
    src_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_guest(cmd=src_qemu_cmd, vm_alias='src')
    src_remote_qmp = RemoteQMPMonitor(id, params, src_host_ip, qmp_port)

    test.sub_step_log('1.1 Connecting to src serial --- ignore for windows guest')

    test.main_step_log('2. Running some application inside guest --- ignore for windows guest')

    test.main_step_log('3. Boot up the guest on destination host')
    incoming_val = 'tcp:0:%s' % incoming_port
    params.vm_base_cmd_add('incoming', incoming_val)
    dst_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_remote_guest(cmd=dst_qemu_cmd, ip=dst_host_ip,
                                       vm_alias='dst')
    dst_remote_qmp = RemoteQMPMonitor(id, params, dst_host_ip, qmp_port)
    test.sub_step_log('Wait 90s for guest boot up')
    time.sleep(90)
    test.main_step_log('4.Set  the migration speed and downtime')
    downtime_cmd = '{"execute":"migrate-set-parameters","arguments":' \
                   '{"downtime-limit": %d}}' % downtime
    src_remote_qmp.qmp_cmd_output(cmd=downtime_cmd)
    speed_cmd = '{"execute":"migrate-set-parameters","arguments":' \
                '{"max-bandwidth": %d}}' % speed
    src_remote_qmp.qmp_cmd_output(cmd=speed_cmd)
    paras_chk_cmd = '{"execute":"query-migrate-parameters"}'
    output = src_remote_qmp.qmp_cmd_output(cmd=paras_chk_cmd)
    if re.findall(r'"downtime-limit": %d' % downtime, output) \
            and re.findall(r'"max-bandwidth": %d' % speed, output):
        test.test_print('Change downtime and speed successfully')
    else:
        test.test_error('Failed to change downtime and speed')

    test.main_step_log('5. Migrate guest from source host to destination host')
    check_info = utils_migration.do_migration(remote_qmp=src_remote_qmp,
                                              migrate_port=incoming_port,
                                              dst_ip=dst_host_ip,
                                              downtime_val=downtime,
                                              speed_val=speed)
    if (check_info == False):
        test.test_error('Migration timeout')

    test.main_step_log('6.After migration finished,check migration statistics')
    cmd = '{"execute":"query-migrate"}'
    output = eval(src_remote_qmp.qmp_cmd_output(cmd=cmd))

    transferred_ram = int(output.get('return').get('ram').get('transferred'))
    transferred_ram_cal = transferred_ram / 1024 / 1024
    total_time = int(output.get('return').get('total-time'))
    total_time_cal = total_time / 1000
    speed_cal = transferred_ram_cal / total_time_cal
    gap_cal = abs(speed_cal - speed_m)
    if (gap_cal >= gap_speed):
        test.test_error('The real migration speed %s M/s and expected speed '
                        'have a gap more than %d M/s' % (speed_cal, gap_speed))
    else:
        test.test_print('The real migration speed is not more or less than '
                        'expected speed by %d M/s' % gap_speed)

    real_downtime = int(output.get('return').get('downtime'))
    gap_cal = real_downtime - downtime
    if (gap_cal > gap_downtime):
        test.test_error('The real migration downtime and expected downtime '
                        'have a gap more than %d milliseconds' % gap_downtime)
    else:
        test.test_print('The real migration downtime is not more or less than '
                        'expected downtime by %d milliseconds' % gap_downtime)

    test.main_step_log('7.After migration finished, check the status of guest')
    test.sub_step_log('4.1 Check dst guest status')
    status = dst_remote_qmp.qmp_cmd_output('{"execute":"query-status"}')
    if '\"status\": \"running\"' not in status:
        dst_remote_qmp.test_error('Dst vm is not running')

    test.sub_step_log('4.2. Reboot guest')
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

