"""Cython build configuration for math kernels."""
from pathlib import Path

import numpy
from Cython.Build import cythonize
from setuptools import Extension, setup

BASE_DIR = Path(__file__).resolve().parent
INCLUDE_DIRS = [numpy.get_include()]

extensions = [
    Extension("backend.cython_math.rsi", [str(BASE_DIR / "rsi.pyx")], include_dirs=INCLUDE_DIRS),
    Extension("backend.cython_math.sma", [str(BASE_DIR / "sma.pyx")], include_dirs=INCLUDE_DIRS),
    Extension("backend.cython_math.vwap", [str(BASE_DIR / "vwap.pyx")], include_dirs=INCLUDE_DIRS),
]

setup(
    ext_modules=cythonize(
        extensions,
        compiler_directives={"language_level": "3"},
    ),
)
