Notabot
=======

This python package provides one class, Notarizer, which is intended as a base
class for a python object which automatically notarizes a signed macOS application
bundle.  The subclass which does the actual notarization needs to provide a
method build_dmg which builds the disk image that will be used to distribute
the app.

Apple's notarization process involves a complex dance which is performed by
this object.  First the signed app is packaged in a disk image and sent to
Apple for notarization.  Then the notarization ticket is stapled to the app
and the app is repackaged in a new disk image which is signed and sent to Apple
for a second notarization.  Finally the notarization ticket can be stapled
to the disk image itself.

The credentials and parameters which are needed for the various notarization
steps are provided in a config file which should be in the current
directory and should have the following structure:

.. code-block::

  [developer]
  username = <your app store id or email>
  password = <your app-specific password>
  identity = <the signing identity you used to sign your app>

  [entitlements]
  plist_file = <path to entitlement plist file>

  [app]
  app_path = <path to the application bundle>
  dmg_path = <path to the disk image that your build_dmg method will create>

This package is available from pypi:

.. code-block::

  pip install notabot
