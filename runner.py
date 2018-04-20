import multiprocessing
import utils_modules
import os
import sys
import time
import traceback

class Status:
    PASS = "\033[92mPASS\033[00m"
    ERROR = "\033[91mERROR\033[00m"
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNINGYELLOW = '\033[93m'
    FAILRED = '\033[91m'
    ENDC = '\033[5m'

class CaseRunner(object):
    def __init__(self, params):
        self._bars = ['|', '/', '-', '\\', '|', '/', '-', '\\']
        self._params = params
        self._requirement_id = params.get_requirement_id()
        self._requirement_name = params.get('test_requirement')['name']
        self._case_list = []
        self._case_dict = {}
        self._case_dict = utils_modules.setup_modules(self._requirement_id)
        self._only_case_list = params.get('only_case_list')
        self._run_result = {}
        self._run_result['error_cases'] = []
        self._run_result['pass_cases'] = []
        self._run_result['case_time'] = {}
        self._run_result['total_time'] = 0
        self.get_case_list()
        self._run_result['TOTAL'] = len(self._case_list)

    def timeout_log_file(self, case):
        log_file_list = []
        test_log_dir = os.path.join(self._params.get('log_dir'),
                                    case + '-'
                                    + self._params.get('sub_dir_timestamp')
                                    +'_logs')
        log = test_log_dir + '/' + 'long_debug.log'
        log_file_list.append(log)
        log = test_log_dir + '/' + 'short_debug.log'
        log_file_list.append(log)
        timeout_info = 'Failed to run %s under %s sec.' \
                       % (case, self._params.get('timeout'))
        for log in log_file_list:
            if os.path.exists(log):
                if self._params.get('verbose') == 'no':
                    with open(log, "a") as run_log:
                        timestamp = time.strftime("%Y-%m-%d-%H:%M:%S")
                        run_log.write("%s: %s\n" % (timestamp, timeout_info))
                if self._params.get('verbose') == 'yes':
                    with open(log, "a") as run_log:
                        timestamp = time.strftime("%Y-%m-%d-%H:%M:%S")
                        run_log.write("%s: %s\n" % (timestamp, timeout_info))
                    print (timeout_info)

    def display_process_bar(self, processor, start_time):
        sys.stdout.write(' ')
        sys.stdout.flush()
        run_timeout = False
        while processor.is_alive():
            for bar in self._bars:
                if float(time.time() - start_time) > \
                        float(int(self._params.get('timeout'))):
                    run_timeout = True
                    break
                sys.stdout.write('\b')
                sys.stdout.write(bar)
                sys.stdout.flush()
                time.sleep(0.5)
            if run_timeout == True:
                break

    def get_case_list(self):
        times = int(self._params.get('repeat_times'))
        if self._only_case_list:
            for i in range(times):
                for case in self._only_case_list:
                    self._case_list.append(case)
        else:
            for i in range(times):
                for k, v in self._params.get('test_cases').items():
                    self._case_list.append(k)

    def display_sum_results(self):
        self._run_result['ERROR'] = len(self._run_result['error_cases'])
        self._run_result['PASS'] = self._run_result['TOTAL'] \
                                   - self._run_result['ERROR']

        print ('\033[93m%s\033[00m' % ('*' * 94))
        print ('RESULTS [%s]:' % (self._requirement_id.upper().replace('_', '-')))
        print ('==>TOTAL : %s' % (self._run_result['TOTAL']))
        print ('==>PASS : %s ' % (self._run_result['PASS']))
        if self._run_result['PASS'] != 0:
            cnt = 1
            for pass_case in self._run_result['pass_cases']:
                print ('   %d: %s-%s (%s)'
                       % (cnt, pass_case.upper().replace('_', '-'),
                          self._params.get('test_cases')[pass_case]['name'],
                          self._run_result['case_time'][str(pass_case)]))
                cnt = cnt + 1
        print ('==>ERROR : %s '  %(self._run_result['ERROR']))
        if self._run_result['ERROR'] != 0:
            cnt = 1
            for error_case in self._run_result['error_cases']:
                print ('   %d: \033[91m%s\033[00m-%s (%s)'
                       % (cnt, error_case.upper().replace('_', '-'),
                          self._params.get('test_cases')[error_case]['name'],
                          self._run_result['case_time'][str(error_case)]))
                cnt = cnt + 1
        print ('==>RUN TIME : %s min %s sec '
               % (int(self._run_time / 60),
                  int(self._run_time - int(self._run_time / 60) * 60)))
        print ('==>TEST LOG : %s ' % (self._params.get('log_dir')))
        print ('\033[93m%s\033[00m' % ('*' * 94))

    def _run(self, case, case_queue):
        log_file_list = []
        try:
            getattr(self._case_dict[case], "run_case")(self._params)
        except KeyboardInterrupt:
            raise
        except :
            test_log_dir = os.path.join(self._params.get('log_dir'), case + '_logs')
            log_file = test_log_dir + '/' + 'long_debug.log'
            log_file_list.append(log_file)
            log_file = test_log_dir + '/' + 'short_debug.log'
            log_file_list.append(log_file)
            for log_file in log_file_list:
                if os.path.exists(log_file):
                    if self._params.get('verbose') == 'no':
                        traceback.print_exc(file=open(log_file, "a"))
                    if self._params.get('verbose') == 'yes':
                        traceback.print_exc(file=open(log_file, "a"))
                        traceback.print_exc()
            case_queue.put(case)

    def main_run(self):
        start_time = time.time()
        cont = 1
        case_queue = multiprocessing.Queue()
        if self._params.get('verbose') == 'no':
            print ('\033[94m%s Test Requirement: %s(%s) %s\033[00m'
                   % (('=' * 25), self._requirement_id.upper().replace('_', '-'),
                      self._requirement_name, ('=' * 25),))
        for case in self._case_list:
            timestamp = time.strftime("%Y-%m-%d-%H:%M:%S")
            self._params.get('sub_dir_timestamp', timestamp)
            if self._params.get('verbose') == 'no':
                info = '--> Running case(%s/%s): %s-%s ' \
                       % (cont, self._run_result['TOTAL'],
                          case.upper().replace('_', '-'),
                          self._params.get('test_cases')[case]['name'])
                sys.stdout.write(info)
                sys.stdout.flush()
            sub_proc = multiprocessing.Process(target=self._run,
                                               args=(case, case_queue))
            sub_proc.start()
            self._sub_start_time = time.time()
            sub_proc.name = case
            if self._params.get('verbose') == 'no':
                self.display_process_bar(sub_proc, start_time=self._sub_start_time)
            else:
                sub_proc.join(timeout=float(int(self._params.get('timeout'))))

            self._sub_end_time = time.time()
            self._sub_run_time = self._sub_end_time - self._sub_start_time
            self._case_time = "%s min %s sec" % (int(self._sub_run_time / 60),
                                           int(self._sub_run_time -
                                               int(self._sub_run_time / 60) * 60))
            if float(self._sub_run_time) > float(int(self._params.get('timeout'))):
                sub_proc.terminate()
                self._run_result['error_cases'].append(case)
                self._run_result['case_time'][case] = self._case_time
                self.timeout_log_file(case)

            if not case_queue.empty():
                self._run_result['error_cases'].append(case_queue.get())
                self._run_result['case_time'][case] = self._case_time
            else:
                self._run_result['pass_cases'].append(case)
                self._run_result['case_time'][case] = self._case_time

            if self._params.get('verbose') == 'no':
                sys.stdout.write('\b')
                if case in self._run_result['error_cases']:
                    info = '(%s min %s sec)--- %s.\n' \
                           % (int(self._sub_run_time / 60),
                              int(self._sub_run_time
                                  - int(self._sub_run_time / 60) * 60),
                              Status.ERROR)
                else:
                    info = '(%s min %s sec)--- %s.\n' \
                           % (int(self._sub_run_time / 60),
                              int(self._sub_run_time
                                  - int(self._sub_run_time / 60) * 60),
                              Status.PASS)
                sys.stdout.write(info)
                sys.stdout.flush()
            cont = cont + 1

        end_time = time.time()
        self._run_time = end_time - start_time

        self.display_sum_results()
