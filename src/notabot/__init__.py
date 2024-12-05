"""
This file defines the Notarizer class, which is a base class that needs to be
extended by defining the build_dmg method in a subclass.

The Notarizer is initialized with the name of a config file in the current
directory. The file should have the following format:

[developer]
username = <your app store id or email>
password = <your app-specific password>
identity = <the signing identity you used to sign your app>

[app]
app_name = <name of the app>
app_path = <path to the application bundle>
dmg_path = <path to the disk image that your build_dmg method will create>

[entitlements]
plist_file = <path to entitlement plist file>
"""
__version__ = '1.3.1'

import os
import sys
import subprocess
import json
import time
import configparser

if sys.byteorder == 'little':
    fat_magic = b'\xca\xfe\xba\xbe'
    mach_magic64 = b'\xfe\xed\xfa\xcf'
else:
    fat_magic = b'\xbe\xba\xfe\xca'
    mach_magic64 = b'\xcf\xfa\xed\xfe'

class Notarizer:
    """
    Base class for app notarizers.
    """

    def __init__(self, config_file):
        self.config = configparser.ConfigParser()
        self.config.read(config_file)
        self.info = {}
        self.start = time.time()
        self.codesign_args = [
            '-s', self.config['developer']['identity'],
            '-v',
            '--entitlements', self.config['entitlements']['plist_file'],
            '--timestamp',
            '--options', 'runtime',
            '--force'] 
        
    def is_mach_binary(self, pathname):
        with open(pathname, 'rb') as file_obj:
            magic = file_obj.read(4)
            if magic == fat_magic or magic == mach_magic64:
                return True
        return False

    def visit_files(self):
        app_bundle = self.config['app']['app_path']
        abs_app_path = os.path.abspath(app_bundle)
        self.binaries = binaries = []
        self.frameworks = frameworks = []
        bad_dirnames = []
        for dirpath, dirnames, filenames in os.walk(app_bundle):
            for filename in filenames:
                pathname = os.path.join(dirpath, filename)
                if os.path.islink(pathname):
                    if os.path.exists(pathname):
                        if not os.path.abspath(pathname).startswith(abs_app_path):
                            raise ValueError(
                                'Symlink %s points outside the app.' % pathname)
                    else:
                        raise ValueError(
                            'Symlink %s is broken.' % pathname)
                elif self.is_mach_binary(pathname):
                        binaries.append(pathname)
                else:
                    print('ignoring', pathname)
            for dirname in dirnames:
                pathname = os.path.join(dirpath, dirname)
                base, ext = os.path.splitext(pathname)
                if ext == '.framework':
                    frameworks.append(pathname)
                elif ext and pathname.find('Versions') < 0:
                    # Directories with extensions are assumed to contain code.
                    bad_dirnames.append(pathname)
        if bad_dirnames:
            print('Bad directories:', bad_dirnames)

    def sign_item(self, pathname):
        args = ['codesign'] + self.codesign_args + [pathname]
        subprocess.call(args)
            
    def sign_app(self):
        app_path = self.config['app']['app_path']
        subprocess.call(['xattr', '-rc', app_path])
        self.visit_files()
        for binary in self.binaries:
            self.sign_item(binary)
        for framework in self.frameworks:
            self.sign_item(framework)
        self.sign_item(app_path)

    def build_dmg(self):
        #Subclasses must override this method in order for the run method to work.
        raise RuntimeError('The Notarizer.build_dmg method must be overridden.')

    def notarize(self):
        info = {}
        config = self.config
        dmg_path = config['app']['dmg_path']
        if not os.path.exists(dmg_path):
            print("No disk image");
        args = ['xcrun', 'notarytool', 'submit', dmg_path,
                '--wait',
                '--apple-id', config['developer']['username'],
                '--team-id', config['developer']['identity'],
                '--password', config['developer']['password']]
        result = subprocess.run(args, text=True, capture_output=True)
        for line in result.stdout.split('\n'):
            line = line.strip()
            if line.find(':') >= 0:
                key, value = line.split(':', maxsplit=1)
                info[key] = value.strip()
        print('Notarization uuid:', info.get('id', 'None'))
        print('Notarization status:', info.get('status', 'None'))
        if info['status'] != 'Accepted':
            log = self.get_log(info['id'])
            if 'issues' in log:
                for info in log['issues']:
                    if info['severity'] == 'error':
                        print(info['path'])
                        print('   ', info['message'])
                sys.exit(-1)

    def get_log(self, UUID):
        config = self.config
        args = ['xcrun', 'notarytool', 'log',
                '--apple-id', config['developer']['username'],
                '--password', config['developer']['password'],
                '--team-id', config['developer']['identity'],
                UUID]
        result = subprocess.run(args, text=True, capture_output=True)
        return json.loads(result.stdout)

    def staple_app(self):
        config = self.config
        print('Stapling the notarization ticket to %s\n'%config['app']['app_path'])
        args = ['xcrun', 'stapler', 'staple', config['app']['app_path']]
        result = subprocess.run(args, text=True, capture_output=True)
        self.check(result, 'Stapling failed')

    def sign_dmg(self):
        config = self.config
        args = ['codesign', '-v', '-s', config['developer']['identity'],
                config['app']['dmg_path']]
        result = subprocess.run(args, text=True, capture_output=True)
        self.check(result, 'Signing failed')

    def staple_dmg(self):
        config = self.config
        print('Stapling the notarization ticket to %s\n'%config['app']['dmg_path'])
        args = ['xcrun', 'stapler', 'staple', config['app']['dmg_path']]
        result = subprocess.run(args, text=True, capture_output=True)
        self.check(result, 'Stapling failed')

    def check(self, result, message):
        if result.returncode:
            print(message + ':')
            print(result.stderr)
            sys.exit(1)
        
    def run(self):
        self.sign_app()
        self.build_dmg()
        print('Notarizing app ...')
        self.notarize()
        self.staple_app()
        self.build_dmg()
        self.sign_dmg()
        print('Notarizing disk image ...')
        self.notarize()
        self.staple_dmg()

