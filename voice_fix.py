import pyautogui 
import sys 
with open('app.py', 'r', encoding='utf-8') as f: content = f.read() 
if 'import pyautogui' not in content: content = 'import pyautogui\\n' + content 
with open('app.py', 'w', encoding='utf-8') as f: f.write(content) 
