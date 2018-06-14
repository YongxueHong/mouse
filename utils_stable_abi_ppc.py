import time
import re

def create_iso(host_session, disk_dir, iso):
    host_session.host_cmd_output(cmd='rm -f %s/%s' % (disk_dir, iso))
    cmd = 'dd if=/dev/zero of=%s/%s bs=1M count=2048' % (disk_dir, iso)
    host_session.host_cmd_output(cmd=cmd)
    output = host_session.host_cmd_output(cmd='qemu-img info %s/%s' % (disk_dir, iso))
    if re.findall(r'file format: raw', output):
        host_session.test_print('The format of %s disk is raw' % iso)
    else:
        host_session.test_error('The format of %s disk is not raw' % iso)
        
def configure_host_hugepage(host_session, matrix, dst_ip, mount_point):
    chk_cmd_pg = 'cat /proc/meminfo | grep -i hugepage'
    if (matrix == 'P8_P9'):
        pg_count_p8 = '512'
        pg_count_p9 = '8'
        src = ''
        dst = ''
        chk_src_cpu = 'lscpu'
        chk_dst_cpu = 'ssh root@%s %s' % (dst_ip, chk_src_cpu)
        src_cpu = host_session.host_cmd_output(cmd=chk_src_cpu)
        dst_cpu = host_session.host_cmd_output(cmd=chk_dst_cpu)
        if re.findall(r'POWER9', src_cpu) and not re.findall(r'POWER9', dst_cpu):
            src = 'p9'
            pg_count_src = pg_count_p9
            dst = 'p8'
            pg_count_dst = pg_count_p8
        elif re.findall(r'POWER9', dst_cpu) and not re.findall(r'POWER9', src_cpu):
            src = 'p8'
            pg_count_src = pg_count_p8
            dst = 'p9'
            pg_count_dst = pg_count_p9

        src_echo_cmd = 'echo %s > /proc/sys/vm/nr_hugepages' % pg_count_src
        host_session.host_cmd_output(cmd=src_echo_cmd)
        output = host_session.host_cmd_output(cmd=chk_cmd_pg)
        if not re.findall(r'%s' % pg_count_src, output):
            host_session.test_error('Failed to configure hugepage of src host')

        dst_echo_cmd = 'ssh root@%s "echo %s > /proc/sys/vm/nr_hugepages"' \
                       % (dst_ip, pg_count_dst)
        host_session.host_cmd_output(cmd=dst_echo_cmd)
        cmd = 'ssh root@%s %s' % (dst_ip, chk_cmd_pg)
        output = host_session.host_cmd_output(cmd=cmd)
        if not re.findall(r'%s' % pg_count_dst, output):
            host_session.test_error('Failed to configure hugepage of dst host')

        if src == 'p9':
            smt_cmd = 'ppc64_cpu --smt=off'
            chk_smt = 'ppc64_cpu --smt'
            mode_cmd = 'echo N > /sys/module/kvm_hv/parameters/indep_threads_mode'
            chk_mode = 'cat /sys/module/kvm_hv/parameters/indep_threads_mode'
        elif dst =='p9':
            smt_cmd = 'ssh root@%s ppc64_cpu --smt=off' % dst_ip
            chk_smt = 'ssh root@%s ppc64_cpu --smt' % dst_ip
            mode_cmd = 'ssh root@%s "echo N > /sys/module/kvm_hv/parameters' \
                       '/indep_threads_mode"' % dst_ip
            chk_mode = 'ssh root@%s cat /sys/module/kvm_hv/parameters/' \
                       'indep_threads_mode' % dst_ip
        host_session.host_cmd_output(cmd=smt_cmd)
        output = host_session.host_cmd_output(cmd=chk_smt)
        if not re.findall(r'SMT is off', output):
            host_session.test_error('Failed to configure smt of p9 host')
        host_session.host_cmd_output(cmd=mode_cmd)
        output = host_session.host_cmd_output(cmd=chk_mode)
        # if not re.findall(r'N', output):
        #     host_session.test_error('Failed to configure indep_threads_mode of p9 host')
    elif (matrix == 'P8_P8'):
        pg_count = '512'
        pg_cmd = 'echo %s > /proc/sys/vm/nr_hugepages' % pg_count
        host_session.host_cmd_output(cmd=pg_cmd)
        output = host_session.host_cmd_output(cmd=chk_cmd_pg)
        if not re.findall(r'%s' % pg_count, output):
            host_session.test_error('Failed to configure hugepage of src host')
        cmd = 'ssh root@%s "%s"' % (dst_ip, pg_cmd)
        host_session.host_cmd_output(cmd=cmd)
        cmd = 'ssh root@%s %s' % (dst_ip, chk_cmd_pg)
        output = host_session.host_cmd_output(cmd=cmd)
        if not re.findall(r'%s' % pg_count, output):
            host_session.test_error('Failed to configure hugepage of dst host')
    elif (matrix == 'P9_P9'):
        output = host_session.host_cmd_output(cmd=chk_cmd_pg)
        if re.findall(r'1048576', output):
            pg_count = '8'
        elif re.findall(r'2048', output):
            pg_count = '4096'
        else:
            host_session.test_error('hugepagesz of p9 is neither 2m nor 1g')
        pg_cmd = 'echo %s > /proc/sys/vm/nr_hugepages' % pg_count
        host_session.host_cmd_output(cmd=pg_cmd)
        output = host_session.host_cmd_output(cmd=chk_cmd_pg)
        if not re.findall(r'%s' % pg_count, output):
            host_session.test_error('Failed to configure hugepage of src host')
        cmd = 'ssh root@%s "%s"' % (dst_ip, pg_cmd)
        host_session.host_cmd_output(cmd=cmd)
        cmd = 'ssh root@%s %s' % (dst_ip, chk_cmd_pg)
        output = host_session.host_cmd_output(cmd=cmd)
        if not re.findall(r'%s' % pg_count, output):
            host_session.test_error('Failed to configure hugepage of dst host')

    endtime = time.time() + 300
    while time.time() < endtime:
        output = host_session.host_cmd_output(cmd='mount')
        if not re.findall(r'none on %s type hugetlbfs' % mount_point, output):
            host_session.host_cmd_output(cmd='rm -rf %s' % mount_point)
            host_session.host_cmd_output(cmd='mkdir %s' % mount_point)
            host_session.host_cmd_output(cmd='mount -t hugetlbfs none %s' % mount_point)
        else:
            break

    endtime = time.time() + 300
    while time.time() < endtime:
        output = host_session.host_cmd_output(cmd='ssh root@%s mount' % dst_ip)
        if not re.findall(r'none on %s type hugetlbfs' % mount_point, output):
            host_session.host_cmd_output(cmd='ssh root@%s rm -rf %s' % (dst_ip, mount_point))
            host_session.host_cmd_output(cmd='ssh root@%s mkdir %s' % (dst_ip, mount_point))
            host_session.host_cmd_output(cmd='ssh root@%s mount -t hugetlbfs none %s'
                                             % (dst_ip, mount_point))
        else:
            break

def check_matrix(host_session, dst_ip, matrix):
    flag = ''
    if (matrix == 'P8_P9'):
        check_src_cmd = 'lscpu'
        check_dst_cmd = 'ssh root@%s %s' % (dst_ip, check_src_cmd)
        src_cpu = host_session.host_cmd_output(cmd=check_src_cmd)
        dst_cpu = host_session.host_cmd_output(cmd=check_dst_cmd)
        if not re.findall(r'POWER9', src_cpu) and re.findall(r'POWER9', dst_cpu):
            flag = 'p8_to_p9'
        elif re.findall(r'POWER9', src_cpu) and not re.findall(r'POWER9', dst_cpu):
            flag = 'p9_to_p8'
        else:
            host_session.test_error('This matrix maybe is not P8_P9')
    return flag

