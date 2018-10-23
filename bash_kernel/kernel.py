from ipykernel.kernelbase import Kernel
from pexpect import replwrap, EOF
import pexpect

from subprocess import check_output
import os.path

import re
import signal

__version__ = '0.0.1'

version_pat = re.compile(r'version (\d+(\.\d+)+)')

from .images import (
    extract_image_filenames, display_data_for_image, image_setup_cmd
)

# nyi : IREPLWrapper eliminated

class LispKernel(Kernel):
    implementation = 'lisp_kernel'
    implementation_version = __version__
    executable = 'lisp'

    @property
    def language_version(self):
        m = version_pat.search(self.banner)
        return m.group(1)

    _banner = None

    @property
    def banner(self):
        if self._banner is None:
            self._banner = check_output([executable, '--version']).decode('utf-8')
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
        # so that bash and its children are interruptible.
        sig = signal.signal(signal.SIGINT, signal.SIG_DFL)
        try:
            # Note: the next few lines mirror functionality in the
            # bash() function of pexpect/replwrap.py.  Look at the
            # source code there for comments and context for
            # understanding the code here.
            child = pexpect.spawn(executable, ['--lispinit', 'init.sxp'], echo=False,
                                  encoding='utf-8', codec_errors='replace')
            ps1 = replwrap.PEXPECT_PROMPT[:5] + u'\[\]' + replwrap.PEXPECT_PROMPT[5:]
            ps2 = replwrap.PEXPECT_CONTINUATION_PROMPT[:5] + u'\[\]' + replwrap.PEXPECT_CONTINUATION_PROMPT[5:]
            prompt_change = u"PS1='{0}' PS2='{1}' PROMPT_COMMAND=''".format(ps1, ps2)

            # Using IREPLWrapper to get incremental output
            self.lispwrapper = REPLWrapper(child, u'\>', '',
                                            line_output_callback=self.process_output)
        finally:
            signal.signal(signal.SIGINT, sig)


    def process_output(self, output):
        if not self.silent:
            # Send standard output
            stream_content = {'name': 'stdout', 'text': output}
            self.send_response(self.iopub_socket, 'stream', stream_content)


    def do_execute(self, code, silent, store_history=True,
                   user_expressions=None, allow_stdin=False):
        self.silent = silent
        if not code.strip():
            return {'status': 'ok', 'execution_count': self.execution_count,
                    'payload': [], 'user_expressions': {}}

        interrupted = False
        try:
            # Note: timeout=None tells IREPLWrapper to do incremental
            # output.  Also note that the return value from
            # run_command is not needed, because the output was
            # already sent by IREPLWrapper.
            self.lispwrapper.run_command(code.rstrip(), timeout=None)
        except KeyboardInterrupt:
            self.lispwrapper.child.sendintr()
            interrupted = True
            self.lispwrapper._expect_prompt()
            output = self.lispwrapper.child.before
            self.process_output(output)
        except EOF:
            output = self.lispwrapper.child.before + 'Restarting Bash'
            self._start_bash()
            self.process_output(output)

        if interrupted:
            return {'status': 'abort', 'execution_count': self.execution_count}

        try:
            exitcode = int(self.lispwrapper.run_command('echo $?').rstrip())
        except Exception:
            exitcode = 1

        if exitcode:
            error_content = {'execution_count': self.execution_count,
                             'ename': '', 'evalue': str(exitcode), 'traceback': []}

            self.send_response(self.iopub_socket, 'error', error_content)
            error_content['status'] = 'error'
            return error_content
        else:
            return {'status': 'ok', 'execution_count': self.execution_count,
                    'payload': [], 'user_expressions': {}}

    def do_complete(self, code, cursor_pos):
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
