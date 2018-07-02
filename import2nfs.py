#!/usr/bin/env python
import os
import re
import subprocess


BASE_DIR = os.path.dirname((os.path.abspath(__file__))) 
# avocado logs path
LOGS_DIR = '%s/test_logs/' % BASE_DIR
# nfs server
NFS = {'bos': 'xxxx',
       'pek': 'xxxx'
       }
# log url
LOG_URL = 'xxxx'
# mounting directory name
DIR_NAME = 'LOG'
# absolute mount path is the /tmp
MOUNT_DIR = os.path.join('/tmp', DIR_NAME)


def system_status_output(cmd):
    """Run a subprocess, returning its exit code and output."""
    sp = subprocess.Popen(cmd, stdout=subprocess.PIPE, shell=True)
    stdout, stderr = sp.communicate()
    return sp.poll(), stdout.decode()


def system_output(cmd):
    """Run a subprocess, returning its output."""
    return system_status_output(cmd)[1]


def get_avg_rtt(host):
    """
    Get average around trip time of the given host.

    :param host: Host name or ip address.
    """
    cmd_out = system_output("ping %s -c 5" % host)
    result = re.search(r"rtt min/avg.*?/([\d\.]+)", cmd_out)
    if not result:
        return float('+inf')
    return float(result.group(1))


def _get_default_nfs():
    """Choosing the fast nfs based on the avg rtt."""
    nfs_rtt = {}
    for k in list(NFS.keys()):
        nfs_rtt[k] = get_avg_rtt(NFS[k].split(':')[0])
    return min(nfs_rtt, key=nfs_rtt.get)


def _get_job_id():
    """Try to get the machine's job id, return None if id is not available."""
    try:
        # machines that run the beaker task successfully should have
        # this file containing job_id.
        with open(os.path.join('/home', 'job_env.txt')) as f:
            job_id = f.read().strip()
    except IOError:
        job_id = None
    return job_id


def _print_log_url(target, path):
    """Assemble log url and print it out."""
    # target in url means targeted nfs
    query_params = 'target=%s&path=%s' % (target, path)
    url = '?'.join([LOG_URL, query_params])
    print('logs available at: %s' % url)


def create_mount_dir(directory=MOUNT_DIR):
    """Create a mount point for the nfs."""
    if os.path.exists(directory):
        print('directory: %s exists, mkdir skiped.' % directory)
    else:
        os.makedirs(directory)
        print('%s is successfully created.' % directory)


def mount_nfs(source, target=MOUNT_DIR):
    """Mount the given nfs to the mount point."""
    if os.path.ismount(target):
        subprocess.check_call(['umount', '-v', target])
    subprocess.check_call(['mount', source, target])
    print('successfully mounted %s to %s' % (source, target))


def import_log(source, target, force=False, builtin_nfs=None):
    """Import test logs from source to target."""
    log_source = os.path.join(LOGS_DIR, source)
    log_dest = os.path.join(MOUNT_DIR, target)
    if not os.path.exists(log_dest):
        os.makedirs(log_dest)
    print('copying %s to %s , this may take a while.' % (log_source, log_dest))
    realpath = os.path.realpath(log_source)

    if force:
        # --force, ignore existent files
        subprocess.check_call(['cp', '-RT', realpath, log_dest])
    else:
        # by default it will not overwrite existent files
        subprocess.check_call(['cp', '-RTn', realpath, log_dest])
    if builtin_nfs:
        _print_log_url(builtin_nfs, target)
    print('\nimport done!')


if __name__ == '__main__':
    import argparse

    # default log source.
    source_dir = 'latest'
    # default log dest will be the beaker job id
    # if job id is not available or a -d is provide
    # it will under imported-logs
    dest_dir = _get_job_id() if _get_job_id() else 'imported-logs'
    # nfs
    print('pinging built-in NFSs, please be patient')
    default_nfs = _get_default_nfs()
    parser = argparse.ArgumentParser(description='import the test \
                                                  results to a NFS')
    parser.add_argument("-s", "--source",
                        help="log source directory,  "
                        "by default it uses %s" % source_dir,
                        default=source_dir,
                        action="store")
    parser.add_argument("-d", "--dest",
                        help="log destination directory,  "
                        "if you want to create nested directories,  "
                        "use dir1/dri2/dir3 ...  "
                        "by default it uses %s" % dest_dir,
                        default=dest_dir,
                        action="store")
    parser.add_argument("-n", "--nfs",
                        help="choose the nfs from [bos, pek] or  "
                        "provide your nfs source,  "
                        "by default it uses %s" % default_nfs,
                        default=default_nfs,
                        action="store")
    parser.add_argument("-f", "--force",
                        help="ignore existent files, force to copy",
                        action="store_true")

    args = parser.parse_args()
    # validate source
    if args.source not in os.listdir(LOGS_DIR):
        parser.error('%s is an invalid source.' % args.source)
    # validate dest, removing leading and trailing slashes
    args.dest = args.dest.strip('/')

    create_mount_dir()
    if args.nfs in list(NFS.keys()):
        mount_nfs(NFS[args.nfs])
        import_log(args.source, args.dest, args.force, args.nfs)
    else:
        mount_nfs(args.nfs)
        import_log(args.source, args.dest, args.force)

