import json
from typing import Dict, List
from enum import Enum
from wattpad_scraper.utils.parse_content import parse_content, raw_content, ChapterPart
from wattpad_scraper.utils.request import get
from wattpad_scraper.utils.log import Log, get_log
from wattpad_scraper.utils.save_books import create_epub, create_pdf, create_txt, create_webpage
from wattpad_scraper.utils.helper_functions import get_workers
from datetime import datetime
from bs4 import BeautifulSoup
import concurrent.futures as cf
import re
import os
import webbrowser



class Status(Enum):
    ONGOING = 1
    COMPLETED = 2
    CANCELLED = 3
    HOLD = 4



class Chapter:
    def __init__(self, url: str, title: str = None, content=None, chapter_number: int = 0) -> None: #type: ignore
        self.url = url
        self.title = title
        self._content = content
        self.number = chapter_number
        self._raw_content = None
        self.log = get_log("wattpad_log_chapter")

    # to json
    def to_json(self) -> Dict[str, str]:
        return json.dumps(self.__dict__, indent=4) #type: ignore

    
    @property
    def content(self) -> List[ChapterPart]:
        """
        Returns the content of the chapter. Will be parsed if not already parsed.
        """
        if self._content is None:
            self._content = parse_content(self.url, self.log)
        return self._content
    
    @property
    def raw_content(self) -> str:
        """
        Returns the raw content of the chapter. Will be parsed if not already parsed.
        """
        if self._raw_content is None:
            self._raw_content = raw_content(self.url, self.log)
        return self._raw_content
        

    def parse_content_again(self) -> List[ChapterPart]:
        """
        Parses the content of the chapter again.
        """
        self._content = parse_content(self.url, self.log)
        return self._content
    
    def parse_raw_content_again(self) -> str:
        """
        Parses the raw content of the chapter again.
        """
        self._raw_content = raw_content(self.url, self.log)
        return self._raw_content

    def __str__(self) -> str:
        return f"Chapter(url={self.url}, title={self.title})"

    def __repr__(self) -> str:
        return self.__str__()

    def __eq__(self, other) -> bool:
        return self.url == other.url

    def __dir__(self) -> List[str]:
        return ['url', 'title', 'content', 'number', 'parse_content_again', 'to_json']

    def __len__(self) -> int:
        total_len = 0
        for content in self.content:
            total_len += len(content)
        return total_len

    def __hash__(self):
        return hash(self.url) 

    def __lt__(self, other) -> bool:
        return self.number < other.number

    def __le__(self, other) -> bool:
        return self.number <= other.number

    def __gt__(self, other) -> bool:
        return self.number > other.number

    def __ge__(self, other) -> bool:
        return self.number >= other.number

    def __ne__(self, other) -> bool:
        return self.url != other.url



def get_chapters(url: str) -> List[Chapter]:
    """
    Args:
        url (string): book url

    Returns:
        List[Chapter]: returns a list of Chapter objects

        Chapter object has the following attributes:
            url (string): chapter url
            title (string): chapter title
            content (list): list of chapter content
    """
    response = get(url)
    soup = BeautifulSoup(response.content, "html.parser")
    main_url = "https://www.wattpad.com"

    toc = soup.find(class_='table-of-contents')
    lis = toc.find_all('li') # type: ignore
    chapters = []
    for n, li in enumerate(lis):
        a = li.find('a')
        url = a.get('href')
        if url.startswith('/'):
            url = main_url + url
        ch = Chapter(
            url=url, title=a.get_text().strip().replace('\n', ' '), chapter_number=n)
        chapters.append(ch)
        n += 1
    return chapters


class Book:
    """
    Book class
        Attributes:
            url: str
            title: str
            author: Author object
            img_url: str
            tags: list of str
            status: Status (ONGOING, COMPLETED, CANCELLED, HOLD)
            isMature: bool
            description: str
            published: str
            reads: int
            votes: int
            total_chapters: int
            chapters: list of Chapter objects

    """

    def __init__(self, url: str, title: str, img_url: str, total_chapters: int, description: str, author: "Author" = None,tags: List[str] = None, published: str = None, reads: int = None, votes: int = None,status: Status = Status.ONGOING, isMature: bool = False, chapters: List[Chapter] = None): # type: ignore
        self.url = url
        self.title = title
        self.author = author
        self._chapters = chapters
        self.img_url = img_url
        self.tags = tags
        self.status:Status = status
        self.isMature = isMature
        self.description = description
        self.published = published
        self.reads = reads
        self.votes = votes
        self.total_chapters = total_chapters
        self._chapters_with_content: List[Chapter] = []
        self.log = Log("wattpad_log", verbose=os.environ.get("WATTPAD_VERBOSE", "False") == "True")
        
        self._id = ""

    def is_completed(self) -> bool:
        return self.status == Status.COMPLETED

    def is_ongoing(self) -> bool:
        return self.status == Status.ONGOING
    
    def is_mature(self) -> bool:
        return self.isMature
    
    
    @property
    def id(self) -> str:
        if self._id != "":
            return self._id
        
        bid = self.url.split('/')[-1]
        if not bid.isdigit():
            bid = re.findall(r'\d+', bid)[0]
        self._id = bid
        return bid

    @property
    def chapters(self) -> List[Chapter]:
        if self._chapters is None:
            self._chapters = get_chapters(self.url)
        return self._chapters

    # @property
    # def chapters_with_content(self) -> List[Chapter]:
    #     threads = []
    #     for chapter in self.chapters:
    #         self.log.print(
    #             f"Getting content for chapter {chapter.number}", color="blue")
    #         t = threading.Thread(target=lambda: chapter.content)
    #         threads.append(t)
    #         t.start()
    #     for t in threads:
    #         t.join()
    #     return self.chapters

    @property
    def chapters_with_content(self) -> List[Chapter]:
        """ Get all chapters with content """
        
        # use threadpool executor and wait for all threads to finish
        with cf.ThreadPoolExecutor(max_workers=get_workers()) as executor: # type: ignore
            futures = [executor.submit(lambda: chapter.content) for chapter in self.chapters]
            cf.wait(futures)
        return self.chapters
    
    @property
    def chapters_with_raw_content(self) -> List[Chapter]:
        """ Get all chapters with raw content """
        # use threadpool executor and wait for all threads to finish
        with cf.ThreadPoolExecutor(max_workers=get_workers()) as executor: # type: ignore
            futures = [executor.submit(lambda: chapter.raw_content) for chapter in self.chapters]
            cf.wait(futures)
        return self.chapters
    
    def genarate_chapters(self):
        """ Returns a generator for the chapters """
        for chapter in self.chapters:
            chapter.content
            yield chapter

    def convert_to_epub(self, loc = None,lang='en', verbose: bool = True) -> None:
        # DEPRECATED
        """ 
        Converts the book to epub format (DEPRECATED) Use create_epub instead

        Args:
            loc (string): location to save the epub file default is current directory
            verbose (bool): if true prints the progress of the conversion default is true
        """
        create_epub(self, loc, lang=lang)
    
    
    def create_epub(self, loc = None, overwrite: bool = True, **kw) -> str:
        """ Creates an epub file of the book
            Args:
                loc (string): location to save the epub file default is current directory
                overwrite (bool): if true overwrites the file if it already exists default is true
                
            Keyword Args:
                lang (string or list): language of the book default is en.
                
            Returns:
                string: path to the epub file
        """
        
        return create_epub(self, loc, overwrite=overwrite, **kw)
    
    def create_pdf(self, loc = None, overwrite: bool = True) -> str:
        """ Creates a pdf file of the book
            Args:
                loc (string): location to save the pdf file default is current directory
                lang (string): language of the book default is english
                overwrite (bool): if true overwrites the file if it already exists default is true
            Returns:
                string: path to the pdf file
        """
        return create_pdf(self, loc, overwrite=overwrite)
    
    def create_txt(self, loc = None, overwrite: bool = True) -> str:
        """ Creates a txt file of the book
            Args:
                loc (string): location to save the txt file default is current directory
                overwrite (bool): if true overwrites the file if it already exists default is true
            Returns:
                string: path to the text file
        """
        return create_txt(self, loc,overwrite=overwrite)
    
    def create_webpage(self, loc = None, overwrite: bool = True) -> str:
        """ Creates a webpage of the book
            Args:
                loc (string): location to save the webpage file default is current directory
                overwrite (bool): if true overwrites the file if it already exists default is true

            Returns:
                string: path to the html file
        """
        return create_webpage(self, loc, overwrite=overwrite)
    
    def create_html(self, loc = None, overwrite: bool = True) -> str:
        """ Creates a html file of the book
            Args:
                loc (string): location to save the html file default is current directory
                overwrite (bool): if true overwrites the file if it already exists default is true
            Returns:
                string: path to the html file
        """
        return create_webpage(self, loc, overwrite=overwrite)
    
    def save(self, loc = None, overwrite: bool = True, **kw) -> str:
        """ Saves the book in the given location
            Args:
                loc (string): location to save the book default is current directory
                overwrite (bool): if true overwrites the file if it already exists default is true
            Returns:
                string: path to the book
        """
        supported_formats = ['epub', 'pdf', 'txt', 'html']
        if loc is None:
            return self.create_epub(overwrite=overwrite, **kw)
        else:
            if loc in supported_formats:
                for frm in supported_formats:
                    if loc == frm:
                        return getattr(self, f'create_{frm}')(overwrite=overwrite)

            if loc.endswith('.epub'):
                return self.create_epub(loc, overwrite=overwrite, **kw)
            elif loc.endswith('.pdf'):
                return self.create_pdf(loc, overwrite=overwrite)
            elif loc.endswith('.txt'):
                return self.create_txt(loc, overwrite=overwrite)
            elif loc.endswith('.html'):
                return self.create_webpage(loc, overwrite=overwrite)
            else:
                if os.path.isdir(loc):
                    return self.create_epub(loc, overwrite=overwrite, **kw)
                else:
                    raise ValueError(f"Invalid file format. Supported formats are {supported_formats}")

        
    
    def read_in_browser(self) -> None:
        """ Opens the book in the browser"""
        html_file = self.create_webpage()
        webbrowser.open(html_file)
    
            

    def to_json(self) -> str:
        # withouth chapters
        """ Returns a json string of the book"""
        return json.dumps(
            {'url': self.url, 'title': self.title, 'author': self.author.to_json(), 'img_url': self.img_url,
             'tags': self.tags, 'status': self.status.name, 'isMature': self.isMature, 'description': self.description,
             'published': self.published, 'reads': self.reads, 'votes': self.votes,
             'total_chapters': self.total_chapters}, indent=4)

    def __str__(self) -> str:
        return f"Book(title={self.title}, url={self.url}, status={self.status.name}, total_chapters={self.total_chapters})"

    def __repr__(self) -> str:
        return self.__str__()

    def __eq__(self, other) -> bool:
        return self.url == other.url
    
    def __hash__(self) -> int:
        return hash(self.url)

    # len
    def __len__(self) -> int:
        return self.total_chapters

    def __dir__(self) -> List[str]:
        return ['url', 'title', 'author', 'img_url', 'tags', 'status', 'isMature', 'description', 'published', 'reads',
                'votes', 'total_chapters', 'chapters', 'to_json']

    # from json
    @classmethod
    def from_json(cls, jsonstr: str) -> 'Book':
        json_str = json.loads(jsonstr) if isinstance(
            jsonstr, str) else jsonstr
        
        title = json_str['title']
        url = json_str['url']
        img_url = json_str['cover']
        description = json_str['description']
        author_name = json_str['user']['name']
        author_url = f"https://www.wattpad.com/user/{author_name}"
        author_avatar = json_str['user'].get('avatar', "")
        author_fullname = json_str['user'].get('fullName', "")
        
        author = Author(username=author_name, url=author_url, fullname=author_fullname, author_img_url=author_avatar)
        tags = json_str['tags']
        status = Status.COMPLETED if json_str['completed'] else Status.ONGOING
        isMature = json_str['mature']

        if 'lastPublishedPart' in json_str:
            published = json_str['lastPublishedPart']['createDate']
        else:
            published = json_str['firstPublishedPart']['createDate']
            
        # 2016-04-04T19:21:55Z
        published = published.replace('T', ' ')
        published = published.replace('Z', '')

        try:
            published = datetime.strptime(published, '%Y-%m-%d %H:%M:%S')
            published = published.strftime('%d/%m/%Y')
        except Exception as e:
            published = "N/A"
        
        reads = json_str['readCount']
        votes = json_str['voteCount']
        total_chapters = json_str['numParts']
        return cls(url=url, title=title, img_url=img_url, description=description, author=author, tags=tags,
                   status=status, isMature=isMature, published=published, reads=reads, votes=votes,
                   total_chapters=total_chapters)

class Author:
    def __init__(self, url: str, username: str,fullname:str="", author_img_url: str = "", books: List['Book'] = []) -> None:
        self.url = url
        self.author_img_url = author_img_url
        self.name = username
        self.fullname = fullname
        self._books = books if books is not None else []

    @property
    def cover(self) -> str:
        return self.author_img_url
    
    def to_json(self) -> str:
        return json.dumps({'url': self.url, 'author_img_url': self.author_img_url, 'name': self.name,'books': self.books if self.books != None else None}, indent=4)
    
    def __hash__(self) -> int:
        return hash(self.url)
    
    @property
    def books(self) -> List['Book']:
        """ Books in the author's profile
            Max 100 books for more books use book_list
        """
        
        if not self._books:
            return self.book_list
        else:
            return self._books
    
    @property
    def book_list(self,start=0,limit=100) -> List['Book']:
        """ Books in the author's profile 
        Args:
            start (int): the offset of the books to get
        Returns:
            List[Book]: list of books
        """
        
        if not self._books:
            res = get(f"https://www.wattpad.com/v4/users/{self.name}/stories/published?offset={start}&limit={limit}")
            data = res.json()
            
            stories = data['stories']
            books = []
            for story in stories:
                book = Book.from_json(story)
                books.append(book)
            self._books = books
        
            return books
        else:
            return self._books   

    def __str__(self) -> str:
        return f'Author(name={self.name}, url={self.url})'

    def __repr__(self) -> str:
        return self.__str__()

    def __eq__(self, __o: object) -> bool:
        if isinstance(__o, Author):
            return self.url == __o.url
        return False

    def __len__(self) -> int:
        return len(self.books)



