"""
Sign each file given as an argument, using the credentials and
options specified in the notabot.cfg file.  If no arguments are
provided, sign the entire app specified in notabot.cfg.
"""
import sys
from .. import Notarizer
notarizer = Notarizer('notabot.cfg')
if len(sys.argv) == 1:
    notarizer.sign_app()
else:
    for pathname in sys.argv[1:]:
        notarizer.sign_item(pathname)
    
