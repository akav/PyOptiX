import logging
import re
import os
import shlex
import fnmatch
from subprocess import check_call, CalledProcessError


logger = logging.getLogger(__name__)


class Compiler(object):
    DEFAULTS = {
        'output_path': '/tmp/pyoptix/ptx',
        'include_paths': ['/usr/local/optix/include'],
        'arch': 'sm_21',
        'use_fast_math': True,
    }

    def __init__(self, output_path=DEFAULTS['output_path'], include_paths=None, arch=DEFAULTS['arch'],
                 use_fast_math=DEFAULTS['use_fast_math']):

        self.include_paths = Compiler.DEFAULTS['include_paths']
        if include_paths:
            self.include_paths.extend(include_paths)

        self.output_path = output_path
        self.arch = arch
        self.use_fast_math = use_fast_math

        if not os.path.exists(self.output_path):
            os.makedirs(self.output_path)

    def _is_compile_required(self, cu_file_path, output_file_path):
        if os.path.isfile(output_file_path):
            ptx_file_mtime = os.path.getmtime(output_file_path)
            cu_file_mtime = os.path.getmtime(cu_file_path)

            if cu_file_mtime > ptx_file_mtime:
                return True
            elif self._has_modified_includes(cu_file_path, ptx_file_mtime):
                return True
            else:
                return False

        else:
            return True

    def _has_modified_includes(self, file_path, modified_after, depth=4):
        if depth == 0:
            return False

        include_pattern = '#include\s*"(.*)"'

        with open(file_path) as f:
            content = f.read()
            for included_path in re.findall(include_pattern, content):
                for compiler_include_path in self.include_paths:
                    included_file_path = os.path.join(compiler_include_path, included_path)
                    if not os.path.exists(included_file_path):
                        continue

                    included_file_mtime = os.path.getmtime(included_file_path)

                    if included_file_mtime > modified_after:
                        return True
                    elif self._has_modified_includes(included_file_path, modified_after, depth=depth - 1):
                        return True

        return False

    def compile(self, cu_file_path, ptx_file_name=None):
        if ptx_file_name is None:
            ptx_file_name = '{0}.ptx'.format(os.path.basename(cu_file_path))

        output_file_path = os.path.join(self.output_path, ptx_file_name)
        is_compiled = True

        if self._is_compile_required(cu_file_path, output_file_path):
            if os.path.exists(output_file_path):
                os.remove(output_file_path)

            logger.info("Compiling {0}".format(cu_file_path))
            bash_command = "nvcc " + cu_file_path
            bash_command += " -ptx"
            bash_command += " -arch=" + self.arch
            if self.use_fast_math:
                bash_command += " --use_fast_math"
            for include_path in self.include_paths:
                if os.path.exists(include_path):
                    bash_command += " -I=" + include_path
            bash_command += " -o=" + output_file_path
            logger.debug("Executing: {0}".format(bash_command))
            try:
                check_call(shlex.split(bash_command))
            except CalledProcessError as e:
                logger.error(e)

            if not os.path.exists(output_file_path):
                logger.error("Could not compile {0}".format(cu_file_path))
                raise RuntimeError("Could not compile {0}".format(cu_file_path))
        else:
            logger.debug("No compiling required for {0}".format(cu_file_path))
            is_compiled = False

        return output_file_path, is_compiled

    def clean(self):
        if os.path.exists(self.output_path):
            for dirpath, dirnames, filenames in os.walk(self.output_path):
                for filename in fnmatch.filter(filenames, '*.ptx'):
                    os.remove(os.path.join(dirpath, filename))
