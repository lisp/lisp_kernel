from ipykernel.kernelapp import IPKernelApp
from .kernel import LispKernel
IPKernelApp.launch_instance(kernel_class=LispKernel)
