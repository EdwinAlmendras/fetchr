import re
from bs4 import Tag


def solve_css_position_captcha(captcha_element: Tag) -> str:
    data = []
    
    for span in captcha_element.find_all('span'):
        number = span.get_text().strip()
        style = span.get('style', '')
        match = re.search(r'padding-left:(\d+)px', style)
        
        if match and number.isdigit():
            data.append((int(match.group(1)), number))
    
    data.sort()
    return ''.join([num for pos, num in data])
