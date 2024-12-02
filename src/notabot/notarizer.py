import os
import sys
import subprocess
import json
import time
import configparser

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
bundle_id = <an (arbitrary) bundle identifier that you provide for the request>

"""

class Notarizer:
    """
    Base class for app notarizers.
    """
    def __init__(self, config_file):
        self.config = configparser.ConfigParser()
        self.config.read(config_file)
        self.start = time.time()
        
    def build_dmg(self):
        #Subclasses must override this method.
        raise RuntimeError('The Notarizer.build_dmg method must be overridden.')

    def upload_dmg(self):
        config = self.config
        dmg_path = config['app']['dmg_path']
        if not os.path.exists(dmg_path):
            print("No disk image");
        args = ['xcrun', 'notarytool', 'submit',
                '--apple-id', config['developer']['username'],
                '--password', config['developer']['password'],
                '--team-id', config['developer']['identity'],
                '--output-format', 'json',
                '--wait',
                dmg_path]
        print("Notarizing %s" % dmg_path)
        result = subprocess.run(args, text=True, capture_output=True)
        info = json.loads(result.stdout)
        print('Notarization uuid:', info['id'])
        print('Notarization status:', info['status'])
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
        print('Signing the disk image')
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
        self.build_dmg()
        self.upload_dmg()
        self.staple_app()
        print('Repackaging the stapled app ...')
        self.build_dmg()
        self.sign_dmg()
        self.upload_dmg()
        self.staple_dmg()
