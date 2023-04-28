
import atexit
import os
from typing import List, Union
from wattpad_scraper.utils.log import Log
from wattpad_scraper.utils.request import access_for_authenticated_user, session, headers, User
from wattpad_scraper.utils.helper_functions import get_workers
import re
import json
from bs4 import BeautifulSoup
from wattpad_scraper.models import Book, Status, Author
import concurrent.futures as cf


def error(error_msg):
    raise ValueError(error_msg)


READING_LIST_API = "https://www.wattpad.com/api/v3/lists/"
# {
#   "id": 348109422,
#   "name": "mine",
#   "user": {
#     "name": "haIfblood",
#     "avatar": "https://img.wattpad.com/useravatar/haIfblood.128.577281.jpg",
#     "fullname": "heidi elle",
#     "backgroundColour": "#4D0958",
#     "following": false
#   },
#   "numStories": 2,
#   "sample_covers": [
#     "https://img.wattpad.com/cover/48217861-256-k175667.jpg",
#     "https://img.wattpad.com/cover/60783168-256-k175683.jpg"
#   ],
#   "cover": "https://img.wattpad.com/ccover/348109422-300-377473.png?v=2"
# }


class ReadingList:
    """Reading List
    Args:
        id (int)
        name (str)
        author (Author)
        numOfStories (int)
        books (List[Book])
        cover_url (str)
    """  

    def __init__(self, id=None, name=None, author=None, numOfStories=0, books=None, cover_url=None):
        self.id = id
        self.name = name
        self.author:Author = author # type: ignore
        self.numOfStories = numOfStories
        self._books = books
        self.cover_url = cover_url
        self.request = ReadingListRequest(verbose=os.environ.get("WATTPAD_VERBOSE", "False") == "True")
        
    def __hash__(self) -> int:
        return hash(self.id)
            
        
    @property
    def books(self) -> List[Book]:
        if self._books is None or len(self._books) == 0:
            self._books = self.request.get_books(self.id, self.numOfStories)
        return self._books
    
    def book_list(self,start=0,limit=None) -> List[Book]:
        """ Get book list from reading list
        Args:
            start (int, optional): start index. Defaults to 0.
            limit (int, optional): limit of books. Defaults to number of books.
        Returns:
            List[Book]: list of books
        """
        if limit is None:
            limit = self.numOfStories
        
        self._books = self.request.get_books(self.id, limit, start)
        return self._books
        
    
    @classmethod
    def from_html(cls, html, id):
        # #reading-list main
        soup = BeautifulSoup(html, 'html.parser')

        # select
        rd = soup.find(id="reading-list")
        main = rd.find("main")  # type: ignore

        lis: [BeautifulSoup] = main.find_all(class_="clearfix")  # type: ignore
        books = []

        for li in lis:
            # img, a[1]
            img = li.find("img")
            img_url = img['src']
            if img_url[0] == "/":
                img_url = "https://www.wattpad.com" + img_url

            a = li.find_all("a")[1]
            url = a['href']
            if url[0] == "/":
                url = "https://www.wattpad.com" + url
            title = a.text.strip()

            # p
            description = li.find("p").text.strip()

            meta = li.find("div", class_="meta")

            reads = meta.find("small", class_="reads")
            reads = reads.text.strip()

            # read M = 1,000,000 , K = 1,000
            if "M" in reads:
                reads = reads.replace("M", "")
                reads = float(reads) * 1000000
            elif "K" in reads:
                reads = reads.replace("K", "")
                reads = float(reads) * 1000

            reads = int(reads)

            votes = meta.find("small", class_="votes")
            votes = votes.text.strip()

            if "M" in votes:
                votes = votes.replace("M", "")
                votes = float(votes) * 1000000

            elif "K" in votes:
                votes = votes.replace("K", "")
                votes = float(votes) * 1000

            votes = int(votes)

            # numParts
            total_chapters = meta.find("small", class_="numParts")
            total_chapters = total_chapters.text.strip()

            # int
            total_chapters = int(total_chapters) if total_chapters else 0

            # story-status
            status = meta.find("span", class_="story-status")
            st = Status.ONGOING
            isMature = False
            if status:
                # spans
                spans = status.find_all("span")

                texts = [span.text.strip() for span in spans]

                if "Completed" in texts:
                    st = Status.COMPLETED
                if "Mature" in texts:
                    isMature = True

            # book
            book = Book(url=url, title=title, img_url=img_url, total_chapters=total_chapters,
                        description=description, reads=reads, votes=votes, status=st, isMature=isMature)
            books.append(book)

        # reading-list-info

        # .reading-list-sidebar div.follow a
        sidebar = soup.select_one(".reading-list-sidebar")
        name = sidebar.find("h1").text.strip()  # type: ignore

        rauthor = sidebar.find("div", class_="follow")  # type: ignore
        if rauthor is not None:
            rauthor_url = rauthor.find("a")['href']  # type: ignore
            rauthor_img = rauthor.find("img")  # type: ignore
            rauthor_img_url = rauthor_img['src']  # type: ignore
            rauthor_name = rauthor_img['alt']  # type: ignore
        else:
            rauthor_name = os.environ.get("WATTPAD_USERNAME", "N/A")
            rauthor_url = f"https://www.wattpad.com/user/{rauthor_name}"
            rauthor_img_url = "https://img.wattpad.com/useravatar/N/A.128.577281.jpg"

        # cover
        cover = sidebar.find("div", class_="cover")  # type: ignore
        cover_url = cover.find("img")['src']  # type: ignore

        # numStories
        numStories = len(books)

        author = Author(url=rauthor_url, username=rauthor_name,author_img_url=rauthor_img_url)  # type: ignore

        reading_list = ReadingList(id=id, name=name, author=author,
                                   numOfStories=numStories, books=books, cover_url=cover_url)

        return reading_list

    @classmethod
    def from_json(cls, data):
        if isinstance(data, str):
            data = json.loads(data)

        user = Author(url=f"https://www.wattpad.com/user/{data['user']['name']}",
                      username=data['user']['name'], author_img_url=data['user']['avatar'])
        books = [Book.from_json(book) for book in data['stories']]
        reading_list = ReadingList(id=data['id'], name=data['name'], author=user,
                                   numOfStories=data['numStories'], books=books, cover_url=data['cover'])
        return reading_list

    @access_for_authenticated_user
    def add_book(self, book: Union['Book', str, list]):
        """Add a book to the reading list"""
        return self.request.add_to_reading_list(book, self)
    
    @access_for_authenticated_user
    def add_books(self, books: list):
        """Add multiple books to the reading list"""
        return self.request.add_to_reading_list(books, self)

    @access_for_authenticated_user
    def remove_book(self, book: Union['Book', str, list]):
        """Remove a book from the reading list"""
        return self.request.remove_from_reading_list(book, self)
    
    @access_for_authenticated_user
    def remove_books(self, books: list):
        """Remove multiple books from the reading list"""
        return self.request.remove_from_reading_list(books, self)

    def update(self, title=None):
        """Update the reading list"""
        if title is not None:
            self.change_title(title)        
        self = self.request.get_reading_list(self.id)
    
    # title setter and getter
    @property
    def title(self):
        return self.name
    
    @title.setter
    def title(self, title):
        self.change_title(title)
    
    @access_for_authenticated_user
    def change_title(self, name: str):
        """Change the name of the reading list"""
        r = self.request.change_reading_list_title(self, name)
        self.name = name
        return r
            
    
    @access_for_authenticated_user
    def delete(self):
        """Delete the reading list"""
        return self.request.delete_reading_list(self.id)

    def __repr__(self):
        return f"ReadingList(id={self.id}, name={self.name}, created_by={self.author}, numOfStories={self.numOfStories}, books={self.books}, cover_url={self.cover_url})"

    def __str__(self) -> str:
        return self.__repr__()

    def __eq__(self, other):
        if isinstance(other, ReadingList):
            return self.id == other.id
        return False


class ReadingListRequest:
    """Actions that can be performed on users ReadingList"""

    def __init__(self, verbose=False, user: 'User' = None):  # type: ignore
        self.verbose = verbose
        self.log = Log(name='wattpad_log', verbose=self.verbose)
        self.user = user

    def __hash__(self) -> int:
        return hash(self.user)
    
    def create_reading_list(self, title) -> Union[ReadingList, bool]:
        json_data = {
            'id': None,
            'name': title,
            'numStories': 0,
            'cover': 0,
            'tags': [],
            'featured': False,
            'action': 'create',
        }
        response = session.post(
            'https://www.wattpad.com/api/v3/lists/', headers=headers, json=json_data)
        if response.status_code == 200:
            self.log.info(
                f'{title} - Reading List was Successfully Created !!!')
            return ReadingList(id=response.json()['id'], name=title, author=self.user, numOfStories=0, books=[], cover_url=None)
        else:
            self.log.error(response.json()['message'])
            return False

    def create_reading_list_if_not_exists(self, title) -> Union[ReadingList, bool]:
        reading_list = self.get_reading_list(title)
        if reading_list:
            return reading_list
        else:
            return self.create_reading_list(title)


    def change_reading_list_title(self, reading_list: ReadingList, name: str) -> bool:
        data = {
            'cover': reading_list.cover_url,
            'featured': False,
            'id': reading_list.id,
            'tags': [],
            'name': name,
            'numStories': reading_list.numOfStories,
            'tags': [],
        }
        
        url = f"https://www.wattpad.com/api/v3/lists/{reading_list.id}"
        response = session.put(url, headers=headers, json=data)
        if response.status_code == 200:
            self.log.info(
                f'{reading_list.name} - Reading List was Successfully Updated to {name} !!!')
            return True
        else:
            self.log.error(response.json()['message'])
            return False
    
    def get_user_reading_lists(self,start=0,limit=100,username=None) -> List[ReadingList]:
        if not username:
            if self.user:
                username = self.user.username
            else:
                if "WATTPAD_USERNAME" in os.environ:
                    username = os.environ["WATTPAD_USERNAME"]
                    self.user = User(username=username)
                else:
                    raise ValueError("Username is not provided")

        
        url = f"https://www.wattpad.com/api/v3/users/{username}/lists?offset={start}&limit={limit}&fields=lists(id,name,user(name,avatar),numStories,featured,cover,stories)"

        response = session.get(url)
        if response.status_code == 200:
            reading_lists = []
            for reading_list in response.json()['lists']:
                reading_lists.append(ReadingList.from_json(reading_list))
            return reading_lists
        else:
            self.log.error(response.json()['message'])
            return []

    def get_reading_list(self, id_or_url, username=None) -> ReadingList:
        id_or_url = str(id_or_url)

        if "http" not in id_or_url and not id_or_url.isdigit():
            # it is a title
            reading_lists = self.get_user_reading_lists(username=username)
            found = False
            for reading_list in reading_lists:
                if reading_list.name == id_or_url:
                    found = True
                    return reading_list

            if not found:
                self.log.error(
                    f"Reading List with title {id_or_url} does not exist")
                return None  # type: ignore 
            
        rid = id_or_url
        
        if "http" in rid:
            rid = rid.split("/")[-1]
        
        if not rid.isdigit():
            rid = re.findall(r'\d+', rid)[0]            

        res1 = session.get(f"https://www.wattpad.com/api/v3/lists/{rid}")
        data = res1.json()
        if res1.status_code != 200:
            self.log.error(data['message'])
            return None # type: ignore
        
        numStories = data['numStories']
        
        all_data = {**data, "stories": []}
        return ReadingList.from_json(all_data)
    
    def get_books(self, rid,limit,start=0) -> List[Book]:
        url = f"https://www.wattpad.com/api/v3/lists/{rid}/stories?fields=stories%28id%2Ctags%2Ctitle%2Ccover%2Cdescription%2Curl%2CvoteCount%2CreadCount%2CcommentCount%2CnumParts%2Ccompleted%2Cmature%2Cuser%28name%2Cavatar%29%2ClastPublishedPart%28createDate%29%29%2Ctotal%2CnextUrl&offset={start}&limit={limit}"
        res = session.get(url)
        data = res.json()
        if res.status_code != 200:
            self.log.error(data['message'])
            return []
        
        books = [Book.from_json(book) for book in data['stories']]
        return books
        
        
    def delete_reading_list(self, id_or_url):
        id_or_url = str(id_or_url)
        rid = id_or_url

        if "http" in id_or_url:
            rid = id_or_url.split("/")[-1]

        if not rid.isdigit():
            rid = re.findall(r"\d+", rid)[0]

        response = session.delete(
            f'https://www.wattpad.com/api/v3/lists/{rid}', headers=headers)
        if response.status_code == 200:
            self.log.info('Reading List was Successfully Deleted !!!', rid)
            return True
        else:
            try:
                self.log.error(response.json()['message'])
            except json.decoder.JSONDecodeError:
                self.log.error(response.text)
            # looks like the reading list does not exist
            self.log.error(f"Reading List with id {id_or_url} does not exist")
            return False
    
    def add_to_reading_list_bulk(self, books: List[Union[Book, str]], reading_list: Union[ReadingList, str])-> List[bool]:
        # use threads to speed up the process
        with cf.ThreadPoolExecutor(max_workers=get_workers()) as executor:
            futures = [executor.submit(self.add_to_reading_list, book, reading_list) for book in books]
            return [future.result() for future in futures] # type: ignore

        
    def add_to_reading_list(self, book: Union[Book, str,list], reading_list: Union[ReadingList, str]) -> Union[bool, List[bool]]:
        if isinstance(book, list):
            return self.add_to_reading_list_bulk(book, reading_list)
        
        elif isinstance(book, str):
            bid = book.split("/")[-1]
            if not bid.isdigit():
                bid = re.findall(r"\d+", bid)[0]
        else:
            bid = book.id

        if isinstance(reading_list, str):
            rid = reading_list.split("/")[-1]
            if not rid.isdigit():
                rid = re.findall(r"\d+", rid)[0]
        else:
            rid = reading_list.id

        data = {
            'stories': bid
        }
        #  https://www.wattpad.com/api/v3/lists/1382349088/stories
        response = session.post(
            url=f'https://www.wattpad.com/api/v3/lists/{rid}/stories', headers=headers, json=data)


        if response.status_code == 200:
            self.log.info('The Book Successfully Added to Reading List !!!')
            return True
        else:
            try:
                self.log.error(response.json()['message'])
            except json.decoder.JSONDecodeError:
                self.log.error(response.text)
            return False
    
    def remove_from_reading_list_bulk(self, books: List[Union[Book, str]], reading_list: Union[ReadingList, str])-> List[bool]:
        # use threads to speed up the process
        with cf.ThreadPoolExecutor(max_workers=get_workers()) as executor:
            futures = [executor.submit(self.remove_from_reading_list, book, reading_list) for book in books]
            return [future.result() for future in futures] # type: ignore

    def remove_from_reading_list(self, book: Union[str, Book, list], reading_list: Union[str, ReadingList]) -> Union[bool, List[bool]]:
        if isinstance(book, list):
            return self.remove_from_reading_list_bulk(book, reading_list)
        
        bid = book
        if isinstance(book, str):
            bid = book.split("/")[-1]
            if not bid.isdigit():
                bid = re.findall(r"\d+", bid)[0]
        elif isinstance(book, Book):
            bid = book.id
        else:
            bid = str(book)

        rid = reading_list
        if isinstance(reading_list, str):
            rid = reading_list.split("/")[-1]
            if not rid.isdigit():
                rid = re.findall(r"\d+", rid)[0]
        elif isinstance(reading_list, ReadingList):
            rid = reading_list.id
        else:
            rid = str(reading_list)

        response = session.delete(
            url=f'https://www.wattpad.com/api/v3/lists/{rid}/stories/{bid}', headers=headers)

        if response.status_code == 200:
            self.log.info('Book was Successfully Removed from Reading List !!!',
                          f'Book ID: {bid}', f'Reading List ID: {rid}')
            return True

        else:
            try:
                self.log.error(response.json()['message'])
            except json.decoder.JSONDecodeError:
                self.log.error(response.text)
            return False


def close():
    session.close()


atexit.register(close)
