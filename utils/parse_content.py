from typing import List
from wattpad_scraper.utils.request import get
from wattpad_scraper.utils.log import Log
from bs4 import BeautifulSoup
import os

STORY_TEXT_API = "https://www.wattpad.com/apiv2/storytext?id={}"

class ChapterPart(str):
    def __new__(cls, value: str, is_img: bool = False) -> 'ChapterPart':
        return super().__new__(cls, value)

    def __init__(self, value: str, is_img: bool = False) -> None:
        super().__init__()
        self.type = 'img' if is_img else 'text'
        self._is_img = is_img
        self._value = value
    
    def __str__(self) -> str:
        return self._value
    
    @property
    def value(self) -> str:
        return self._value
    
    # setter
    @value.setter
    def value(self, value: str) -> None:
        self._value = value
    

    @property
    def is_img(self) -> bool:
        return self._is_img

    @property
    def is_text(self) -> bool:
        return not self._is_img
    

# def chapter_soups(url : str) -> BeautifulSoup:
#     page = 1
#     soups = []
#     while 1:
#         res = get(url + '/page/' + str(page))
#         soup = BeautifulSoup(res.content, "html.parser")
#         next_part = soup.find("div",{"class":["next-up","next-part","orange"]})
#         next_part = "next-up next-part orange hidden" in str(next_part)
#         soups.append(soup)
#         page += 1
#         if not next_part:
#             break
#     return soups
    
    
# def parse_content(url : str) -> List[str]:
#     """parse wattpad chapters

#     Args:
#         url (string): chapter url

#     Returns:
#         list: returns a list of content ether a text or a img url
#     """
#     log = Log(name="wattpad_log",)
#     log.debug("Parsing {}".format(url))
#     soups = chapter_soups(url)
#     contents = []
#     log.info("Got content in {} pages".format(len(soups)))

#     for soup in soups:
#         ptags = soup.select('p[data-p-id]')
#         for p in ptags:
#             # check if if p tag have img tag
#             if p.find('img') is not None:
#                 # if p tag have img tag, get img tag src
#                 img_url = p.find('img').get('src')
#                 if img_url.startswith('/'):
#                     img_url = 'https://www.wattpad.com' + img_url
#                 contents.append(img_url)
#             else:
#                 # if p tag don't have img tag, get text
#                 contents.append(p.get_text())
#     log.debug("This chapter has {} contents".format(len(contents)))
#     return contents


def raw_content(url : str, log) -> str:
    chapter_name = url.split('/')[-1]
    chapter_id = chapter_name.split('-')[0]

    api_url = STORY_TEXT_API.format(chapter_id)
    res = get(api_url)
    
    if res.status_code == 200:
        return res.content.decode('utf-8')
    
    log.error(f"Failed to get raw content for {url}")
    return ''


def parse_content(url: str, log) -> List[ChapterPart]:
    raw = raw_content(url, log)
    content = "<body>" + raw + "</body>"
    soup = BeautifulSoup(content, "html.parser")
    
    tags = soup.body.find_all(recursive=False) # type: ignore
    contents = []
    for tag in tags:
        attrs = tag.attrs
        if attrs.get('data-media-type', 'None') == 'image':
            # contents.append(tag.img.attrs['src'])
            contents.append(ChapterPart(tag.img.attrs['src'], is_img=True))
        else:
            # contents.append(tag.get_text())
            contents.append(ChapterPart(tag.get_text(), is_img=False))
    return contents



    
    
    
    
    
    