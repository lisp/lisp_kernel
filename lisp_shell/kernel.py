from ipykernel.kernelbase import Kernel
from pexpect import replwrap, EOF
import pexpect

from subprocess import check_output
import os.path

import re
import signal
import syslog

__version__ = '0.0.1'

version_pat = re.compile(r'version (\d+(\.\d+)+)')

from .images import (
    extract_image_filenames, display_data_for_image, image_setup_cmd
)

# nyi : IREPLWrapper eliminated

class LispKernel(Kernel):
    implementation = 'lisp_kernel'
    implementation_version = __version__

    @property
    def language_version(self):
        m = version_pat.search(self.banner)
        return m.group(1)

    _banner = None

    @property
    def banner(self):
        if self._banner is None:
            self._banner = check_output(['lisp', '--version']).decode('utf-8')
        return self._banner

    language_info = {'name': 'bash',
                     'codemirror_mode': 'text/x-common-lisp',
                     'mimetype': 'application/sparql-query',
                     'file_extension': '.rq'}

    def __init__(self, **kwargs):
        Kernel.__init__(self, **kwargs)
        self._start_lisp()

    def _start_lisp(self):
        # Signal handlers are inherited by forked processes, and we can't easily
        # reset it from the subprocess. Since kernelapp ignores SIGINT except in
        # message handlers, we need to temporarily reset the SIGINT handler here
        # so that the child and its children are interruptible.
        syslog.openlog('kernel')
        sig = signal.signal(signal.SIGINT, signal.SIG_DFL)
        try:
            # Note: the next few lines mirror functionality in the
            # bash() function of pexpect/replwrap.py.  Look at the
            # source code there for comments and context for
            # understanding the code here.
            self.child = pexpect.spawn('lisp', ['--lispinit', '/opt/spocq/init.sxp'], echo=False,
                                       encoding='utf-8', codec_errors='replace')
            self.lispwrapper = replwrap.REPLWrapper(self.child, u'\*', None, '', '')
            self.child.expect_exact('* ', -1)
        finally:
            signal.signal(signal.SIGINT, sig)


    def process_output(self, output):
        syslog.syslog(output)
        if not self.silent:
            # Send standard output
            stream_content = {'name': 'stdout', 'text': output}
            self.send_response(self.iopub_socket, 'stream', stream_content)


    def run_command(self, code):
        # Split up multiline commands and feed them in bit-by-bit
        # in order to avoid buffer size limit
        res = []
        cmdlines = code.splitlines()
        if not cmdlines:
            raise ValueError("No command was given")
        syslog.syslog('run_command(' + code + ')')

        for line in cmdlines:
            syslog.syslog('run_command.line(' + line + ')')
            self.child.sendline(line)
        syslog.syslog('run_command.pad')
        self.child.sendline('')
        mode = self.child.expect(['\\* ', '\\d*] '], -1)
        self.process_output(self.child.before)
        if mode == 1 :
          syslog.syslog('run_command: abort')
          self.child.sendline(':abort')
          mode = self.child.expect('\\* ', -1)
          self.process_output(self.child.before)
                                 
    def do_execute(self, code, silent, store_history=True,
                   user_expressions=None, allow_stdin=False):
        self.silent = silent
        if not code.strip():
            return {'status': 'ok', 'execution_count': self.execution_count,
                    'payload': [], 'user_expressions': {}}
        syslog.syslog('do_execute(' + code + ')')
        interrupted = False
        try:
            # Note: timeout=None tells IREPLWrapper to do incremental
            # output.  Also note that the return value from
            # run_command is not needed, because the output was
            # already sent by IREPLWrapper.
            # self.lispwrapper.run_command(code, timeout=None)
            self.run_command(code)
        except KeyboardInterrupt:
            self.lispwrapper.child.sendintr()
            interrupted = True
            self.lispwrapper._expect_prompt()
            output = self.lispwrapper.child.before
            self.process_output(output)
        except EOF:
            output = self.lispwrapper.child.before + 'Restarting Lisp'
            self._start_lisp()
            self.process_output(output)

        if interrupted:
            return {'status': 'abort', 'execution_count': self.execution_count}

        syslog.syslog('return ok')
        return {'status': 'ok', 'execution_count': self.execution_count,
                'payload': [], 'user_expressions': {}}

    def do_complete(self, code, cursor_pos):
        syslog.syslog('do_complete(' + code + ')')
        code = code[:cursor_pos]
        default = {'matches': [], 'cursor_start': 0,
                   'cursor_end': cursor_pos, 'metadata': dict(),
                   'status': 'ok'}

        if not code or code[-1] == ' ':
            return default

        tokens = code.replace(';', ' ').split()
        if not tokens:
            return default

        matches = []
        token = tokens[-1]
        start = cursor_pos - len(token)

        if token[0] == '$':
            # complete variables
            cmd = 'compgen -A arrayvar -A export -A variable %s' % token[1:] # strip leading $
            output = self.lispwrapper.run_command(cmd).rstrip()
            completions = set(output.split())
            # append matches including leading $
            matches.extend(['$'+c for c in completions])
        else:
            # complete functions and builtins
            cmd = 'compgen -cdfa %s' % token
            output = self.lispwrapper.run_command(cmd).rstrip()
            matches.extend(output.split())

        if not matches:
            return default
        matches = [m for m in matches if m.startswith(token)]

        return {'matches': sorted(matches), 'cursor_start': start,
                'cursor_end': cursor_pos, 'metadata': dict(),
                'status': 'ok'}
