import os
from distutils.command.build import build

from django.core import management
from setuptools import setup, find_packages


try:
    with open(os.path.join(os.path.dirname(__file__), 'README.rst'), encoding='utf-8') as f:
        long_description = f.read()
except Exception:
    long_description = ''


class CustomBuild(build):
    def run(self):
        management.call_command('compilemessages', verbosity=1)
        build.run(self)


cmdclass = {
    'build': CustomBuild
}


setup(
    name='pretix-qpaypro',
    version='1.0.11',
    description='Integration for the QPayPro payment provider.',
    long_description=long_description,
    long_description_content_type='text/x-rst',
    url='https://github.com/aruanoguate/pretix-qpaypro',
    author='Alvaro Enrique Ruano',
    author_email='alvaro.ruano90@outlook.com',
    license='Apache Software License',

    install_requires=[],
    packages=find_packages(exclude=['tests', 'tests.*']),
    include_package_data=True,
    cmdclass=cmdclass,
    entry_points="""
[pretix.plugin]
pretix_qpaypro=pretix_qpaypro:PretixPluginMeta
""",
)
