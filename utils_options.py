import getopt
import sys
import os
import re
import yaml
from usr_exceptions import Error

BASE_FILE = os.path.dirname(os.path.abspath(__file__))

options_list = [
    "help",
    "show_category",
    "show_requirement=",
    "test_requirement=",
    "test_cases=",
    "verbose=",
    "src_host_ip=",
    "dst_host_ip=",
    "image_format=",
    "drive_format=",
    "share_images_dir="
]

help_info = "Usage: \n" \
            "python Start2Run.py --test_requirement=$requirement_id " \
            "[option] [option] [option]\n" \
            "python Start2Run.py --show_requirement=$requirement id \n" \
            "python Start2Run.py --show_category \n" \
            "python Start2Run.py --help \n" \
            "Standard option: \n" \
            "--help \n" \
            "  Display mouse tool help. \n" \
            "--show_category \n " \
            "  Display all category of requirement. \n" \
            "--show_requirement=$requirement id     \n" \
            "  Display all cases of requirement. \n" \
            "--test_requirement=$requirement id     \n" \
            "  Run all cases of requirement. \n" \
            "--test_cases=$case id0,$case id1,...   \n" \
            "  Run specific cases. \n" \
            "--verbose=yes|no \n" \
            "  Display the log of running. \n" \
            "--src_host_ip=xxx.xxx.xxx.xxx \n" \
            "  Set the source host ip for migration. \n" \
            "--dst_host_ip=xxx.xxx.xxx.xxx \n" \
            "  Set the destination host ip for migration. \n" \
            "--image_format=qcow2|raw|luks \n" \
            "  Set the type of image. \n" \
            "--drive_format=virtio-blk|virtio-scsi  \n" \
            "  Set the type of drive .\n" \
            "--share_images_dir=$directory name \n" \
            "  Set the shared directory of images.  \n" \
            "Please see README for more information."

class Options():
    def __init__(self):
        self.options = self.initial_options()

    def show_category(self):
        print ("This function is developing...")

    def show_requirement_info(self, id):
        file_path = ''
        search_name = id + '.yaml'
        index = 1
        for (thisdir, subshere, fileshere) in os.walk(BASE_FILE):
            for fname in fileshere:
                path = os.path.join(thisdir, fname)
                last_file = re.split(r'/', path)[-1]
                if search_name == last_file:
                    file_path = path
                    with open(file_path) as f:
                        params_dict = yaml.load(f)
                    print ("Category of requirement %s %s:"
                           % (id.upper().replace("_", "-"),
                              params_dict.get('test_requirement')['name']))
                    for case, info in params_dict['test_cases'].items():
                        print ("(%d) %s: %s" % (index,
                                                case.upper().replace("_", "-"),
                                                info['name'][0]))
                        index = index + 1

        if not file_path:
            info = 'No found corresponding yaml file : %s' % search_name
            raise Error(info)

    def usage(self):
        print ("%s" % help_info)

    def has_key(self, key):
        return self.options.has_key(key)

    def initial_options(self):
        opt_dict = {}
        try:
            options, args = getopt.getopt(sys.argv[1:], "", options_list)
            for opt, val in options:
                if opt == "--help":
                    self.usage()
                elif opt == "--show_category":
                    self.show_category()
                elif opt == "--show_requirement":
                    if val:
                        self.show_requirement_info(val)
                elif opt == "--test_requirement":
                    opt_dict[opt] = val
                elif opt == "--test_cases":
                    opt_dict[opt] = val
                elif opt == "--verbose":
                    opt_dict[opt] = val
                elif opt == "--src_host_ip":
                    opt_dict[opt] = val
                elif opt == "--dst_host_ip":
                    opt_dict[opt] = val
                elif opt == "--image_format":
                    opt_dict[opt] = val
                elif opt == "--drive_format":
                    opt_dict[opt] = val
                elif opt == "--share_images_dir":
                    opt_dict[opt] = val

        except getopt.GetoptError:
            print ("Please use Start2Run.py --help.")
            sys.exit(1)
        return opt_dict

    def set_pramas(self, params):
        for k, v in self.options.items():
            if k == '--verbose':
                params.get('verbose', v)
            if k == '--src_host_ip':
                params.get('src_host_ip', v)
            if k == '--dst_host_ip':
                params.get('dst_host_ip', v)
            if k == '--image_format':
                params.get('image_format', v)
            if k == '--drive_format':
                params.get('drive_format', v)
            if k == '--share_images_dir':
                params.get('share_images_dir', v)