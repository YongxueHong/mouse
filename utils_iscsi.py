from vm import TestCmd
from utils_host import HostSession
import re
import os
from utils_session import ShellSession
import platform
import time


class Iscsi(TestCmd):
    def __init__(self, id, params):
        super(Iscsi, self).__init__(id, params)


class IscsiTarget(ShellSession):
    def __init__(self, id, params, target_ip):
        super(IscsiTarget, self).__init__(
            id, params, target_ip, r'^\[.*\][\#\$]\s*$', '[root@%s ~]#' % target_ip)
        self._target_ip = target_ip
        self._check_iscsi_target_tool()
        self._enable_iscsi_target_server()

    def _check_iscsi_target_tool(self):
        cmd = 'yum list installed | grep targetcli'
        ShellSession.cmd_output_safe(self, cmd)

    def _install_iscsi_target_tool(self):
        cmd = 'yum install -y targetcli'
        status, output = ShellSession.cmd_status_output(self, cmd)
        if status:
            ShellSession.test_error(self, 'Failed to install targetcli')

    def _enable_iscsi_target_server(self):
        cmd = 'iptables -F'
        ShellSession.cmd_output(self, cmd)
        cmd = 'systemctl start target'
        ShellSession.cmd_output(self, cmd)
        cmd = 'systemctl enable target'
        ShellSession.cmd_output(self, cmd)
        output = ShellSession.cmd_output(self, 'systemctl status target -l')
        if not re.findall(r'Active: active', output):
            ShellSession.test_error(self, 'Failed to start target server.')

    def _create_fileio_file(self, path):
        self._fileio_path = path
        if os.path.exists(path):
            pass
        else:
            ShellSession.cmd_output(self, 'mkdir -p %s' % path)

    def create_backstore(self, file_or_dev, backend_name, size, write_back='false'):
        if re.findall(r'/', file_or_dev):
            path = '/'
            for p in file_or_dev.split('/')[0:-1]:
                path = os.path.join(path, p)
            self._create_fileio_file(path)
        else:
            ShellSession.test_error(self, 'Please specify a path for backstore.')
        cmd = "echo \"backstores/fileio/ create file_or_dev=%s name=%s size=%s " \
              "write_back=%s\" | targetcli" \
              % (file_or_dev, backend_name, size, write_back)
        output = ShellSession.cmd_output(self, cmd)
        if 'Storage object fileio/%s exists' % backend_name in output:
            cmd = "echo \"backstores/fileio/ delete %s\" | targetcli" % backend_name
            ShellSession.cmd_output(self, cmd)
            cmd = "echo \"backstores/fileio/ create file_or_dev=%s name=%s size=%s " \
                  "write_back=%s\" | targetcli" % (
                  file_or_dev, backend_name, size, write_back)
            ShellSession.cmd_output(self, cmd)

    def delete_iscsi_target_portal(self, iqn):
        return ShellSession.cmd_output(
            self, 'echo \"iscsi/ delete %s\" | targetcli' % iqn)

    def create_iscsi_target_portal(self, iqn):
        self.delete_iscsi_target_portal(iqn)
        if 'This Target already exists in configFS' \
                in ShellSession.cmd_output(
            self, 'echo \"iscsi/ create %s\" | targetcli' % iqn):
            ShellSession.test_error(self, 'Failed to create target %s' % iqn)

    def create_lun(self, iqn, backend_name, fileio_mode=False, block_mode=False):
        if not fileio_mode and not block_mode:
            ShellSession.test_error(self, 'Please specify fileio '
                                          '| block mode for lun.')
        elif fileio_mode:
            cmd = 'echo \"iscsi/%s/tpg1/luns/ create /backstores/fileio/%s\" ' \
                  '| targetcli' % (iqn, backend_name)
        elif block_mode:
            cmd = 'echo \"iscsi/%s/tpg1/luns/ create /backstores/block/%s\" ' \
                  '| targetcli' % (iqn, backend_name)
        ShellSession.cmd_output(self, cmd)

    def create_acl(self):
        # TODO
        pass

    def disable_acl(self, iqn):
        cmd = 'echo \"iscsi/%s/tpg1/ set attribute authentication=0\"' \
              '| targetcli' % iqn
        ShellSession.cmd_output(self, cmd)
        cmd = 'echo \"iscsi/%s/tpg1/ set attribute demo_mode_write_protect=0\"' \
              '| targetcli' % iqn
        ShellSession.cmd_output(self, cmd)
        cmd = 'echo \"iscsi/%s/tpg1/ set attribute generate_node_acls=1\"' \
              '| targetcli' % iqn
        ShellSession.cmd_output(self, cmd)


class IscsiInitiator(HostSession):
    def __init__(self, id, params):
        super(IscsiInitiator, self).__init__(id, params)
        self._check_iscsi_initiator()
        self._enable_iscsiid()

    def _check_iscsi_initiator(self):
        cmd = 'yum list installed | grep iscsi-initiator-utils'
        output = HostSession.host_cmd_output(self, cmd)
        if 'iscsi-initiator-utils.%s' % platform.machine() not in output:
            self._install_iscsi_initia_tool()

    def _install_iscsi_initia_tool(self):
        cmd = 'yum install -y iscsi-initiator-utils'
        output = HostSession.host_cmd_output(self, cmd)
        if HostSession.host_cmd_output(self, 'echo $?'):
            HostSession.test_error(self, 'Failed to install iscsi-initiator-utils')

    def discovery_iscsi_target(self, target_ip):
        cmd = 'iscsiadm --mode discovery --type sendtargets --portal %s' \
              % target_ip
        output = HostSession.host_cmd_output(self, cmd)
        if HostSession.host_cmd_output(self, 'echo $?'):
            HostSession.test_error(self, 'Failed to discovery iscsi target')
        target_list = re.findall('iqn.\d{4}-\d{2}.com..*:.*', output)
        if not target_list:
            HostSession.test_print(self, 'No found any iscsi target.')
        HostSession.test_print(self, 'iSCSi target: %s' % target_list)
        return target_list

    def _enable_iscsiid(self):
        HostSession.host_cmd_output(self, 'systemctl enable iscsid iscsi')
        HostSession.host_cmd_output(self, 'systemctl start iscsid iscsi')
        output = HostSession.host_cmd_output(
            self, 'systemctl status iscsid iscsi -l')
        if not re.findall(r'Active: active', output):
            ShellSession.test_error(self, 'Failed to start iscsid server.')

    def connect_iscsi_target(self, iqn):
        output = HostSession.host_cmd_output(self, 'iscsiadm -m node -T %s -l'
                                             % iqn)
        if 'successful' not in output:
            HostSession.test_error(self, 'Failed to login to target.')

    def disconnect_iscsi_target(self, iqn):
        output = HostSession.host_cmd_output(self, 'iscsiadm -m node -T %s -u'
                                             % iqn)
        if 'successful' not in output:
            HostSession.test_error(self, 'Failed to logout to target.')
