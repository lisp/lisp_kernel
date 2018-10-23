A Jupyter kernel for lisp

This requires IPython 3 and a Lisp executable - eg sbcl saved with its core or a bash wrapper

To install::

    pip install lisp_shell
    python -m lisp_shell.install

To use it, run one of:

.. code:: shell

    jupyter notebook
    # In the notebook interface, select lisp_shell from the 'New' menu
    jupyter qtconsole --kernel lisp_shell
    jupyter console --kernel lisp_shell

For details of how this works, see the Jupyter docs on `wrapper kernels
<http://jupyter-client.readthedocs.org/en/latest/wrapperkernels.html>`_, and
Pexpect's docs on the `replwrap module
<http://pexpect.readthedocs.org/en/latest/api/replwrap.html>`_

This is adapted from the bash kernel (https://github.com/takluyver/bash_kernel)

