import base64 
import sys 
with open(sys.argv[1], 'wb') as f: f.write(base64.b64decode(sys.argv[2])) 
