"""
Sign each file given as an argument, using the credentials and
options specified in the notabot.cfg file.  If no arguments are
provided, sign the entire app specified in notabot.cfg.
"""
import sys
import os
from .. import Notarizer

notarizer = Notarizer('notabot.cfg')
if len(sys.argv) == 1:
    notarizer.sign_bundle()
else:
    for arg in sys.argv[1:]:
        _, ext = os.path.splitext(arg)
        if ext in ('.app', '.framework'):
            print('signing bundle', arg)
            notarizer.sign_bundle(arg)
        else:
            notarizer.sign_item(arg)
        
>>>>>>> af316384a8a63f4c9dd3ebf8b5308dde8348eb0c
