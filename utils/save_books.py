import json
from typing import Dict
from ebooklib import epub
from wattpad_scraper.utils.request import get
from wattpad_scraper.utils.log import get_log
from wattpad_scraper.utils.helper_functions import get_asset, get_workers
import os
from fpdf import FPDF
from uuid import uuid4
from bs4 import BeautifulSoup
import concurrent.futures as cf

PLACEHOLDER_IMG = get_asset("img", "placeholder.jpg")


class TempImage:
    def __init__(self):
        self.paths = []
        self.save_path = os.path.join(os.getcwd(), 'temp_imgs')
        if not os.path.exists(self.save_path):
            os.mkdir(self.save_path)
        self.path_map = {}

    def get_path(self, url):
        res = get(url)
        name = str(uuid4()) + ".jpg"
        path = os.path.join(self.save_path, name)
        with open(path, "wb") as f:
            f.write(res.content)
        self.paths.append(path)
        self.path_map[url] = path
        return path

    def get_paths(self, urls: list) -> Dict[str, str]:
        with cf.ThreadPoolExecutor() as executor:
            paths = executor.map(self.get_path, urls)
        return self.path_map

    def cleanup(self):
        for path in self.paths:
            os.remove(path)
        self.paths = []
        self.path_map = {}


def download_image(img_file_name, img_url, ebook, log):
    res = get(img_url)
    if res.status_code == 200:
        ebook.add_item(epub.EpubItem(file_name=img_file_name,
                       media_type='image/jpeg', content=res.content))
    else:
        log.warning(
            f"Could not add image {img_file_name} :{img_url}[{res.status_code}]")
        with open(PLACEHOLDER_IMG, 'rb') as f:
            ebook.add_item(epub.EpubItem(file_name=img_file_name,
                           media_type='image/jpeg', content=f.read()))


def get_location(loc, title, ext, overwrite=False):
    filename = title.replace(" ", "_") + "." + ext
    if loc is None:
        loc = os.path.join(os.getcwd(), filename)
    else:
        if os.path.isdir(loc):
            loc = os.path.join(loc, filename)

    if os.path.exists(loc) and not overwrite:
        raise FileExistsError(f"File {loc} already exists")

    return loc


def create_epub(book, loc=None, overwrite: bool = True, **kw) -> str:
    log = get_log("wattpad_save_books:create_epub")

    if "lang" in kw:
        lang = kw["lang"]
    else:
        lang = "en"

    ebook = epub.EpubBook()
    ebook.set_identifier(book.id)
    ebook.set_title(book.title)
    ebook.set_language(lang)
    ebook.add_author(book.author.name)

    log.debug(f"Creating epub for {book.title}")
    # add cover
    res = get(book.img_url)
    if res.status_code == 200:
        log.debug(f"Adding cover for {book.title}")
        ebook.set_cover(file_name='cover.jpg',
                        content=res.content, create_page=True)
    else:
        log.warning(f"Could not add cover for {book.title}")
        log.warning(f"Status code: {res.status_code}")
        ebook.set_cover(file_name='cover.jpg',
                        content=open(PLACEHOLDER_IMG, 'rb').read(), create_page=True)

    # about
    log.debug(f"Adding about for {book.title}")
    about = epub.EpubHtml(title='About', file_name='about.xhtml', lang=lang)
    about.content = f"""<h2><a href="{book.url}">{book.title}</a></h2> by <h3><a href="{book.author.url}">{book.author.name}</a></h3><p>{book.description}</p>"""
    ebook.add_item(about)

    # chapters
    log.debug(f"Adding chapters for {book.title}")
    log.debug(f"Number of chapters: {book.total_chapters}")

    book_chapters = book.chapters_with_raw_content
    chapters = []
    for chapter in book_chapters:
        chapter_obj = epub.EpubHtml(
            title=chapter.title, file_name=f"{chapter.number}.xhtml", lang=lang)
        content = f"<h1>{chapter.title}</h1>"
        # chapter.content is a html string
        chapter_content = "<body>" + chapter.raw_content + "</body>"
        chapter_soup = BeautifulSoup(chapter_content, 'html.parser')
        # get all tags
        tags = chapter_soup.body.find_all(recursive=False)  # type: ignore
        img_no = 0
        imgs = []  # file name
        # p {'data-p-id': '5fb324a57c83f76bafb22dd3604ec42f', 'style': 'text-align: center'}
        # p {'data-media-type': 'image', 'data-image-layout': 'one-horizontal', 'data-p-id': '3a25bb234ecd47b834f66dc13ced0c10', 'style': 'text-align: center'}
        for tag in tags:
            attrs = tag.attrs
            if attrs.get('data-media-type', 'None') == 'image':
                img = tag.find('img')
                img_url = img['src']
                file_name = f"{chapter.number}_{img_no}.jpg"
                img_no += 1
                imgs.append((file_name, img_url))
                tag.img['src'] = file_name

            content += str(tag)

        log.debug(f"Found {len(imgs)} images for chapter {chapter.number}")
        with cf.ThreadPoolExecutor(max_workers=get_workers()) as executor:
            for img_file_name, img_url in imgs:
                executor.submit(download_image, img_file_name,
                                img_url, ebook, log)

        log.debug(
            f"Adding chapter {chapter.number}.{chapter.title}[{len(content)}]")

        chapter_obj.content = content
        ebook.add_item(chapter_obj)
        chapters.append(chapter_obj)


    ebook.toc = tuple(chapters)  # type: ignore
    ebook.add_item(epub.EpubNcx())
    ebook.add_item(epub.EpubNav())

    style = '''
    @namespace epub "http://www.idpf.org/2007/ops";
    body {
        font-family: Cambria, Liberation Serif, Bitstream Vera Serif, Georgia, Times, Times New Roman, serif;
    }
    h2 {
        text-align: left;
        text-transform: uppercase;
        font-weight: 200;     
    }
    ol {
            list-style-type: none;
    }
    ol > li:first-child {
            margin-top: 0.3em;
    }
    nav[epub|type~='toc'] > ol > li > ol  {
        list-style-type:square;
    }
    nav[epub|type~='toc'] > ol > li > ol > li {
            margin-top: 0.3em;
    }'''

    nav_css = epub.EpubItem(
        uid="style_nav", file_name="style/nav.css", media_type="text/css", content=style)  # type: ignore
    ebook.add_item(nav_css)

    ebook.spine = ['cover', about, 'nav'] + chapters

    location = get_location(loc, book.title, "epub", overwrite)
    epub.write_epub(location, ebook, {})
    log.success(f"Created epub for {book.title} saved at {location}")
    return location


class BookPDF(FPDF):
    # methods: set cover, add item: (text, image), add toc
    def __init__(self, timg, img_path_map, *args, **kw):
        super().__init__(*args, **kw)

        self.bold_font = get_asset("fonts", "DejaVuSansCondensed-Bold.ttf")
        self.regular_font = get_asset("fonts", "DejaVuSansCondensed.ttf")

        self.add_font(self.bold_font, fname=self.bold_font)
        self.add_font(self.regular_font, fname=self.regular_font)

        self.timg: TempImage = timg
        self.img_path_map = img_path_map

    def set_cover(self, book):
        self.add_page()
        self.set_font(self.bold_font, size=20)
        self.cell(200, 10, txt=f"{book.title}", ln=1, align="C")
        self.set_font(self.regular_font, size=15)
        self.cell(200, 10, txt=f"By {book.author.name}", ln=1, align="C")
        path = self.timg.get_path(book.img_url)
        self.image(path, 10, 30, 190)
        self.ln(50)

    def add_item(self, title, contents):
        # contents: list of (text or image_url) both are str
        # for checking if text or image: content.is_text
        # return page number

        self.add_page()
        self.set_font(self.bold_font, size=20)
        self.cell(200, 10, txt=title, ln=1, align="C")
        self.ln(10)

        self.set_font(self.regular_font, size=15)

        self.auto_page_break = True
        for content in contents:
            if content.is_text:
                self.multi_cell(0, 10, txt=content, align="L", ln=1)
            else:
                path = self.img_path_map[content]
                self.image(name=path, x=-0.5, w=self.w + 1)
            self.ln(10)

    def add_toc(self, toc):
        self.add_page()
        self.set_font(self.bold_font, size=20)
        self.cell(200, 10, txt="Table of Contents", ln=1, align="C")
        self.ln(10)
        self.set_font(self.regular_font, size=15)
        for title in toc:
            self.cell(0, 10, txt=title, ln=1, align="L")
            self.ln(2)

    def save(self, loc=None, overwrite=True):
        location = get_location(loc, self.title, "pdf", overwrite)
        self.output(location)
        self.timg.cleanup()
        return location


def create_pdf(book, loc=None, overwrite=True) -> str:
    log = get_log('wattpad_save_books: create_pdf')
    timg = TempImage()

    log.print(f"Creating pdf for {book.title}", color="green")

    img_urls = []
    book_chapters = book.chapters_with_content
    for chapter in book_chapters:
        for content in chapter.content:
            if content.is_img:
                img_urls.append(content)
    path_map = timg.get_paths(img_urls)

    pdf = BookPDF(timg=timg, img_path_map=path_map,
                  orientation="P", unit="mm", format="A4")
    pdf.title = book.title
    pdf.set_cover(book)
    pdf.add_toc([chapter.title for chapter in book_chapters])

    for chapter in book_chapters:
        log.print(
            f"Adding chapter {chapter.number} {chapter.title}", color="green")
        pdf.add_item(chapter.title, chapter.content)

    location = pdf.save(loc, overwrite)
    log.success(f"Created pdf for {book.title} saved at {location}")
    return location


def create_txt(book, loc=None, overwrite=True) -> str:
    log = get_log('wattpad_save_books: create_txt')

    log.print(f"Creating txt for {book.title}", color="green")
    # about page
    log.print("Adding about page", color="green")
    content = f"{book.title} by {book.author.name}\n {book.description}\n\n"

    log.print("Getting chapters", color="green")
    log.print(f"Chapters: {book.total_chapters}", color="green")
    book_chapters = book.chapters_with_content
    for chapter in book_chapters:
        log.print(
            f"Adding chapter {chapter.number} {chapter.title}", color="green")
        content += f"\n\n{chapter.title}\n\n"
        texts = chapter.content
        # check if image
        for text in texts:
            if text.is_img:
                content += f"[IMAGE: {text}]\n"
            else:
                content += f"{text}\n"

    location = get_location(loc, book.title, "txt", overwrite=overwrite)
    with open(location, "w", encoding="utf-8") as f:
        f.write(content)
    log.success(f"Text created at {location}")
    return location


def create_webpage(book, loc=None, overwrite=True) -> str:
    log = get_log('wattpad_save_books: create_webpage')
    html = "<h1> Still in development. Showing Text</h1>"
    
    location = get_location(loc, book.title, "html", overwrite)
    txt_location = get_location(loc, book.title, "txt", overwrite)
    book.create_txt(txt_location)
    with open(txt_location, "r", encoding="utf-8") as f:
        html += f"<pre>{f.read()}</pre>"
    with open(location, "w", encoding="utf-8") as f:
        f.write(html)
    log.success(f"Webpage created at {location}")
    return location
    
