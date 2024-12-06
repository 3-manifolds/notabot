"""
This file defines the Notarizer class, which serves as an interface
to the various xcrun and codesign commands which are needed to sign
and notarize a macOS app.  Notarization requires extending this class
by defining a build_dmg method which builds the disk image to be sent
to Apple's notarization service.

The Notarizer is initialized with the path to a config file which
includes the credentials and paths needed for signing and notarizing.

The file should have the following format, in which the paths section
is optional, but required for notarization.

[developer]
username = <your app store id or email>
password = <your app-specific password>
identity = <the signing identity you used to sign your app>

[entitlements]
plist_file = <path to entitlement plist file>

[entitlements]
plist_file = <path to entitlement plist file>

[paths]
bundle_path = <path to a framework or application bundle>
dmg_path = <path to the disk image that your build_dmg method will create>
"""
__version__ = '1.3.3'

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

    def _get_path(self):
        try:
            return self.config['paths']['bundle_path']
        except:
            raise ValueError('Specify a path to an app or framework.')

    def visit_files(self, bundle_path=None):
        """Finds all files and directories which need to be signed.

        Also, checks and reports broken symlinks and symlinks which point out of
        the bundle.
        """
        if bundle_path is None:
            bundle_path = self._get_path()
        _, ext = os.path.splitext(bundle_path)
        if ext not in ('.app', '.framework'):
            raise ValueError('An app or framework was expected.')
        abs_path = os.path.abspath(bundle_path)
        binaries = []
        frameworks = []
        apps = []
        # Subdirectories with a dot in the name are expected to contain code.
        code_dirnames = []
        for dirpath, dirnames, filenames in os.walk(bundle_path):
            for filename in filenames:
                pathname = os.path.join(dirpath, filename)
                if os.path.islink(pathname):
                    if os.path.exists(pathname):
                        if not os.path.abspath(pathname).startswith(abs_path):
                            raise ValueError(
                                'Symlink %s points outside the bundle.' % pathname)
                    else:
                        raise ValueError(
                            'Symlink %s is broken.' % pathname)
                elif self.is_mach_binary(pathname):
                        binaries.append(pathname)
            for dirname in dirnames:
                pathname = os.path.join(dirpath, dirname)
                base, ext = os.path.splitext(pathname)
                if ext == '.framework':
                    frameworks.append(pathname)
                elif ext == '.app':
                    apps.append(pathname)
                elif ext and pathname.find('Versions') < 0:
                    # Directories with extensions are assumed to contain code.
                    code_dirnames.append(pathname)
        if code_dirnames:
            print('Code directories:', code_dirnames)
        return binaries, frameworks, apps

    def sign_item(self, item_path):
        args = ['codesign'] + self.codesign_args + [item_path]
        subprocess.call(args)
            
    def sign_bundle(self, bundle_path=None):
        if bundle_path is None:
            bundle_path = self._get_path()
        # This removes signatures from scripts.
        subprocess.call(['xattr', '-rc', bundle_path])
        binaries, frameworks, apps = self.visit_files(bundle_path)
        for binary in binaries:
            self.sign_item(binary)
        for framework in frameworks:
            self.sign_item(framework)
        for app in apps:
            self.sign_item(app)
        self.sign_item(bundle_path)

    def build_dmg(self):
        #Subclasses must override this method in order for the run method to work.
        raise RuntimeError('The Notarizer.build_dmg method must be overridden.')

    def notarize(self):
        info = {}
        config = self.config
        dmg_path = config['app']['dmg_path']
        if not os.path.exists(dmg_path):
            raise ValueError("No disk image was specified.");
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
        # Requires that the paths section exist.
        config = self.config
        print('Stapling the notarization ticket to %s\n'%config['paths']['bundle_path'])
        args = ['xcrun', 'stapler', 'staple', config['paths']['bundle_path']]
        result = subprocess.run(args, text=True, capture_output=True)
        self.check(result, 'Stapling failed')

    def sign_dmg(self):
        # Requires that the paths section exist.
        config = self.config
        args = ['codesign', '-v', '-s', config['developer']['identity'],
                config['paths']['dmg_path']]
        result = subprocess.run(args, text=True, capture_output=True)
        self.check(result, 'Signing failed')

    def check(self, result, message):
        if result.returncode:
            print(message + ':')
            print(result.stderr)
            sys.exit(1)
        
    def staple_dmg(self):
        # Requires that the paths section exist.
        config = self.config
        print('Stapling the notarization ticket to %s\n'%config['app']['dmg_path'])
        args = ['xcrun', 'stapler', 'staple', config['paths']['dmg_path']]
        result = subprocess.run(args, text=True, capture_output=True)
        self.check(result, 'Stapling failed')

    def run(self):
        """Do the full notarization dance."""
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

