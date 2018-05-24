import aexpect
from vm import Test, TestCmd
import re


class ShellSession(TestCmd):
    def __init__(self, id, params, ip, prompt, cmd_custom_prompt=''):
        self._prompt = prompt
        self._cmd_prompt = cmd_custom_prompt
        self._ip = ip
        self._linesep = '\n'
        self._passwd = 'kvmautotest'
        super(ShellSession, self).__init__(id, params)
        self._create_session()

    def _create_session(self):
        timeout = 300
        cmd = ("ssh -o UserKnownHostsFile=/dev/null "
               "-o PreferredAuthentications=password -p %s %s@%s"
               % (22, 'root', self._ip))
        self._session = aexpect.ShellSession(command=cmd, prompt=self._prompt,
                                             linesep=self._linesep)
        try:
            self._handle_prompts('root', self._passwd, self._prompt, timeout)
            TestCmd.test_print(self, 'Connect %s session successfully.'
                               % self._ip)
        except Exception:
            self._session.close()
            TestCmd.test_error(self,
                               'Failed to Connect %s session under %s sec.'
                               % (self._ip, timeout))

    def _handle_prompts(self, username, password, prompt, timeout=60):
        password_prompt_count = 0
        login_prompt_count = 0
        while True:
            try:
                match, text = self._session.read_until_last_line_matches(
                    [r"[Aa]re you sure",
                     r"[Pp]assword:\s*",
                     r"(?<![Ll]ast).*[Ll]ogin:\s*$",
                     r"[Cc]onnection.*closed",
                     r"[Cc]onnection.*refused",
                     r"[Ww]arning",
                     r"[Ee]nter.*username",
                     r"[Ee]nter.*password",
                     prompt],
                    timeout=timeout, internal_timeout=0.5)
                if match == 0:  # "Are you sure you want to continue connecting"
                    self._session.sendline("yes")
                    continue
                elif match == 1 or match == 7:  # "password:"
                    if password_prompt_count == 0:
                        self._session.sendline(password)
                        password_prompt_count += 1
                        continue
                    else:
                        pass
                elif match == 2 or match == 7:  # "login:"
                    if login_prompt_count == 0 and password_prompt_count == 0:
                        self._session.sendline(username)
                        login_prompt_count += 1
                        continue
                    else:
                        pass
                elif match == 3:  # "Connection closed"
                    TestCmd.test_error(self, "Client said 'connection closed'")
                    break
                elif match == 4:  # "Connection refused"
                    TestCmd.test_error(self, "Client said 'connection refused'")
                    break
                elif match == 6:  # "Warning added RSA"
                    TestCmd.test_print(self,
                                       "Got 'Warning added RSA to known host list")
                    break
                elif match == 8:  # prompt
                    TestCmd.test_print(self,"Got shell prompt -- logged in")
                    break
            except aexpect.ExpectTimeoutError as e:
                TestCmd.test_error(self, e.output)
            except aexpect.ExpectProcessTerminatedError as e:
                TestCmd.test_error(self, e.output)

    def cmd_output_safe(self, cmd, timeout=300, verbose=True):
        if verbose:
            TestCmd.test_print(self, '%s %s' % (self._cmd_prompt, cmd))
        output = self._session.cmd_output_safe(cmd=cmd, timeout=timeout)
        output = TestCmd.remove_cmd_echo_blank_space(self, output=output, cmd=cmd)
        if verbose:
            TestCmd.test_print(self, output)
        if re.findall(r'command not found', output) or re.findall(r'-bash', output):
            TestCmd.test_error(self, 'Command %s failed' % cmd)
        return output

    def cmd_status_output(self, cmd, timeout=300, verbose=True):
        if verbose:
            TestCmd.test_print(self, '%s %s' % (self._cmd_prompt, cmd))
        status, output = self._session.cmd_status_output(cmd=cmd, timeout=timeout)
        output = TestCmd.remove_cmd_echo_blank_space(self, output=output, cmd=cmd)
        if verbose:
            TestCmd.test_print(self, (status,output))
        if re.findall(r'command not found', output) or re.findall(r'-bash', output):
            TestCmd.test_error(self, 'Command %s failed' % cmd)
        return (int(status), output)

    def cmd_status(self, cmd, timeout=300, verbose=True):
        if verbose:
            TestCmd.test_print(self, '%s %s' % (self._cmd_prompt, cmd))
        status = self._session.cmd_status(cmd=cmd, timeout=timeout)
        status = TestCmd.remove_cmd_echo_blank_space(self, output=status, cmd=cmd)
        if verbose:
            TestCmd.test_print(self, status)
        return status

    def cmd_output(self, cmd, timeout=300, verbose=True):
        if verbose:
            TestCmd.test_print(self, '%s %s' % (self._cmd_prompt, cmd))
        output = self._session.cmd_output(cmd=cmd, timeout=timeout)
        output = TestCmd.remove_cmd_echo_blank_space(self, output=output, cmd=cmd)
        if verbose:
            TestCmd.test_print(self, output)
        return output

    def cmd(self, cmd, timeout=300, verbose=True):
        if verbose:
            TestCmd.test_print(self, '%s %s' % (self._cmd_prompt, cmd))
        output = self._session.cmd(cmd=cmd, timeout=timeout)
        output = TestCmd.remove_cmd_echo_blank_space(self, output=output, cmd=cmd)
        if verbose:
            TestCmd.test_print(self, output)
        return output

    def close(self):
        TestCmd.test_print(self,
                        'Closed session(%s).' % (self._ip))
        self._session.close()

    def __del__(self):
        TestCmd.test_print(self,
                        'Closed session(%s).' % (self._ip))
        self._session.close()