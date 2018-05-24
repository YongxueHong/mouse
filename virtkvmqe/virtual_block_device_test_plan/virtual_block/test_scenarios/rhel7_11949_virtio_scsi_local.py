from utils_host import HostSession
from utils_guest import GuestSession
from monitor import RemoteSerialMonitor, RemoteQMPMonitor
from vm import CreateTest
import re
import time
import os
from utils_iscsi import IscsiTarget, IscsiInitiator
project_file = os.path.dirname(os.path.dirname(os.path.dirname
                                           (os.path.dirname
                                            (os.path.dirname
                                             (os.path.abspath(__file__))))))
tmp_file = project_file


def run_case(params):
    test = CreateTest(case_id='rhel7_11949_virtio_scsi_local', params=params)
    id = test.get_id()

    target_ip = '10.66.10.208'

    test.main_step_log('1. boot a guest with a lvm.')
    test.sub_step_log('1.1 Initial iscsi target.')
    iqn = 'iqn.2018-06.com.yhong:target'
    target = IscsiTarget(id, params, target_ip)
    target.create_backstore(file_or_dev='/tmp/yhong', backend_name='yhong', size='1G')
    target.create_iscsi_target_portal(iqn)
    target.create_lun(iqn, 'yhong', True)
    target.disable_acl(iqn)

    test.sub_step_log('1.2 connect to iscsi target.')
    initiator = IscsiInitiator(id, params)
    initiator.discovery_iscsi_target(target_ip)
    initiator.connect_iscsi_target(iqn)
    initiator.disconnect_iscsi_target(iqn)

    test.main_step_log(
        '2. verify the it\'s a good lvm: '
        'in guest dd a file to this data disk in lvm.')

    test.main_step_log('3. in host set this lun as readonly')

    test.main_step_log('4. launch the KVM guest again with the readonly lvm.')

    test.main_step_log('5. in host change lun to r/w')

    test.main_step_log(
        '6. launch the KVM guest again with the read/write lvm.')

    test.main_step_log('7. in guest dd a new file to this data disk')